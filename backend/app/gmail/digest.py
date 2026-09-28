"""Daily digest (08:00 IST): new high-match jobs, follow-ups, recruiter mail, source problems.
Sent only to your own address; always stored in the app too.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings, load_profile
from ..models import Digest, EmailThread, Job, SourceHealth, utcnow
from ..pipeline.apply_method import LABELS as APPLY_LABELS
from . import client as gmail
from .sync import due_followups

log = logging.getLogger(__name__)


def collect(db: Session) -> dict[str, Any]:
    prof = load_profile()
    m = prof.get("matching", {})
    min_score = int(m.get("digest_min_score", 45))
    limit = int(m.get("digest_max_jobs", 15))
    since = utcnow() - timedelta(days=2)
    jobs = list(db.scalars(
        select(Job).where(Job.digested_at.is_(None), Job.first_seen_at >= since, Job.match_score >= min_score,
                          Job.scam_level != "high", or_(Job.eligible.is_(True), Job.eligible.is_(None)))
        .order_by(Job.match_score.desc()).limit(limit)))
    total_new = db.scalar(select(func.count()).select_from(Job).where(Job.first_seen_at >= utcnow() - timedelta(days=1)))
    recruiter = list(db.scalars(select(EmailThread).where(
        EmailThread.category.in_(("recruiter", "interview")), EmailThread.created_at >= utcnow() - timedelta(days=1))))
    problems = list(db.scalars(select(SourceHealth).where(SourceHealth.status.in_(("down", "degraded")))))
    return {"jobs": jobs, "total_new": total_new or 0, "followups": due_followups(db), "recruiter": recruiter,
            "problems": problems}


def render(data: dict[str, Any]) -> tuple[str, str, str]:
    tz = ZoneInfo(get_settings().timezone)
    today = utcnow().astimezone(tz).strftime("%a %d %b %Y")
    jobs: list[Job] = data["jobs"]
    subject = f"RemoteHunt digest – {today}: {len(jobs)} top matches"
    rows = []
    text = [subject, ""]
    for j in jobs:
        flag = "" if j.eligible else " (check region)"
        reasons = "; ".join((j.match_reasons or [])[:2])
        missing = ", ".join((j.missing_skills or [])[:4])
        link = j.apply_url or j.url
        rows.append(
            f"<tr><td style='padding:10px 8px;border-bottom:1px solid #eee;vertical-align:top'>"
            f"<div style='font-size:22px;font-weight:700;color:{'#15803d' if (j.match_score or 0) >= 70 else '#b45309'}'>"
            f"{j.match_score}</div></td><td style='padding:10px 8px;border-bottom:1px solid #eee'>"
            f"<a href='{escape(link)}' style='font-weight:600;color:#1d4ed8;text-decoration:none'>{escape(j.title)}</a>"
            f"<div style='color:#374151'>{escape(j.company or '')} · {escape(j.location or j.remote_type)}{flag}</div>"
            f"<div style='color:#6b7280;font-size:12px'>{escape(reasons)}</div>"
            + (f"<div style='color:#9a3412;font-size:12px'>Missing: {escape(missing)}</div>" if missing else "")
            + f"<div style='color:#6b7280;font-size:12px'>{escape(APPLY_LABELS.get(j.apply_method, j.apply_method))}"
              f" · via {escape(j.source)}{' · ' + escape(j.salary_text) if j.salary_text else ''}</div></td></tr>")
        text.append(f"[{j.match_score}] {j.title} – {j.company} ({j.location or j.remote_type}){flag}\n  {link}\n"
                    f"  {reasons}" + (f"\n  Missing: {missing}" if missing else ""))
    fu_html = "".join(
        f"<li>{escape(f.get('title') or f.get('subject') or '')} {escape('– ' + f['company'] if f.get('company') else '')}"
        f" <span style='color:#6b7280'>({'no reply to your email' if f['type'] == 'thread' else 'applied 7+ days ago'})"
        f"</span></li>" for f in data["followups"])
    rec_html = "".join(f"<li><b>{escape(t.category.title())}</b>: {escape(t.subject)}"
                       f" <span style='color:#6b7280'>– {escape(t.from_name or 'recruiter')}</span></li>"
                       for t in data["recruiter"])
    prob_html = "".join(f"<li>{escape(p.source)}: {escape(p.status)} – {escape(p.message[:120])}</li>"
                        for p in data["problems"])
    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:680px;margin:auto;color:#111">
<h2 style="margin:0 0 4px">RemoteHunt daily digest</h2>
<div style="color:#6b7280;margin-bottom:16px">{today} · {data['total_new']} new jobs in the last 24h · top {len(jobs)} shown</div>
<table style="border-collapse:collapse;width:100%">{''.join(rows) or '<tr><td>No new high-match jobs today.</td></tr>'}</table>
{f'<h3>Follow-ups due</h3><ul>{fu_html}</ul><p style="color:#6b7280;font-size:12px">Open RemoteHunt → Tracker to create a follow-up draft (drafts are never sent automatically).</p>' if fu_html else ''}
{f'<h3>Recruiter emails (last 24h)</h3><ul>{rec_html}</ul>' if rec_html else ''}
{f'<h3>Source issues</h3><ul>{prob_html}</ul>' if prob_html else ''}
<p style="color:#9ca3af;font-size:11px;margin-top:24px">Sent by your RemoteHunt instance to you only. Nothing is applied for or sent to anyone without your approval.</p>
</div>"""
    if data["followups"]:
        text += ["", "FOLLOW-UPS DUE"] + [f"- {f.get('title') or f.get('subject')}" for f in data["followups"]]
    if data["recruiter"]:
        text += ["", "RECRUITER EMAILS"] + [f"- {t.category}: {t.subject}" for t in data["recruiter"]]
    return subject, html, "\n".join(text)


def build_and_send(db: Session, send: bool = True) -> Digest:
    data = collect(db)
    subject, html, text = render(data)
    d = Digest(subject=subject, html=html, text=text, job_ids=[j.id for j in data["jobs"]])
    db.add(d)
    now = utcnow()
    for j in data["jobs"]:
        j.digested_at = now
    db.commit()
    if send:
        try:
            if gmail.is_connected(db):
                gmail.send_to_self(db, subject, html, text)
                d.sent = True
            else:
                d.send_error = "Gmail not connected - digest stored in the app only"
        except Exception as exc:
            d.send_error = f"{type(exc).__name__}"[:300]
            log.warning("Digest send failed: %s", type(exc).__name__)
        db.commit()
    return d
