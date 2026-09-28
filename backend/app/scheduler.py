"""APScheduler jobs (Asia/Kolkata): search every 6h, digest 08:00 daily, weekly check-in, monthly trends."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .config import get_settings
from .db import SessionLocal

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def search_cycle() -> None:
    """Health checks -> fetch all due sources -> Gmail recruiter sync. Every step is failure-isolated."""
    from .gmail import client as gmail
    from .gmail.sync import sync_mailbox
    from .sources.registry import check_all_health, run_all

    try:
        check_all_health()
    except Exception as exc:
        log.warning("Health check cycle failed: %s", type(exc).__name__)
    try:
        run_all()
    except Exception as exc:
        log.warning("Search cycle failed: %s", type(exc).__name__)
    try:
        with SessionLocal() as db:
            if gmail.is_connected(db):
                sync_mailbox(db)
    except Exception as exc:
        log.warning("Gmail sync failed: %s", type(exc).__name__)


def daily_digest() -> None:
    from .gmail.digest import build_and_send

    try:
        with SessionLocal() as db:
            build_and_send(db)
    except Exception as exc:
        log.warning("Digest failed: %s", type(exc).__name__)


def weekly_checkin() -> None:
    from .reports.reports import weekly_checkin as run

    try:
        with SessionLocal() as db:
            run(db)
    except Exception as exc:
        log.warning("Weekly check-in failed: %s", type(exc).__name__)


def monthly_trends() -> None:
    from .reports.reports import monthly_trends as run

    try:
        with SessionLocal() as db:
            run(db)
    except Exception as exc:
        log.warning("Monthly report failed: %s", type(exc).__name__)


def start() -> BackgroundScheduler:
    global _scheduler
    tz = get_settings().timezone
    sched = BackgroundScheduler(timezone=tz, job_defaults={"coalesce": True, "max_instances": 1,
                                                           "misfire_grace_time": 3600})
    # First search shortly after start-up; per-source min intervals stop restarts from over-calling APIs.
    sched.add_job(search_cycle, IntervalTrigger(hours=6, timezone=tz), id="search",
                  next_run_time=datetime.now().astimezone() + timedelta(minutes=2))
    sched.add_job(daily_digest, CronTrigger(hour=8, minute=0, timezone=tz), id="digest")
    sched.add_job(weekly_checkin, CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=tz), id="weekly_checkin")
    sched.add_job(monthly_trends, CronTrigger(day=1, hour=9, minute=30, timezone=tz), id="monthly_trends")
    sched.start()
    _scheduler = sched
    log.info("Scheduler started (%s)", tz)
    return sched


def shutdown() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)


def jobs_info() -> list[dict[str, str | None]]:
    if _scheduler is None:
        return []
    return [{"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
             "trigger": str(j.trigger)} for j in _scheduler.get_jobs()]
