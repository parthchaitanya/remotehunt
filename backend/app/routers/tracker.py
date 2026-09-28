from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import load_profile
from ..db import get_db
from ..gmail import client as gmail
from ..gmail.sync import draft_follow_up, due_followups
from ..models import Application, Job, utcnow
from ..serializers import application

router = APIRouter(prefix="/api/tracker", tags=["tracker"])
STATUSES = ["saved", "applying", "applied", "interview", "offer", "rejected", "withdrawn"]


@router.get("")
def board(db: Session = Depends(get_db)):
    cols = {s: [] for s in STATUSES}
    for a in db.scalars(select(Application).order_by(Application.position, Application.updated_at.desc())):
        cols.setdefault(a.status, []).append(application(a))
    return {"statuses": STATUSES, "columns": cols}


class AddBody(BaseModel):
    job_id: int
    status: str = "saved"


def _set_status(a: Application, status: str) -> None:
    if status not in STATUSES:
        raise HTTPException(400, f"status must be one of {STATUSES}")
    if status == "applied" and a.status != "applied":
        a.applied_at = a.applied_at or utcnow()
        a.follow_up_at = a.applied_at + timedelta(days=int(load_profile()["gmail"].get("follow_up_days", 7)))
        a.follow_up_done = False
    if status in ("interview", "offer", "rejected", "withdrawn"):
        a.follow_up_done = True
    a.status = status


@router.post("")
def add(body: AddBody, db: Session = Depends(get_db)):
    job = db.get(Job, body.job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    a = db.scalar(select(Application).where(Application.job_id == body.job_id))
    if a is None:
        pos = (db.scalar(select(func.max(Application.position))) or 0) + 1
        a = Application(job_id=body.job_id, status="saved", position=pos)
        db.add(a)
    job.hidden = False
    _set_status(a, body.status)
    db.commit()
    return application(a)


class PatchBody(BaseModel):
    status: str | None = None
    position: int | None = None
    notes: str | None = None
    follow_up_done: bool | None = None


@router.patch("/{app_id}")
def patch(app_id: int, body: PatchBody, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(404, "Application not found")
    if body.status is not None:
        _set_status(a, body.status)
    if body.position is not None:
        a.position = body.position
    if body.notes is not None:
        a.notes = body.notes
    if body.follow_up_done is not None:
        a.follow_up_done = body.follow_up_done
    db.commit()
    return application(a)


@router.delete("/{app_id}")
def remove(app_id: int, db: Session = Depends(get_db)):
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(404, "Application not found")
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/followups")
def followups(db: Session = Depends(get_db)):
    return due_followups(db)


@router.post("/{app_id}/followup-draft")
def followup_draft(app_id: int, db: Session = Depends(get_db)):
    """Creates a Gmail draft (if a related email thread exists) or returns the text. Never sends."""
    try:
        if not gmail.is_connected(db):
            from ..gmail.sync import _draft_text

            a = db.get(Application, app_id)
            if a is None:
                raise LookupError
            return {"body": _draft_text(db, "follow_up", f"{a.job.title} at {a.job.company}"), "draft_id": "",
                    "open_url": "", "note": "Gmail not connected - copy this text into your email client."}
        return draft_follow_up(db, application_id=app_id)
    except LookupError:
        raise HTTPException(404, "Application not found") from None
