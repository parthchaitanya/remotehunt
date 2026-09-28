"""Label recruiter emails, track threads awaiting a reply, and compute follow-up reminders.

Nothing here sends mail. Reply/follow-up text is only ever saved as a Gmail draft.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import llm
from ..config import load_profile
from ..models import Application, EmailThread, Job, ResumeVersion, utcnow
from ..tailor.guardrail import build_allowed, check_text
from . import client as gmail
from .classify import LABELS, classify

log = logging.getLogger(__name__)
RECRUITER_CATS = ("recruiter", "interview", "application_update", "rejection")


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _date(h: str | None) -> datetime | None:
    try:
        return _aware(parsedate_to_datetime(h)) if h else None
    except (TypeError, ValueError):
        return None


def sync_mailbox(db: Session, days: int = 14, max_messages: int = 100) -> dict[str, int]:
    svc = gmail.service(db)
    me = (gmail.connected_email(db) or "").lower()
    q = f"newer_than:{int(days)}d -in:chats -in:sent -category:promotions -category:social"
    listing = svc.users().messages().list(userId="me", q=q, maxResults=max_messages).execute()
    gmail.record_call(db)
    known = set(db.scalars(select(EmailThread.gmail_message_id)))
    stats = {"scanned": 0, "labeled": 0, "recruiter": 0}
    for ref in listing.get("messages", []):
        if ref["id"] in known:
            continue
        msg = svc.users().messages().get(userId="me", id=ref["id"], format="metadata",
                                         metadataHeaders=["From", "Subject", "Date", "List-Unsubscribe"]).execute()
        gmail.record_call(db)
        stats["scanned"] += 1
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        cat = classify(headers.get("from", ""), headers.get("subject", ""), msg.get("snippet", ""),
                       "list-unsubscribe" in headers)
        if cat is None or cat == "job_alert":
            continue  # alerts are labelled by the gmail_alerts source
        name, addr = parseaddr(headers.get("from", ""))
        if addr.lower() == me:
            continue
        labels = [LABELS["recruiter"]] + ([LABELS[cat]] if cat != "recruiter" else [])
        try:
            gmail.add_labels(db, svc, ref["id"], labels)
            labeled = True
            stats["labeled"] += 1
        except Exception:
            labeled = False
            log.warning("Could not label a recruiter email")
        db.add(EmailThread(gmail_message_id=ref["id"], gmail_thread_id=msg.get("threadId", ""), category=cat,
                           subject=headers.get("subject", "")[:500], from_name=name[:200], from_email=addr[:200],
                           snippet=msg.get("snippet", ""), received_at=_date(headers.get("date")), labeled=labeled,
                           job_id=_guess_job(db, headers.get("subject", ""), addr)))
        stats["recruiter"] += 1
    db.commit()
    stats["threads_checked"] = refresh_reply_state(db, svc, me)
    log.info("Gmail sync: scanned=%d recruiter=%d labeled=%d", stats["scanned"], stats["recruiter"], stats["labeled"])
    return stats


def _guess_job(db: Session, subject: str, sender: str) -> int | None:
    """Link an email to a tracked application by company name."""
    s = f"{subject} {sender}".lower()
    for app in db.scalars(select(Application)):
        company = (app.job.company or "").lower() if app.job else ""
        if company and len(company) > 2 and company.split()[0] in s:
            return app.job_id
    return None


def refresh_reply_state(db: Session, svc, me: str) -> int:
    """For recruiter threads, record whether the last message is yours (awaiting their reply)."""
    threads = {t.gmail_thread_id: t for t in db.scalars(
        select(EmailThread).where(EmailThread.category.in_(RECRUITER_CATS), EmailThread.follow_up_dismissed.is_(False))
        .order_by(EmailThread.received_at.desc()).limit(50))}
    for tid, row in threads.items():
        try:
            th = svc.users().threads().get(userId="me", id=tid, format="metadata",
                                           metadataHeaders=["From", "Date"]).execute()
            gmail.record_call(db)
        except Exception:
            continue
        msgs = th.get("messages", [])
        if not msgs:
            continue
        last = msgs[-1]
        h = {x["name"].lower(): x["value"] for x in last.get("payload", {}).get("headers", [])}
        from_me = parseaddr(h.get("from", ""))[1].lower() == me or "SENT" in (last.get("labelIds") or [])
        when = _date(h.get("date"))
        for r in db.scalars(select(EmailThread).where(EmailThread.gmail_thread_id == tid)):
            r.last_from_me_at = when if from_me else r.last_from_me_at
            r.awaiting_reply_since = when if from_me else None
    db.commit()
    return len(threads)


def due_followups(db: Session) -> list[dict[str, Any]]:
    days = int(load_profile()["gmail"].get("follow_up_days", 7))
    now = utcnow()
    out: list[dict[str, Any]] = []
    for app in db.scalars(select(Application).where(Application.status == "applied",
                                                    Application.follow_up_done.is_(False))):
        due = _aware(app.follow_up_at) or (_aware(app.applied_at) + timedelta(days=days) if app.applied_at else None)
        if due and due <= now:
            out.append({"type": "application", "application_id": app.id, "job_id": app.job_id,
                        "title": app.job.title if app.job else "", "company": app.job.company if app.job else "",
                        "applied_at": app.applied_at.isoformat() if app.applied_at else None,
                        "due_since": due.isoformat()})
    seen_threads = set()
    for t in db.scalars(select(EmailThread).where(EmailThread.awaiting_reply_since.is_not(None),
                                                  EmailThread.follow_up_dismissed.is_(False))):
        since = _aware(t.awaiting_reply_since)
        if since and since <= now - timedelta(days=days) and t.gmail_thread_id not in seen_threads:
            seen_threads.add(t.gmail_thread_id)
            out.append({"type": "thread", "thread_row_id": t.id, "subject": t.subject, "from_name": t.from_name,
                        "waiting_since": since.isoformat()})
    return out


def _resume(db: Session) -> ResumeVersion | None:
    return db.scalar(select(ResumeVersion).where(ResumeVersion.is_active.is_(True)).order_by(ResumeVersion.id.desc()))


def _draft_text(db: Session, purpose: str, context: str, instructions: str = "") -> str:
    resume = _resume(db)
    name = (resume.parsed.get("name") if resume else "") or ""
    fallback = {
        "reply": (f"Hi,\n\nThank you for reaching out. I'm interested and would be glad to continue the "
                  f"conversation. Please let me know the next steps or a convenient time to talk (I'm in IST, "
                  f"UTC+5:30).\n\nBest regards,\n{name}"),
        "follow_up": (f"Hi,\n\nI hope you're well. I wanted to follow up on my application and reiterate my interest "
                      f"in the role. I'd be happy to share anything else that would help.\n\nBest regards,\n{name}"),
    }[purpose]
    if not llm.available() or resume is None:
        return fallback
    system = ("You draft short, polite, professional emails for a job seeker. Never invent facts, skills, numbers, "
              "availability dates or commitments; do not accept or decline offers. Under 120 words. Plain text only.")
    user = (f"Purpose: {purpose.replace('_', ' ')}\nContext (email / application):\n{context[:3000]}\n\n"
            f"Candidate resume (facts you may use):\n{resume.raw_text[:3000]}\n\nExtra instructions: {instructions}\n"
            f"Sign off as {name}.")
    text = llm.chat(system, user, max_tokens=400)
    if not text:
        return fallback
    allowed = build_allowed(resume.parsed, resume.raw_text, ["UTC+5:30", "IST"])
    if check_text(text, allowed):
        return fallback
    return text.strip()


def draft_reply(db: Session, thread_row_id: int, instructions: str = "") -> dict[str, str]:
    row = db.get(EmailThread, thread_row_id)
    if row is None:
        raise LookupError("thread not found")
    svc = gmail.service(db)
    msg = svc.users().messages().get(userId="me", id=row.gmail_message_id, format="full").execute()
    gmail.record_call(db)
    html, text = gmail.message_body(msg.get("payload", {}))
    from ..textutil import html_to_text

    body = text or html_to_text(html)
    draft_body = _draft_text(db, "reply", f"Subject: {row.subject}\n\n{body}", instructions)
    draft_id = gmail.create_reply_draft(db, row.gmail_message_id, draft_body)
    row.draft_id = draft_id
    db.commit()
    return {"draft_id": draft_id, "body": draft_body,
            "open_url": "https://mail.google.com/mail/u/0/#drafts"}


def draft_follow_up(db: Session, *, application_id: int | None = None, thread_row_id: int | None = None) -> dict:
    if thread_row_id is not None:
        row = db.get(EmailThread, thread_row_id)
        if row is None:
            raise LookupError("thread not found")
        body = _draft_text(db, "follow_up", f"Subject: {row.subject}\nFrom: {row.from_name}\n{row.snippet}")
        draft_id = gmail.create_reply_draft(db, row.gmail_message_id, body)
        row.draft_id = draft_id
        db.commit()
        return {"draft_id": draft_id, "body": body, "open_url": "https://mail.google.com/mail/u/0/#drafts"}
    app = db.get(Application, application_id)
    if app is None:
        raise LookupError("application not found")
    thread = db.scalar(select(EmailThread).where(EmailThread.job_id == app.job_id)
                       .order_by(EmailThread.received_at.desc()))
    job: Job = app.job
    body = _draft_text(db, "follow_up", f"Application for {job.title} at {job.company}, applied "
                                        f"{app.applied_at:%d %b %Y}" if app.applied_at else job.title)
    result = {"body": body, "draft_id": "", "open_url": ""}
    if thread is not None:
        result["draft_id"] = gmail.create_reply_draft(db, thread.gmail_message_id, body)
        result["open_url"] = "https://mail.google.com/mail/u/0/#drafts"
    return result
