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
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship to leads
    leads = relationship("Lead", back_populates="owner")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
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

    # Relationship to user
    owner = relationship("User", back_populates="leads")
