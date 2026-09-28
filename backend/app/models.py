"""SQLAlchemy models (portable across SQLite and Postgres)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    TypeDecorator,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores UTC; always returns timezone-aware datetimes (SQLite drops tzinfo otherwise)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    filename: Mapped[str] = mapped_column(String(255), default="")
    file_type: Mapped[str] = mapped_column(String(10), default="")
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ats_score: Mapped[int] = mapped_column(Integer, default=0)
    suggestions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    external_id: Mapped[str] = mapped_column(String(200), default="")
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    remote_type: Mapped[str] = mapped_column(String(20), default="unknown")  # remote/hybrid/onsite/unknown
    regions: Mapped[list[str]] = mapped_column(JSON, default=list)
    tz_restrictions: Mapped[list[float]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    apply_url: Mapped[str] = mapped_column(String(1000), default="")
    apply_method: Mapped[str] = mapped_column(String(30), default="job_board")
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(10), default="")
    salary_text: Mapped[str] = mapped_column(String(200), default="")
    employment_type: Mapped[str] = mapped_column(String(50), default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    posted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    also_seen_on: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)

    eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    eligibility_reason: Mapped[str] = mapped_column(String(300), default="")
    scam_score: Mapped[int] = mapped_column(Integer, default=0)
    scam_level: Mapped[str] = mapped_column(String(10), default="low")
    scam_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    match_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    match_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    job_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    role_family: Mapped[str] = mapped_column(String(50), default="")
    scored_resume_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    digested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    application: Mapped[Application | None] = relationship(back_populates="job", uselist=False)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="saved", index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    follow_up_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="application")


class TailoredDoc(Base):
    __tablename__ = "tailored_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    resume_version_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # resume | cover_letter
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | approved | rejected
    guardrail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generator: Mapped[str] = mapped_column(String(20), default="template")  # llm | template
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ApiCall(Base):
    """Every outbound call to a rate-limited API, used for budgets."""

    __tablename__ = "api_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), default="fetch")


class SourceHealth(Base):
    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    message: Mapped[str] = mapped_column(String(500), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_fetch_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    backoff_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    new: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[str] = mapped_column(String(500), default="")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    encrypted_token: Mapped[str] = mapped_column(Text)
    encrypted_email: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class EmailThread(Base):
    """Recruiter/alert emails seen in Gmail (stored locally only, never logged)."""

    __tablename__ = "email_threads"
    __table_args__ = (UniqueConstraint("gmail_message_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64))
    gmail_thread_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)  # recruiter/interview/rejection/application_update/job_alert
    subject: Mapped[str] = mapped_column(String(500), default="")
    from_name: Mapped[str] = mapped_column(String(200), default="")
    from_email: Mapped[str] = mapped_column(String(200), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    labeled: Mapped[bool] = mapped_column(Boolean, default=False)
    draft_id: Mapped[str] = mapped_column(String(64), default="")
    last_from_me_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    awaiting_reply_since: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    follow_up_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    subject: Mapped[str] = mapped_column(String(300), default="")
    html: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    job_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    send_error: Mapped[str] = mapped_column(String(300), default="")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class ProfileText(Base):
    __tablename__ = "profile_texts"
    __table_args__ = (UniqueConstraint("platform", "field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(40))
    field: Mapped[str] = mapped_column(String(60))
    generated_text: Mapped[str] = mapped_column(Text, default="")
    current_text: Mapped[str] = mapped_column(Text, default="")
    generator: Mapped[str] = mapped_column(String(20), default="template")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class ProfileChecklist(Base):
    __tablename__ = "profile_checklist"
    __table_args__ = (UniqueConstraint("platform", "item_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(40))
    item_key: Mapped[str] = mapped_column(String(60))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # weekly_checkin | monthly_trends
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
