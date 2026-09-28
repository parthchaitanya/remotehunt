from __future__ import annotations

from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import llm, scheduler
from ..config import get_settings, load_profile
from ..db import get_db
from ..gmail import client as gmail
from ..gmail.sync import due_followups
from ..models import Application, Job, Notification, Report, ResumeVersion, utcnow
from ..reports.reports import monthly_trends, weekly_checkin
from ..serializers import job_summary, notification, report
from ..skills import DISPLAY

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(days: int = 30, db: Session = Depends(get_db)):
    tz = ZoneInfo(get_settings().timezone)
    since = utcnow() - timedelta(days=days)
    jobs = list(db.scalars(select(Job).where(Job.first_seen_at >= since)))
    per_day: Counter = Counter(j.first_seen_at.astimezone(tz).date().isoformat() if j.first_seen_at.tzinfo
                               else j.first_seen_at.date().isoformat() for j in jobs)
    today = utcnow().astimezone(tz).date()
    series = [{"date": (today - timedelta(days=i)).isoformat(),
               "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(days - 1, -1, -1)]
    buckets = Counter()
    for j in jobs:
        if j.match_score is not None:
            buckets[min(9, j.match_score // 10)] += 1
    hist = [{"bucket": f"{b * 10}-{b * 10 + 9}", "count": buckets.get(b, 0)} for b in range(10)]
    skills: Counter = Counter()
    missing: Counter = Counter()
    for j in jobs:
        skills.update(set(j.job_skills or []))
        if (j.match_score or 0) >= 40:
            missing.update(j.missing_skills or [])
    apps = list(db.scalars(select(Application)))
    funnel = Counter(a.status for a in apps)
    return {
        "window_days": days,
        "jobs_total": db.scalar(select(func.count()).select_from(Job)) or 0,
        "jobs_in_window": len(jobs),
        "per_day": series,
        "by_source": Counter(j.source for j in jobs).most_common(),
        "by_role": Counter(j.role_family or "Other" for j in jobs).most_common(),
        "eligibility": Counter("eligible" if j.eligible else "ineligible" if j.eligible is False else "unclear"
                               for j in jobs).most_common(),
        "scam_levels": Counter(j.scam_level for j in jobs).most_common(),
        "apply_methods": Counter(j.apply_method for j in jobs).most_common(),
        "score_histogram": hist,
        "top_skills": [(DISPLAY.get(k, k), n) for k, n in skills.most_common(15)],
        "top_missing_skills": missing.most_common(12),
        "funnel": {s: funnel.get(s, 0) for s in ["saved", "applying", "applied", "interview", "offer", "rejected",
                                                  "withdrawn"]},
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    resume = db.scalar(select(ResumeVersion).where(ResumeVersion.is_active.is_(True)).order_by(ResumeVersion.id.desc()))
    day = utcnow() - timedelta(days=1)
    top = db.scalars(select(Job).where(Job.hidden.is_(False), Job.scam_level != "high", Job.eligible.is_not(False),
                                       Job.first_seen_at >= utcnow() - timedelta(days=7))
                     .order_by(Job.match_score.desc().nulls_last()).limit(8))
    thr = int(load_profile()["matching"].get("tailor_min_score", 70))
    return {
        "resume": {"ats_score": resume.ats_score, "version_no": resume.version_no, "grade": resume.ats.get("grade")}
        if resume else None,
        "new_jobs_24h": db.scalar(select(func.count()).select_from(Job).where(Job.first_seen_at >= day)) or 0,
        "high_match_7d": db.scalar(select(func.count()).select_from(Job).where(
            Job.match_score >= thr, Job.eligible.is_not(False), Job.scam_level != "high",
            Job.first_seen_at >= utcnow() - timedelta(days=7))) or 0,
        "applications": db.scalar(select(func.count()).select_from(Application)) or 0,
        "interviews": db.scalar(select(func.count()).select_from(Application).where(
            Application.status == "interview")) or 0,
        "followups_due": due_followups(db),
        "top_jobs": [job_summary(j) for j in top],
        "notifications": [notification(n) for n in db.scalars(
            select(Notification).where(Notification.read.is_(False)).order_by(Notification.id.desc()).limit(10))],
        "gmail_connected": gmail.is_connected(db),
        "llm_available": llm.available(),
        "scheduler": scheduler.jobs_info(),
    }


@router.get("/notifications")
def notifications(db: Session = Depends(get_db)):
    return [notification(n) for n in db.scalars(select(Notification).order_by(Notification.id.desc()).limit(100))]


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if n is None:
        raise HTTPException(404, "Not found")
    n.read = True
    db.commit()
    return notification(n)


@router.get("/reports")
def reports(kind: str = "", db: Session = Depends(get_db)):
    stmt = select(Report).order_by(Report.id.desc()).limit(24)
    if kind:
        stmt = stmt.where(Report.kind == kind)
    return [report(r) for r in db.scalars(stmt)]


@router.post("/reports/{kind}/run")
def run_report(kind: str, db: Session = Depends(get_db)):
    if kind == "weekly_checkin":
        return report(weekly_checkin(db))
    if kind == "monthly_trends":
        return report(monthly_trends(db))
    raise HTTPException(404, "Unknown report")


@router.get("/settings")
def settings_view(db: Session = Depends(get_db)):
    s = get_settings()
    prof = load_profile()
    return {
        "llm": {"provider": "groq", "configured": llm.available(), "model": s.groq_model, "daily_cap": s.llm_daily_cap},
        "gmail": {"configured": gmail.client_config() is not None, "connected": gmail.is_connected(db),
                  "expected_email": prof["gmail"].get("address")},
        "keys": {"adzuna": bool(s.adzuna_app_id and s.adzuna_app_key), "jooble": bool(s.jooble_api_key),
                 "careerjet": bool(s.careerjet_affid)},
        "profile": prof, "timezone": s.timezone, "database": s.resolved_database_url.split(":", 1)[0],
        "scheduler": scheduler.jobs_info(),
    }
