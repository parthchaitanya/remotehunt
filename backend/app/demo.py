"""Public showcase mode: fictional candidate + snapshot of real public job postings.

In demo mode nothing leaves the server: no Gmail, no live job-API calls (so public visitors can't burn
rate limits), no uploads (so visitors can't leave personal data on a shared instance).
"""
from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal

log = logging.getLogger(__name__)
FIXTURE = Path(__file__).parent / "demo_data" / "jobs.json.gz"

# (method, path prefix) blocked in demo mode, with the reason shown to visitors
BLOCKED = [
    ("POST", "/api/resume/upload", "Uploading is disabled in the public demo - run RemoteHunt locally to use your own resume."),
    ("POST", "/api/search/run", "Live searches are disabled in the demo to respect the job APIs' rate limits."),
    ("POST", "/api/sources/", "Source health checks are disabled in the demo."),
    ("POST", "/api/gmail/", "Gmail features are disabled in the demo."),
    ("GET", "/api/gmail/auth/", "Gmail features are disabled in the demo."),
    ("POST", "/api/digests/run", "Sending digests is disabled in the demo (preview works)."),
]

DEMO_RESUME = """Asha Verma
+91 90000 00000 | asha.verma@example.com | github.com/ashaverma-demo | linkedin.com/in/ashaverma-demo
Professional Summary
Computer science student building data and machine learning applications with Python, SQL and Flask.
Education
Example Institute of Technology, Pune 2023-Present
Bachelor of Technology in Computer Science
Technical Skills
Programming: Python, Java, SQL
Machine Learning: Supervised Learning, Regression, Classification, NLP
Libraries: Pandas, NumPy, Scikit-learn, Matplotlib, Seaborn
Web Technologies: Flask, Streamlit, HTML, CSS
Databases: MySQL, MongoDB
Tools & Platforms: Git, Jupyter Notebook, Docker
Projects
Sales Forecaster: Demand Prediction Model Github
Python, Pandas, Scikit-learn, Streamlit
• Built a regression model predicting weekly sales for 1,200 stores, cutting forecast error by
18% versus the baseline.
• Deployed an interactive Streamlit dashboard used by 40+ classmates.
Review Sentiment Classifier Github
Python, NLP, Scikit-learn, Flask
• Trained a sentiment classifier on 25,000 product reviews reaching 89% accuracy.
• Served predictions through a Flask REST API with Docker.
Internship
Data Intern – Acme Analytics (Jun 2024 – Aug 2024)
Python, SQL, Excel
• Automated a weekly SQL reporting pipeline, saving 6 hours of manual work per week.
• Cleaned and analysed 50,000 customer records with Pandas to identify churn drivers.
Extracurricular Activities
Coding Club Lead (2024 – Present): Organised 3 hackathons with 300+ participants.
"""


async def middleware(request: Request, call_next):
    if get_settings().demo_mode:
        for method, prefix, reason in BLOCKED:
            if request.method == method and request.url.path.startswith(prefix):
                return JSONResponse({"detail": reason}, status_code=403)
    return await call_next(request)


def seed() -> None:
    """Populate an empty database with the demo resume, jobs, tracker, documents, profiles and reports."""
    from .models import Application, Job, ResumeVersion, TailoredDoc, utcnow
    from .pipeline.run import process
    from .profiles.generator import generate
    from .reports.reports import monthly_trends, weekly_checkin
    from .resume.ats import score_resume
    from .resume.parser import parse_text
    from .resume.service import target_roles
    from .resume.suggestions import generate_suggestions
    from .sources.base import RawJob, to_dt
    from .tailor.generator import build_cover_letter, build_resume

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(ResumeVersion)):
            return
        log.info("Seeding demo data")
        parsed = parse_text(DEMO_RESUME)
        parsed["file_type"] = "pdf"
        ats = score_resume(parsed, DEMO_RESUME, target_roles())
        v = ResumeVersion(version_no=1, label="v1 (demo)", filename="asha-verma-resume.pdf", file_type="pdf",
                          raw_text=DEMO_RESUME, parsed=parsed, ats=ats, ats_score=ats["score"], is_active=True,
                          suggestions=generate_suggestions(parsed, DEMO_RESUME, target_roles()))
        db.add(v)
        db.commit()

        rows = json.loads(gzip.decompress(FIXTURE.read_bytes())) if FIXTURE.exists() else []
        raws = [RawJob(**{**r, "posted_at": to_dt(r.get("posted_at"))}) for r in rows]
        stats = process(db, raws)
        log.info("Demo jobs loaded: %s", stats)
        from collections import Counter

        from .models import SourceHealth

        for source, n in Counter(r.source for r in raws).items():
            db.merge(SourceHealth(source=source, status="ok", message=f"Demo snapshot: {n} jobs",
                                  last_check_at=utcnow(), last_run_at=utcnow(), last_success_at=utcnow(),
                                  last_fetch_count=n, consecutive_failures=0))
        db.commit()

        top = list(db.scalars(select(Job).where(Job.eligible.is_not(False), Job.scam_level != "high")
                              .order_by(Job.match_score.desc().nulls_last()).limit(8)))
        for i, (job, status) in enumerate(zip(top, ["interview", "applied", "applied", "applying", "saved", "saved"])):
            a = Application(job_id=job.id, status=status, position=i)
            if status in ("applied", "interview"):
                from datetime import timedelta

                a.applied_at = utcnow() - timedelta(days=9 if i == 1 else 3)
                a.follow_up_at = a.applied_at + timedelta(days=7)
            db.add(a)
        db.commit()
        if top:
            for kind, fn in (("resume", build_resume), ("cover_letter", build_cover_letter)):
                content, guard, gen = fn(v, top[0])
                db.add(TailoredDoc(job_id=top[0].id, resume_version_id=v.id, kind=kind, content=content,
                                   guardrail=guard, generator=gen, status="approved" if kind == "resume" else "draft",
                                   approved_at=utcnow() if kind == "resume" else None))
            db.commit()
        for platform in ("linkedin", "github", "naukri"):
            generate(db, platform)
        weekly_checkin(db)
        monthly_trends(db)
        log.info("Demo seed complete")
