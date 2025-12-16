from __future__ import annotations

import os
import json
from datetime import datetime
from sqlalchemy import (
    create_engine, Integer, String, DateTime, Text, ForeignKey, text
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, relationship, Session, Mapped, mapped_column
)
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    tokens = relationship("OAuthToken", back_populates="user", cascade="all,delete-orphan")
    events = relationship("Event", back_populates="user", cascade="all,delete-orphan")

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    token_json: Mapped[str] = mapped_column(Text)

    user = relationship("User", back_populates="tokens")

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50), default="local")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    view: Mapped[str | None] = mapped_column(String(50), nullable=True)

    user = relationship("User", back_populates="events")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///app.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    Base.metadata.create_all(bind=engine)

    ensure_view_column()

def ensure_view_column():
    
    try:
        with engine.begin() as conn:

            res = conn.execute(text("PRAGMA table_info('events')")).fetchall()
            cols = [r[1] for r in res] if res else []
            if 'view' in cols:
                return

            if engine.url.drivername.startswith('sqlite'):
                conn.execute(text("ALTER TABLE events ADD COLUMN view VARCHAR(50)"))
            else:

                conn.execute(text("ALTER TABLE events ADD COLUMN view VARCHAR(50) NULL"))
    except Exception:

        pass

def get_user_creds(user_id: int) -> Credentials | None:
    try:
        from google.oauth2.credentials import Credentials
    except Exception:
        Credentials = None

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT token_json FROM oauth_tokens WHERE user_id = :uid AND provider = 'google'"),
            {"uid": user_id}
        ).fetchone()

    if not row:
        return None

    if Credentials is None:
        return None

    return Credentials.from_authorized_user_info(json.loads(row[0]))

def ensure_user_exists(user_id: int):
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT user_id FROM users WHERE user_id = :uid"),
            {"uid": user_id}
        ).fetchone()
        if not existing:
            conn.execute(
                text("INSERT INTO users (user_id) VALUES (:uid)"),
                {"uid": user_id}
            )

def save_user_creds(user_id: int, creds: Credentials):
    ensure_user_exists(user_id)
    token_json = creds.to_json()
    with engine.begin() as conn:
        updated = conn.execute(
            text("UPDATE oauth_tokens SET token_json = :t WHERE user_id = :u AND provider = 'google'"),
            {"u": user_id, "t": token_json}
        )

        if updated.rowcount == 0:
            conn.execute(
                text("INSERT INTO oauth_tokens (user_id, provider, token_json) VALUES (:u, 'google', :t)"),
                {"u": user_id, "t": token_json}
            )
