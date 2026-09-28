"""Model -> JSON dicts for the API."""
from __future__ import annotations

from typing import Any

from .models import Application, Digest, EmailThread, Job, Notification, Report, ResumeVersion, TailoredDoc
from .pipeline.apply_method import LABELS as APPLY_LABELS
from .textutil import truncate


def _iso(dt):
    return dt.isoformat() if dt else None


def job_summary(j: Job) -> dict[str, Any]:
    return {
        "id": j.id, "title": j.title, "company": j.company, "location": j.location, "remote_type": j.remote_type,
        "source": j.source, "url": j.url, "apply_url": j.apply_url, "apply_method": j.apply_method,
        "apply_method_label": APPLY_LABELS.get(j.apply_method, j.apply_method), "salary_text": j.salary_text,
        "posted_at": _iso(j.posted_at), "first_seen_at": _iso(j.first_seen_at), "eligible": j.eligible,
        "eligibility_reason": j.eligibility_reason, "scam_score": j.scam_score, "scam_level": j.scam_level,
        "match_score": j.match_score, "match_reasons": j.match_reasons or [],
        "missing_skills": j.missing_skills or [], "matched_skills": j.matched_skills or [],
        "role_family": j.role_family, "hidden": j.hidden, "also_seen_on": j.also_seen_on or [],
        "tracker_status": j.application.status if j.application else None,
        "snippet": truncate((j.description or "").replace("\n", " "), 220),
    }


def job_detail(j: Job) -> dict[str, Any]:
    d = job_summary(j)
    d.update({"description": j.description, "regions": j.regions or [], "scam_flags": j.scam_flags or [],
              "match_breakdown": j.match_breakdown or {}, "job_skills": j.job_skills or [], "tags": j.tags or [],
              "employment_type": j.employment_type, "last_seen_at": _iso(j.last_seen_at)})
    return d


def resume_version(v: ResumeVersion, full: bool = False) -> dict[str, Any]:
    d = {"id": v.id, "version_no": v.version_no, "label": v.label, "filename": v.filename, "file_type": v.file_type,
         "ats_score": v.ats_score, "is_active": v.is_active, "note": v.note, "parent_id": v.parent_id,
         "created_at": _iso(v.created_at)}
    if full:
        d.update({"parsed": v.parsed, "ats": v.ats, "suggestions": v.suggestions, "raw_text": v.raw_text})
    return d


def application(a: Application) -> dict[str, Any]:
    return {"id": a.id, "job_id": a.job_id, "status": a.status, "position": a.position, "notes": a.notes,
            "applied_at": _iso(a.applied_at), "follow_up_at": _iso(a.follow_up_at),
            "follow_up_done": a.follow_up_done, "updated_at": _iso(a.updated_at),
            "job": job_summary(a.job) if a.job else None}


def doc(d: TailoredDoc) -> dict[str, Any]:
    return {"id": d.id, "job_id": d.job_id, "resume_version_id": d.resume_version_id, "kind": d.kind,
            "content": d.content, "status": d.status, "guardrail": d.guardrail, "generator": d.generator,
            "created_at": _iso(d.created_at), "approved_at": _iso(d.approved_at)}


def thread(t: EmailThread) -> dict[str, Any]:
    return {"id": t.id, "category": t.category, "subject": t.subject, "from_name": t.from_name,
            "from_email": t.from_email, "snippet": t.snippet, "received_at": _iso(t.received_at),
            "labeled": t.labeled, "draft_id": t.draft_id, "awaiting_reply_since": _iso(t.awaiting_reply_since),
            "job_id": t.job_id}


def digest(d: Digest, full: bool = False) -> dict[str, Any]:
    out = {"id": d.id, "created_at": _iso(d.created_at), "subject": d.subject, "sent": d.sent,
           "send_error": d.send_error, "job_count": len(d.job_ids or [])}
    if full:
        out["html"] = d.html
    return out


def notification(n: Notification) -> dict[str, Any]:
    return {"id": n.id, "created_at": _iso(n.created_at), "kind": n.kind, "title": n.title, "body": n.body,
            "read": n.read, "data": n.data}


def report(r: Report) -> dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "created_at": _iso(r.created_at), "data": r.data}
