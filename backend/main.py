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
    # Check if user already exists
    existing = db.query(models.User).filter(models.User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    user = models.User(
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Auto-login: return token immediately after registration
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


# ─── Lead Routes (Protected) ────────────────────────────────────────

@app.get("/api/leads")
def get_leads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Lead)
        .filter(models.Lead.user_id == current_user.id)
        .order_by(models.Lead.id.desc())
        .all()
    )


@app.delete("/api/leads")
def clear_leads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db.query(models.Lead).filter(models.Lead.user_id == current_user.id).delete()
    db.commit()
    return {"status": "cleared", "message": "All your leads have been deleted."}


def process_leads_task(industry: str, location: str, user_id: int, db: Session):
    """Background task to scrape and enrich leads."""
    try:
        raw_leads = scraper.scrape_leads(industry, location, max_results=10)
        print(f"Scraped {len(raw_leads)} raw leads for '{industry}'")

        for rl in raw_leads:
            try:
                enriched = ai.enrich_lead(rl)

                lead = models.Lead(
                    user_id=user_id,
                    name=enriched.get("name", "Decision Maker"),
                    role=enriched.get("role", "Executive"),
                    company=rl["company"],
                    industry=rl["industry"],
                    location=rl["location"],
                    email=rl["email"],
                    status="ready",
                    summary=enriched.get("summary", rl.get("summary_raw", "")),
                    email_draft=enriched.get("email_draft", ""),
                )
                db.add(lead)
                db.commit()
                print(f"  ✓ Saved lead: {lead.name} at {lead.company}")

                import time
                time.sleep(1)
            except Exception as e:
                print(f"  ✗ Error processing lead for {rl.get('company', '?')}: {e}")
                db.rollback()
                continue

    except Exception as e:
        print(f"Error in lead generation pipeline: {e}")


@app.post("/api/generate")
def generate_leads(
    industry: str,
    background_tasks: BackgroundTasks,
    location: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not industry:
        raise HTTPException(status_code=400, detail="Industry is required")

    background_tasks.add_task(process_leads_task, industry, location, current_user.id, db)

    return {
        "status": "accepted",
        "message": f"Lead generation queued for '{industry}' in '{location or 'Anywhere'}'.",
    }
