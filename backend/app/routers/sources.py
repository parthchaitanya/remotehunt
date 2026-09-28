from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_target_companies
from ..db import get_db
from ..models import SourceHealth, SourceRun
from ..sources import registry
from ..sources.base import Budget

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _iso(dt):
    return dt.isoformat() if dt else None


@router.get("")
def list_sources(db: Session = Depends(get_db)):
    out = []
    sources = registry.load_sources()
    for name, src in sources.items():
        h = db.get(SourceHealth, name)
        configured, why = src.configured()
        runs = list(db.scalars(select(SourceRun).where(SourceRun.source == name)
                               .order_by(SourceRun.started_at.desc()).limit(5)))
        out.append({
            "name": name, "type": src.type_name, "enabled": src.enabled, "configured": configured,
            "config_message": why, "active_health": src.active_health, "limits": src.limits,
            "usage": Budget(name, src.limits).usage(), "remaining": src.http.budget.remaining(),
            "status": (h.status if h else ("disabled" if not src.enabled else "unknown")),
            "message": h.message if h else "", "details": h.details if h else {},
            "last_check_at": _iso(h.last_check_at) if h else None, "last_run_at": _iso(h.last_run_at) if h else None,
            "last_success_at": _iso(h.last_success_at) if h else None,
            "consecutive_failures": h.consecutive_failures if h else 0,
            "last_fetch_count": h.last_fetch_count if h else 0,
            "backoff_until": _iso(h.backoff_until) if h else None,
            "recent_runs": [{"started_at": _iso(r.started_at), "status": r.status, "fetched": r.fetched, "new": r.new,
                             "error": r.error} for r in runs],
        })
        src.http.close()
    return {"sources": out, "target_companies": load_target_companies(), "running": registry.is_running()}


@router.post("/health-check")
def health_check():
    return registry.check_all_health()


@router.post("/{name}/health-check")
def health_check_one(name: str):
    src = registry.load_sources().get(name)
    if src is None:
        return {"status": "unknown", "message": "No such source"}
    r = registry.check_health(name, src)
    return {"status": r.status, "message": r.message}
