"""Export a snapshot of public job postings from your local DB into the demo fixture.

Only job-posting data is exported (titles, companies, descriptions, links) - nothing from your resume,
tracker, Gmail or settings.   Usage (from backend/):  ../.venv/bin/python scripts/export_demo_jobs.py
"""
import gzip
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Job  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "demo_data" / "jobs.json.gz"


def main(n_good: int = 160, n_rest: int = 140) -> None:
    random.seed(7)
    with SessionLocal() as db:
        jobs = list(db.scalars(select(Job)))
    good = sorted([j for j in jobs if j.eligible is not False and j.scam_level != "high"],
                  key=lambda j: -(j.match_score or 0))[:n_good]
    chosen = {j.id for j in good}
    rest = random.sample([j for j in jobs if j.id not in chosen], min(n_rest, len(jobs) - len(good)))
    out = []
    for j in good + rest:
        out.append(dict(
            source=j.source, external_id=j.external_id, title=j.title, company=j.company, url=j.url,
            apply_url=j.apply_url, description=(j.description or "")[:3500], location=j.location,
            remote={"remote": True, "onsite": False}.get(j.remote_type), region_restrictions=j.regions or [],
            timezone_restrictions=j.tz_restrictions or [], salary_min=j.salary_min, salary_max=j.salary_max,
            salary_currency=j.salary_currency, salary_text=j.salary_text, employment_type=j.employment_type,
            tags=j.tags or [], posted_at=j.posted_at.isoformat() if j.posted_at else None,
        ))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(json.dumps(out).encode())
    OUT.write_bytes(data)
    print(f"{len(out)} jobs, {len(data) // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()
