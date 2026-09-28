"""Weekly resume check-in and monthly market-trend report."""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_profile
from ..models import Application, Job, Notification, Report, ResumeVersion, utcnow
from ..resume.service import rescore_ats
from ..resume.skill_gap import skill_gap
from ..skills import DISPLAY


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def weekly_checkin(db: Session) -> Report:
    resume = db.scalar(select(ResumeVersion).where(ResumeVersion.is_active.is_(True)).order_by(ResumeVersion.id.desc()))
    now = utcnow()
    week = now - timedelta(days=7)
    data: dict[str, Any] = {"period_start": week.isoformat(), "period_end": now.isoformat()}
    if resume is None:
        data["message"] = "No resume uploaded yet."
    else:
        prev_score = resume.ats_score
        rescore_ats(db, resume)
        roles = load_profile()["candidate"].get("target_roles", [])
        gap = skill_gap(db, resume.parsed, roles)
        age = (now - _aware(resume.created_at)).days
        data.update({
            "ats_score": resume.ats_score, "ats_change_since_last_check": resume.ats_score - prev_score,
            "resume_version": resume.version_no, "resume_age_days": age,
            "top_tips": resume.ats.get("top_tips", [])[:4],
            "skill_priorities": [{"role": g["role"], "coverage": g["coverage"],
                                  "learn_next": [p["skill"] for p in g["priorities"][:3]]} for g in gap],
        })
        if age > 30:
            data["nudge"] = f"Your resume hasn't changed in {age} days - consider adding recent work."
    apps = list(db.scalars(select(Application)))
    data["applications"] = {
        "applied_this_week": sum(1 for a in apps if a.applied_at and _aware(a.applied_at) >= week),
        "interviews": sum(1 for a in apps if a.status == "interview"),
        "offers": sum(1 for a in apps if a.status == "offer"),
        "total_tracked": len(apps),
    }
    jobs_week = list(db.scalars(select(Job).where(Job.first_seen_at >= week)))
    data["jobs"] = {"new_this_week": len(jobs_week),
                    "high_match": sum(1 for j in jobs_week if (j.match_score or 0) >= 70 and j.eligible is not False)}
    rep = Report(kind="weekly_checkin", data=data)
    db.add(rep)
    db.add(Notification(kind="weekly_checkin", title="Weekly resume check-in ready",
                        body=f"ATS {data.get('ats_score', '–')} · {data['jobs']['high_match']} high-match jobs this week",
                        data={"report_kind": "weekly_checkin"}))
    db.commit()
    return rep


def _window_stats(jobs: list[Job]) -> dict[str, Any]:
    skills: Counter = Counter()
    for j in jobs:
        skills.update(set(j.job_skills or []))
    by_role = Counter(j.role_family or "Other" for j in jobs)
    by_source = Counter(j.source for j in jobs)
    companies = Counter(j.company for j in jobs if j.company)
    apply = Counter(j.apply_method for j in jobs)
    elig = Counter("eligible" if j.eligible else "ineligible" if j.eligible is False else "unclear" for j in jobs)
    remote = Counter(j.remote_type for j in jobs)
    salaries: dict[str, list[float]] = {}
    for j in jobs:
        if j.salary_min and j.salary_currency:
            salaries.setdefault(j.salary_currency.upper(), []).append(j.salary_min)
    return {
        "total": len(jobs), "skills": skills, "by_role": dict(by_role), "by_source": dict(by_source),
        "top_companies": companies.most_common(10), "apply_methods": dict(apply), "eligibility": dict(elig),
        "remote_types": dict(remote),
        "salary_min_median": {cur: round(statistics.median(v)) for cur, v in salaries.items() if len(v) >= 3},
    }


def monthly_trends(db: Session) -> Report:
    now = utcnow()
    cur = list(db.scalars(select(Job).where(Job.first_seen_at >= now - timedelta(days=30))))
    prev = list(db.scalars(select(Job).where(Job.first_seen_at >= now - timedelta(days=60),
                                              Job.first_seen_at < now - timedelta(days=30))))
    c, p = _window_stats(cur), _window_stats(prev)
    rising = []
    for k, n in c["skills"].most_common(40):
        share = n / c["total"] if c["total"] else 0
        prev_share = p["skills"].get(k, 0) / p["total"] if p["total"] else 0
        rising.append({"skill": DISPLAY.get(k, k), "jobs": n, "share": round(100 * share, 1),
                       "change_pts": round(100 * (share - prev_share), 1) if p["total"] else None})
    data = {
        "period_start": (now - timedelta(days=30)).isoformat(), "period_end": now.isoformat(),
        "jobs_seen": c["total"], "jobs_prev_period": p["total"],
        "top_skills": rising[:15],
        "rising_skills": sorted([r for r in rising if r["change_pts"] is not None], key=lambda r: -r["change_pts"])[:8],
        "by_role": c["by_role"], "by_source": c["by_source"], "top_companies": c["top_companies"],
        "apply_methods": c["apply_methods"], "eligibility": c["eligibility"], "remote_types": c["remote_types"],
        "salary_min_median": c["salary_min_median"],
    }
    rep = Report(kind="monthly_trends", data=data)
    db.add(rep)
    top = ", ".join(s["skill"] for s in data["top_skills"][:5])
    db.add(Notification(kind="monthly_trends", title="Monthly market-trend report ready",
                        body=f"{c['total']} jobs analysed. Most requested: {top}", data={"report_kind": "monthly_trends"}))
    db.commit()
    return rep
