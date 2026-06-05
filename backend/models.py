from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    plan = Column(String, default="free")  # "free" or "pro"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    leads = relationship("Lead", back_populates="owner")
    batches = relationship("SearchBatch", back_populates="owner")


class SearchBatch(Base):
    """Each 'Generate Leads' click creates one batch — shown as a row in search history."""
    __tablename__ = "search_batches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    industry = Column(String, nullable=False)
    location = Column(String, nullable=True)
    lead_count = Column(Integer, default=0)
    status = Column(String, default="running")  # running, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="batches")
    leads = relationship("Lead", back_populates="batch")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    batch_id = Column(Integer, ForeignKey("search_batches.id"), nullable=True)
    name = Column(String, index=True)
    role = Column(String, nullable=True)
    company = Column(String, index=True)
    industry = Column(String, index=True)
    location = Column(String, nullable=True)
    email = Column(String, index=True, nullable=True)
    status = Column(String, default="idle")  # idle, scraping, enriching, ready, failed
    summary = Column(Text, nullable=True)
    email_draft = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="leads")
    batch = relationship("SearchBatch", back_populates="leads")
