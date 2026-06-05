from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import models
from database import engine, get_db
from auth import hash_password, verify_password, create_access_token, get_current_user
import scraper
import ai

# We now use Alembic for migrations instead of create_all()
# models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Lead Gen SaaS API")

# Configure CORS so our Next.js app on port 3000 can query us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
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
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name},
    }


@app.get("/api/auth/me")
def get_me(current_user: models.User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
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


def process_leads_task(industry: str, location: str, user_id: int, batch_id: int, db: Session, auto_enrich: bool):
    """Background task to scrape leads and optionally enrich them."""
    try:
        raw_leads = scraper.scrape_leads(industry, location, max_results=10)
        print(f"Scraped {len(raw_leads)} raw leads for '{industry}'")

        saved_count = 0
        for rl in raw_leads:
            try:
                # 1. Save initially as idle
                lead = models.Lead(
                    user_id=user_id,
                    batch_id=batch_id,
                    name="Decision Maker",
                    role="Executive",
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

                        lead.name = enriched.get("name", lead.name)
                        lead.role = enriched.get("role", lead.role)
                        lead.summary = enriched.get("summary", lead.summary)
                        lead.email_draft = enriched.get("email_draft", "")
                        lead.status = "ready"
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

    background_tasks.add_task(process_leads_task, industry, location, current_user.id, batch.id, db, auto_enrich)

    return {
        "status": "accepted",
        "batch_id": batch.id,
        "message": f"Lead generation queued for '{industry}' in '{location or 'Anywhere'}'.",
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
        lead.email_draft = enriched.get("email_draft", "")
        lead.status = "ready"
        db.commit()
        db.refresh(lead)
        return lead
    except Exception as e:
        lead.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
