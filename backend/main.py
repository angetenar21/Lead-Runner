from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import models
from database import engine, get_db
from auth import hash_password, verify_password, create_access_token, get_current_user
import scraper
import ai
import cache
import billing

# We now use Alembic for migrations instead of create_all()
# models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Lead Gen SaaS API")

import os
# Strip any trailing slash the user might have accidentally added to FRONTEND_URL
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# Configure CORS so our Next.js app can query us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str


# ─── Health Check ────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Lead Gen SaaS API!"}

@app.get("/health")
def health_check():
    return {"status": "ok"}


# ─── Auth Routes ─────────────────────────────────────────────────────

@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = models.User(
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"user_id": user.id, "email": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "plan": user.plan or "free"},
    }


@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"user_id": user.id, "email": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "plan": user.plan or "free"},
    }


@app.get("/api/auth/me")
def get_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan": current_user.plan or "free",
    }


# ─── Search History (Batches) ───────────────────────────────────────

@app.get("/api/batches")
def get_batches(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    batches = (
        db.query(models.SearchBatch)
        .filter(models.SearchBatch.user_id == current_user.id)
        .order_by(models.SearchBatch.id.desc())
        .all()
    )
    return [
        {
            "id": b.id,
            "industry": b.industry,
            "location": b.location,
            "lead_count": b.lead_count,
            "status": b.status,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in batches
    ]


@app.delete("/api/batches/{batch_id}")
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    batch = db.query(models.SearchBatch).filter(
        models.SearchBatch.id == batch_id,
        models.SearchBatch.user_id == current_user.id,
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    # Delete all leads in this batch first
    db.query(models.Lead).filter(models.Lead.batch_id == batch_id).delete()
    db.delete(batch)
    db.commit()
    return {"status": "deleted"}


# ─── Lead Routes (Protected) ────────────────────────────────────────

@app.get("/api/leads")
def get_leads(
    batch_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Lead).filter(models.Lead.user_id == current_user.id)
    if batch_id:
        query = query.filter(models.Lead.batch_id == batch_id)
    return query.order_by(models.Lead.id.desc()).all()


@app.delete("/api/leads")
def clear_leads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db.query(models.Lead).filter(models.Lead.user_id == current_user.id).delete()
    db.query(models.SearchBatch).filter(models.SearchBatch.user_id == current_user.id).delete()
    db.commit()
    return {"status": "cleared", "message": "All your leads and search history have been deleted."}


def process_leads_task(industry: str, location: str, user_id: int, batch_id: int, db: Session, auto_enrich: bool, max_leads: int):
    """Background task to scrape leads and optionally enrich them."""
    try:
        cache_key = f"scrape:{industry.lower()}:{location.lower()}:{max_leads}"
        cached_leads = cache.get_json(cache_key)

        if cached_leads:
            print(f"  [Cache Hit] Using cached scraped leads for '{industry}' in '{location}'")
            raw_leads = cached_leads
        else:
            raw_leads = scraper.scrape_leads(industry, location, max_results=max_leads)
            print(f"Scraped {len(raw_leads)} raw leads for '{industry}' (requested {max_leads})")
            if raw_leads:
                cache.set_json(cache_key, raw_leads, expiry_seconds=86400) # cache for 24 hours

        saved_count = 0
        for rl in raw_leads:
            try:
                # 1. Save initially as idle
                lead = models.Lead(
                    user_id=user_id,
                    batch_id=batch_id,
                    name=rl.get("name_hint") or "Decision Maker",
                    role=rl.get("role_hint") or "Executive",
                    company=rl["company"],
                    industry=rl["industry"],
                    location=rl["location"],
                    email=rl["email"],
                    status="idle",
                    summary=rl.get("summary_raw", ""),
                    email_draft="",
                )
                db.add(lead)
                db.commit()
                db.refresh(lead)
                saved_count += 1
                print(f"  ✓ Saved lead: {lead.company}")

                # 2. Auto-enrich if requested
                if auto_enrich:
                    lead.status = "enriching"
                    db.commit()
                    
                    try:
                        lead_data = {
                            "company": lead.company,
                            "industry": lead.industry,
                            "location": lead.location,
                            "summary_raw": lead.summary,
                            "name_hint": "",
                            "role_hint": "",
                            "domain": rl.get("domain", ""),
                        }
                        enriched = ai.enrich_lead(lead_data)

                        extracted_name = enriched.get("name")
                        
                        # Fallback for vague names
                        if not extracted_name or extracted_name.lower().strip() in ["decision maker", "executive", "none", "null"]:
                            extracted_name = "Decision Maker"

                        lead.name = extracted_name
                        lead.role = enriched.get("role", lead.role)
                        lead.summary = enriched.get("summary", lead.summary)
                        lead.status = "enriched"
                        db.commit()
                        print(f"    ✓ Auto-enriched: {lead.name}")
                    except Exception as ai_e:
                        print(f"    ✗ Auto-enrich failed for {lead.company}: {ai_e}")
                        lead.status = "failed"
                        db.commit()

            except Exception as e:
                print(f"  ✗ Error saving lead for {rl.get('company', '?')}: {e}")
                db.rollback()
                continue

        # Update batch with final count and status
        batch = db.query(models.SearchBatch).filter(models.SearchBatch.id == batch_id).first()
        if batch:
            batch.lead_count = saved_count
            batch.status = "completed"
            db.commit()

    except Exception as e:
        print(f"Error in lead generation pipeline: {e}")
        batch = db.query(models.SearchBatch).filter(models.SearchBatch.id == batch_id).first()
        if batch:
            batch.status = "failed"
            db.commit()


@app.post("/api/generate")
def generate_leads(
    industry: str,
    background_tasks: BackgroundTasks,
    location: str = None,
    auto_enrich: bool = False,
    max_leads: int = 10,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not industry:
        raise HTTPException(status_code=400, detail="Industry is required")

    # Create a new search batch
    batch = models.SearchBatch(
        user_id=current_user.id,
        industry=industry.strip(),
        location=location.strip() if location else "",
        status="running",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # Enforce tier-based lead limits
    user_plan = current_user.plan or "free"
    plan_max = 10 if user_plan == "free" else 20
    max_leads = max(1, min(plan_max, max_leads))

    if max_leads > 10 and user_plan == "free":
        raise HTTPException(status_code=403, detail="Free plan is limited to 10 leads per scan. Upgrade to Pro for up to 20.")

    background_tasks.add_task(process_leads_task, industry, location, current_user.id, batch.id, db, auto_enrich, max_leads)

    return {
        "status": "accepted",
        "batch_id": batch.id,
        "message": f"Lead generation queued for '{industry}' in '{location or 'Anywhere'}'.",
    }


def process_single_company_task(company_name: str, user_id: int, batch_id: int, db: Session, auto_enrich: bool):
    try:
        rl = scraper.scrape_target_company(company_name)
        if not rl:
            print(f"Failed to find company: {company_name}")
            batch = db.query(models.SearchBatch).filter(models.SearchBatch.id == batch_id).first()
            if batch:
                batch.status = "failed"
                db.commit()
            return
            
        # Save initially
        lead = models.Lead(
            user_id=user_id,
            batch_id=batch_id,
            name=rl.get("name_hint") or "Decision Maker",
            role=rl.get("role_hint") or "Executive",
            company=rl["company"],
            industry=rl["industry"],
            location=rl["location"],
            email=rl["email"],
            status="idle",
            summary=rl.get("summary_raw", ""),
            email_draft="",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        
        saved_count = 1
        
        if auto_enrich:
            lead.status = "enriching"
            db.commit()
            try:
                lead_data = {
                    "company": lead.company,
                    "industry": lead.industry,
                    "location": lead.location,
                    "summary_raw": lead.summary,
                    "name_hint": "",
                    "role_hint": "",
                    "domain": rl.get("domain", ""),
                }
                enriched = ai.enrich_lead(lead_data)

                extracted_name = enriched.get("name")
                if not extracted_name or extracted_name.lower().strip() in ["decision maker", "executive", "none", "null"]:
                    db.delete(lead)
                    db.commit()
                    saved_count = 0
                else:
                    lead.name = extracted_name
                    lead.role = enriched.get("role", lead.role)
                    lead.summary = enriched.get("summary", lead.summary)
                    lead.status = "enriched"
                    db.commit()
            except Exception as e:
                lead.status = "failed"
                db.commit()

        batch = db.query(models.SearchBatch).filter(models.SearchBatch.id == batch_id).first()
        if batch:
            batch.lead_count = saved_count
            batch.status = "completed"
            db.commit()

    except Exception as e:
        print(f"Error in single company pipeline: {e}")
        batch = db.query(models.SearchBatch).filter(models.SearchBatch.id == batch_id).first()
        if batch:
            batch.status = "failed"
            db.commit()

@app.post("/api/generate/company")
def generate_single_company(
    company_name: str,
    background_tasks: BackgroundTasks,
    auto_enrich: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not company_name:
        raise HTTPException(status_code=400, detail="Company name is required")

    batch = models.SearchBatch(
        user_id=current_user.id,
        industry=f"Company: {company_name.strip()}",
        location="",
        status="running",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    background_tasks.add_task(process_single_company_task, company_name.strip(), current_user.id, batch.id, db, auto_enrich)

    return {
        "status": "accepted",
        "batch_id": batch.id,
        "message": f"Lead extraction queued for '{company_name}'.",
    }


@app.post("/api/leads/{lead_id}/enrich")
def enrich_single_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id, models.Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = "enriching"
    db.commit()

    try:
        lead_data = {
            "company": lead.company,
            "industry": lead.industry,
            "location": lead.location,
            "summary_raw": lead.summary,
            "name_hint": lead.name if lead.name != "Decision Maker" else "",
            "role_hint": lead.role if lead.role != "Executive" else "",
        }
        enriched = ai.enrich_lead(lead_data)

        lead.name = enriched.get("name", lead.name)
        lead.role = enriched.get("role", lead.role)
        lead.summary = enriched.get("summary", lead.summary)
        lead.status = "enriched"
        db.commit()
        db.refresh(lead)
        return lead
    except Exception as e:
        lead.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/leads/{lead_id}/draft")
def draft_email_for_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id, models.Lead.user_id == current_user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = "drafting"
    db.commit()

    try:
        lead_data = {
            "name": lead.name,
            "role": lead.role,
            "company": lead.company,
            "industry": lead.industry,
            "location": lead.location,
            "summary": lead.summary,
        }
        email_text = ai.draft_outreach_email(lead_data)

        lead.email_draft = email_text
        lead.status = "ready"
        db.commit()
        db.refresh(lead)
        return lead
    except Exception as e:
        lead.status = "enriched"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


# ─── Stripe Billing Endpoints ───────────────────────────────────────

import billing

PLAN_LIMITS = {
    "free": {"max_leads": 10, "price": 0, "label": "Free"},
    "pro": {"max_leads": 20, "price": 29, "label": "Pro"},
}

@app.get("/api/billing/status")
def billing_status(
    current_user: models.User = Depends(get_current_user),
):
    plan = current_user.plan or "free"
    info = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    return {
        "plan": plan,
        "label": info["label"],
        "max_leads": info["max_leads"],
        "price": info["price"],
        "has_stripe": bool(current_user.stripe_customer_id),
    }


@app.post("/api/billing/create-checkout")
def create_checkout(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Creates a Stripe Checkout Session and returns the URL.
    The frontend redirects the user to this URL for payment.
    """
    if current_user.plan == "pro":
        return {"status": "already_pro", "message": "You are already on the Pro plan."}

    try:
        result = billing.create_checkout_session(
            user_id=current_user.id,
            user_email=current_user.email,
        )
        return {
            "status": "checkout_created",
            "checkout_url": result["url"],
            "session_id": result["session_id"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/billing/verify-session")
def verify_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Verifies a Stripe Checkout Session after payment.
    If paid, upgrades the user to Pro.
    """
    try:
        result = billing.verify_checkout_session(session_id)

        if result["paid"] and result["user_id"] == current_user.id:
            current_user.plan = "pro"
            current_user.stripe_customer_id = result.get("stripe_customer_id", "")
            db.commit()
            db.refresh(current_user)

            return {
                "status": "success",
                "plan": "pro",
                "message": "Payment verified! You are now on the Pro plan.",
            }
        else:
            return {
                "status": "pending",
                "message": "Payment not yet confirmed. Please try again.",
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/billing/manage")
def manage_billing(
    current_user: models.User = Depends(get_current_user),
):
    """
    Creates a Stripe Customer Portal session for managing subscriptions.
    """
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found.")

    try:
        portal_url = billing.create_billing_portal_session(current_user.stripe_customer_id)
        return {"url": portal_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/billing/downgrade")
def downgrade(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Downgrade back to free plan."""
    current_user.plan = "free"
    db.commit()
    return {"status": "success", "plan": "free", "message": "Downgraded to Free plan."}


