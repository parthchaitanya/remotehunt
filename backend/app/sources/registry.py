"""Loads source plugins from config/sources.yaml and runs them safely (a source can never crash a run)."""
from __future__ import annotations

import logging
import threading
from datetime import timedelta, timezone
from typing import Any

from ..config import load_profile, load_sources_config
from ..db import SessionLocal
from ..models import SourceHealth, SourceRun, utcnow
from .aggregators import AdzunaSource, CareerjetSource, JoobleSource
from .ats_boards import AshbySource, GreenhouseSource, LeverSource, SmartRecruitersSource, WorkableSource
from .base import BudgetExceeded, HealthResult, NotConfigured, Source, SourceError
from .boards import (ArbeitnowSource, FourDayWeekSource, HasjobSource, HimalayasSource, HNJobsSource,
                     HNWhosHiringSource, JobicySource, MuseSource, RemoteOKSource, RemotiveSource, RSSFeedsSource,
                     WorkingNomadsSource, WWRSource)
from .gmail_alerts import GmailAlertsSource

log = logging.getLogger(__name__)

TYPES: dict[str, type[Source]] = {cls.type_name: cls for cls in (
    RemotiveSource, RemoteOKSource, WWRSource, HimalayasSource, JobicySource, ArbeitnowSource, WorkingNomadsSource,
    HNWhosHiringSource, MuseSource, HasjobSource, FourDayWeekSource, RSSFeedsSource, HNJobsSource,
    GreenhouseSource, LeverSource, AshbySource, WorkableSource, SmartRecruitersSource,
    AdzunaSource, JoobleSource, CareerjetSource, GmailAlertsSource)}

_run_lock = threading.Lock()


def load_sources() -> dict[str, Source]:
    cfg = load_sources_config()
    defaults = cfg.get("defaults", {})
    out: dict[str, Source] = {}
    for name, scfg in (cfg.get("sources") or {}).items():
        typ = (scfg or {}).get("type", name)
        cls = TYPES.get(typ)
        if cls is None:
            log.warning("Unknown source type '%s' for '%s' - skipped", typ, name)
            continue
        try:
            out[name] = cls(name, scfg, defaults)
        except Exception as exc:  # bad config must not take the app down
            log.warning("Source '%s' failed to initialise: %s", name, type(exc).__name__)
    return out


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _update_health(name: str, result: HealthResult, *, run: bool = False, success: bool | None = None,
                   fetched: int = 0) -> None:
    with SessionLocal() as db:
        h = db.get(SourceHealth, name) or SourceHealth(source=name)
        now = utcnow()
        h.status, h.message = result.status, result.message[:500]
        if result.details:
            h.details = result.details
        h.last_check_at = now
        if run:
            h.last_run_at = now
            h.last_fetch_count = fetched
            if success:
                h.last_success_at = now
                h.consecutive_failures = 0
            elif success is False:
                h.consecutive_failures = (h.consecutive_failures or 0) + 1
        elif result.status in ("down", "degraded"):
            h.consecutive_failures = (h.consecutive_failures or 0) + 1
        elif result.status == "ok":
            h.consecutive_failures = 0
        db.merge(h)
        db.commit()


def check_health(name: str, src: Source) -> HealthResult:
    try:
        result = src.health_check()
    except BudgetExceeded as exc:
        result = HealthResult("budget_exhausted", str(exc))
    except (SourceError, Exception) as exc:  # never crash on health checks
        result = HealthResult("down", f"{type(exc).__name__}: {str(exc)[:200]}")
        log.warning("Health check failed for %s: %s", name, result.message)
    finally:
        src.http.close()
    _update_health(name, result)
    return result


def check_all_health() -> dict[str, dict[str, str]]:
    return {name: {"status": r.status, "message": r.message}
            for name, src in load_sources().items() for r in [check_health(name, src)]}


def _due(name: str, src: Source) -> tuple[bool, str]:
    hours = src.limits.get("min_hours_between_runs")
    if not hours:
        return True, ""
    with SessionLocal() as db:
        h = db.get(SourceHealth, name)
        last = _aware(h.last_run_at) if h else None
    if last and utcnow() - last < timedelta(hours=float(hours)):
        return False, f"ran {int((utcnow() - last).total_seconds() // 60)} min ago (min interval {hours}h)"
    return True, ""


def run_source(name: str, src: Source, *, force: bool = False) -> dict[str, Any]:
    """Fetch one source and push its jobs through the pipeline. Never raises."""
    from ..pipeline.run import process

    if not src.enabled:
        return {"source": name, "status": "disabled"}
    ok, why = src.configured()
    if not ok:
        _update_health(name, HealthResult("unconfigured", why))
        return {"source": name, "status": "unconfigured", "message": why}
    due, why = _due(name, src)
    if not due and not force:
        return {"source": name, "status": "skipped", "message": why}

    queries = load_profile().get("search", {}).get("queries") or ["python developer"]
    with SessionLocal() as db:
        run = SourceRun(source=name)
        db.add(run)
        db.commit()
        run_id = run.id
    status, message, fetched, stats = "ok", "", 0, {}
    try:
        raws = src.fetch(queries)[: src.max_jobs]
        fetched = len(raws)
        with SessionLocal() as db:
            stats = process(db, raws)
        details = src.health_details() if hasattr(src, "health_details") else {}
        _update_health(name, HealthResult("ok", f"Fetched {fetched} jobs ({stats.get('new', 0)} new)", details),
                       run=True, success=True, fetched=fetched)
    except BudgetExceeded as exc:
        status, message = "budget_exhausted", str(exc)
        _update_health(name, HealthResult("budget_exhausted", message), run=False)
    except NotConfigured as exc:
        status, message = "unconfigured", str(exc)
        _update_health(name, HealthResult("unconfigured", message))
    except Exception as exc:  # any connector bug is contained here
        status, message = "error", f"{type(exc).__name__}: {str(exc)[:200]}"
        log.warning("Source %s failed: %s", name, message)
        details = src.health_details() if hasattr(src, "health_details") else {}
        _update_health(name, HealthResult("degraded", message, details), run=True, success=False)
    finally:
        src.http.close()
    with SessionLocal() as db:
        run = db.get(SourceRun, run_id)
        run.finished_at = utcnow()
        run.fetched, run.new = fetched, int(stats.get("new", 0))
        run.status, run.error = status, message[:500]
        db.commit()
    log.info("Source %s: %s fetched=%d new=%d", name, status, fetched, stats.get("new", 0))
    return {"source": name, "status": status, "message": message, "fetched": fetched, **stats}


def run_all(force: bool = False, only: list[str] | None = None) -> list[dict[str, Any]]:
    if not _run_lock.acquire(blocking=False):
        return [{"status": "busy", "message": "A search run is already in progress"}]
    try:
        results = []
        for name, src in load_sources().items():
            if only and name not in only:
                src.http.close()
                continue
            results.append(run_source(name, src, force=force))
        return results
    finally:
        _run_lock.release()


def is_running() -> bool:
    return _run_lock.locked()
