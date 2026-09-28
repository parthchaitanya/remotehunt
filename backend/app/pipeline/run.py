"""Pipeline: normalize -> eligibility -> scam -> apply method -> dedupe/upsert -> match score."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_profile
from ..models import Job, ResumeVersion, utcnow
from ..sources.base import RawJob
from . import apply_method, region, scam
from .dedupe import choose, dedupe_batch, link_rank
from .matcher import Matcher
from .normalize import NormJob, normalize

log = logging.getLogger(__name__)


def _active_resume(db: Session) -> ResumeVersion | None:
    return db.scalar(select(ResumeVersion).where(ResumeVersion.is_active.is_(True)).order_by(ResumeVersion.id.desc()))


def _apply_norm(job: Job, n: NormJob) -> None:
    job.source, job.external_id, job.title, job.company = n.source, n.external_id, n.title, n.company
    job.location, job.remote_type, job.regions = n.location, n.remote_type, n.regions
    job.tz_restrictions = n.tz_restrictions
    job.description, job.url, job.apply_url = n.description, n.url, n.apply_url
    job.salary_min, job.salary_max, job.salary_currency = n.salary_min, n.salary_max, n.salary_currency
    job.salary_text, job.employment_type, job.tags, job.posted_at = n.salary_text, n.employment_type, n.tags, n.posted_at


def _as_norm(job: Job) -> NormJob:
    return NormJob(source=job.source, external_id=job.external_id, title=job.title, company=job.company,
                   location=job.location, remote_type=job.remote_type, regions=job.regions or [], tz_restrictions=job.tz_restrictions or [],
                   description=job.description, url=job.url, apply_url=job.apply_url, salary_min=job.salary_min,
                   salary_max=job.salary_max, salary_currency=job.salary_currency, salary_text=job.salary_text,
                   employment_type=job.employment_type, tags=job.tags or [], posted_at=job.posted_at,
                   fingerprint=job.fingerprint)


def _classify(job: Job, n: NormJob, profile: dict[str, Any]) -> None:
    el = region.assess(n, profile)
    job.eligible, job.eligibility_reason = el.eligible, el.reason[:300]
    sr = scam.detect(n.title, n.company, n.description, n.source, n.apply_url, n.salary_max, n.salary_currency)
    job.scam_score, job.scam_level, job.scam_flags = sr.score, sr.level, sr.flags
    job.apply_method = apply_method.tag(n.source, n.url, n.apply_url, n.description, n.extra.get("platform", ""))


def process(db: Session, raws: list[RawJob]) -> dict[str, int]:
    profile = load_profile()
    norms = [n for n in (normalize(r) for r in raws) if n is not None]
    uniq, sightings = dedupe_batch(norms)
    fps = [n.fingerprint for n in uniq]
    existing: dict[str, Job] = {}
    for i in range(0, len(fps), 500):
        for j in db.scalars(select(Job).where(Job.fingerprint.in_(fps[i:i + 500]))):
            existing[j.fingerprint] = j

    now = utcnow()
    new_jobs: list[Job] = []
    changed: list[Job] = []
    for n in uniq:
        job = existing.get(n.fingerprint)
        extra_seen = sightings.get(n.fingerprint, [])
        if job is None:
            job = Job(fingerprint=n.fingerprint, first_seen_at=now, also_seen_on=[])
            _apply_norm(job, n)
            _classify(job, n, profile)
            db.add(job)
            new_jobs.append(job)
        else:
            job.last_seen_at = now
            current = _as_norm(job)
            primary, secondary = choose(current, n)
            if primary is n and link_rank(n) > link_rank(current):
                # Prefer the direct ATS link: swap the stored record to the better source.
                extra_seen = extra_seen + [{"source": current.source, "url": current.url}]
                _apply_norm(job, n)
                _classify(job, n, profile)
                changed.append(job)
            elif n.source != job.source:
                extra_seen = extra_seen + [{"source": n.source, "url": n.url}]
        if extra_seen:
            known = {(s["source"], s["url"]) for s in job.also_seen_on or []}
            merged = list(job.also_seen_on or [])
            for s in extra_seen:
                if (s["source"], s["url"]) not in known and s["url"] != job.url:
                    merged.append(s)
                    known.add((s["source"], s["url"]))
            job.also_seen_on = merged[:10]
    db.flush()
    scored = score_jobs(db, new_jobs + changed, profile)
    db.commit()
    return {"received": len(raws), "normalized": len(norms), "unique": len(uniq), "new": len(new_jobs),
            "upgraded": len(changed), "scored": scored}


def score_jobs(db: Session, jobs: list[Job], profile: dict[str, Any] | None = None,
               matcher: Matcher | None = None) -> int:
    if not jobs:
        return 0
    profile = profile or load_profile()
    resume = _active_resume(db)
    if resume is None:
        return 0
    matcher = matcher or Matcher(resume.parsed, resume.raw_text, profile)
    keep_min = int(profile.get("search", {}).get("keep_min_score", 25))
    done = 0
    for i in range(0, len(jobs), 64):
        batch = jobs[i:i + 64]
        results = matcher.score_many([{"title": j.title, "description": j.description, "tags": j.tags} for j in batch])
        for job, r in zip(batch, results):
            job.match_score = r.score
            job.match_breakdown = r.breakdown()
            job.match_reasons = r.reasons
            job.matched_skills = r.matched_skills
            job.missing_skills = r.missing_skills
            job.job_skills = r.job_skills
            job.role_family = r.role_family
            job.scored_resume_version = resume.id
            if job.application is None:
                job.hidden = bool(r.score < keep_min or job.scam_level == "high" or job.eligible is False)
            done += 1
    return done


def rescore_all(db: Session) -> int:
    profile = load_profile()
    resume = _active_resume(db)
    if resume is None:
        return 0
    matcher = Matcher(resume.parsed, resume.raw_text, profile)
    jobs = list(db.scalars(select(Job)))
    for j in jobs:  # region/scam rules may have changed too
        _classify(j, _as_norm(j), profile)
    n = score_jobs(db, jobs, profile, matcher)
    db.commit()
    log.info("Rescored %d jobs", n)
    return n
