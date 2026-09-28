from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings, load_profile
from ..db import get_db
from ..gmail import client as gmail
from ..gmail.digest import build_and_send, collect, render
from ..gmail.sync import RECRUITER_CATS, draft_follow_up, draft_reply, sync_mailbox
from ..models import Digest, EmailThread
from ..serializers import digest, thread

router = APIRouter(prefix="/api", tags=["gmail"])
log = logging.getLogger(__name__)


@router.get("/gmail/status")
def status(db: Session = Depends(get_db)):
    connected = gmail.is_connected(db)
    return {"configured": gmail.client_config() is not None, "connected": connected,
            "email": gmail.connected_email(db) if connected else None,
            "expected_email": load_profile()["gmail"].get("address"), "scopes": gmail.SCOPES}


@router.get("/gmail/auth/start")
def auth_start():
    try:
        return {"url": gmail.start_auth()}
    except gmail.GmailNotConnected as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/gmail/auth/callback")
def auth_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    front = get_settings().frontend_url.rstrip("/")
    if error or not code:
        return RedirectResponse(f"{front}/settings?gmail=denied")
    try:
        gmail.finish_auth(db, code, state)
    except Exception as exc:
        log.warning("Gmail OAuth failed: %s", type(exc).__name__)
        return RedirectResponse(f"{front}/settings?gmail=error&reason={type(exc).__name__}")
    return RedirectResponse(f"{front}/settings?gmail=connected")


@router.post("/gmail/disconnect")
def disconnect(db: Session = Depends(get_db)):
    gmail.disconnect(db)
    return {"connected": False}


@router.post("/gmail/sync")
def sync(db: Session = Depends(get_db)):
    try:
        return sync_mailbox(db)
    except gmail.GmailNotConnected as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/gmail/threads")
def threads(db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailThread).where(EmailThread.category.in_(RECRUITER_CATS))
                      .order_by(EmailThread.received_at.desc()).limit(100))
    return [thread(t) for t in rows]


class DraftBody(BaseModel):
    instructions: str = ""


@router.post("/gmail/threads/{tid}/draft-reply")
def reply_draft(tid: int, body: DraftBody, db: Session = Depends(get_db)):
    """Creates a Gmail DRAFT. RemoteHunt never sends replies to recruiters."""
    try:
        return draft_reply(db, tid, body.instructions)
    except LookupError:
        raise HTTPException(404, "Thread not found") from None
    except gmail.GmailNotConnected as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/gmail/threads/{tid}/followup-draft")
def thread_followup(tid: int, db: Session = Depends(get_db)):
    try:
        return draft_follow_up(db, thread_row_id=tid)
    except LookupError:
        raise HTTPException(404, "Thread not found") from None
    except gmail.GmailNotConnected as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/gmail/threads/{tid}/dismiss")
def dismiss(tid: int, db: Session = Depends(get_db)):
    t = db.get(EmailThread, tid)
    if t is None:
        raise HTTPException(404, "Thread not found")
    for r in db.scalars(select(EmailThread).where(EmailThread.gmail_thread_id == t.gmail_thread_id)):
        r.follow_up_dismissed = True
    db.commit()
    return {"ok": True}


@router.get("/digests")
def digests(db: Session = Depends(get_db)):
    return [digest(d) for d in db.scalars(select(Digest).order_by(Digest.id.desc()).limit(60))]


@router.get("/digests/preview", response_class=HTMLResponse)
def preview(db: Session = Depends(get_db)):
    _, html, _ = render(collect(db))
    return html


@router.get("/digests/{did}", response_class=HTMLResponse)
def digest_html(did: int, db: Session = Depends(get_db)):
    d = db.get(Digest, did)
    if d is None:
        raise HTTPException(404, "Digest not found")
    return d.html


class DigestBody(BaseModel):
    send: bool = True


@router.post("/digests/run")
def run_digest(body: DigestBody, db: Session = Depends(get_db)):
    return digest(build_and_send(db, send=body.send))
