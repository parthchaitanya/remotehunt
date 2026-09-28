"""Source plugin base: budgeted HTTP client, raw job record, health contract."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar

import httpx
from sqlalchemy import func, select

from ..db import SessionLocal
from ..models import ApiCall, SourceHealth, utcnow

log = logging.getLogger(__name__)


class SourceError(Exception):
    """A recoverable problem with a source (bad response, auth, etc.)."""


class BudgetExceeded(SourceError):
    pass


class NotConfigured(SourceError):
    pass


@dataclass
class RawJob:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    apply_url: str = ""
    description: str = ""  # may contain HTML
    location: str = ""
    remote: bool | None = None
    region_restrictions: list[str] = field(default_factory=list)
    timezone_restrictions: list[float] = field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_text: str = ""
    employment_type: str = ""
    tags: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResult:
    status: str  # ok | degraded | down | disabled | unconfigured | budget_exhausted | unknown
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def to_dt(value: Any) -> datetime | None:
    """Parse epoch seconds/ms, ISO-8601 or RFC-822 into an aware datetime."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            v = float(value)
            if v > 1e12:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        s = str(value).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


class Budget:
    """Rolling-window call budgets persisted in the api_calls table."""

    def __init__(self, source: str, limits: dict[str, Any]):
        self.source = source
        self.limits = limits or {}

    def _count(self, since: datetime | None) -> int:
        with SessionLocal() as db:
            q = select(func.count()).select_from(ApiCall).where(ApiCall.source == self.source)
            if since is not None:
                q = q.where(ApiCall.ts >= since)
            return db.scalar(q) or 0

    def usage(self) -> dict[str, Any]:
        now = utcnow()
        return {
            "last_24h": self._count(now - timedelta(days=1)),
            "last_7d": self._count(now - timedelta(days=7)),
            "lifetime": self._count(None),
            "limits": self.limits,
        }

    def remaining(self) -> int | None:
        """Calls still allowed right now (None = unlimited)."""
        now = utcnow()
        rem: list[int] = []
        if (d := self.limits.get("max_calls_per_day")) is not None:
            rem.append(int(d) - self._count(now - timedelta(days=1)))
        if (w := self.limits.get("max_calls_per_week")) is not None:
            rem.append(int(w) - self._count(now - timedelta(days=7)))
        if (lt := self.limits.get("lifetime_budget")) is not None:
            rem.append(int(lt) - self._count(None))
        return max(0, min(rem)) if rem else None

    def check(self) -> None:
        rem = self.remaining()
        if rem is not None and rem <= 0:
            raise BudgetExceeded(f"{self.source}: call budget exhausted")
        with SessionLocal() as db:
            h = db.get(SourceHealth, self.source)
            if h and h.backoff_until and _aware(h.backoff_until) > utcnow():
                raise BudgetExceeded(f"{self.source}: backing off after rate-limit until {h.backoff_until:%H:%M} UTC")

    def record(self, ok: bool, status: int | None, purpose: str) -> None:
        with SessionLocal() as db:
            db.add(ApiCall(source=self.source, ok=ok, status_code=status, purpose=purpose))
            db.commit()

    def set_backoff(self, seconds: float) -> None:
        with SessionLocal() as db:
            h = db.get(SourceHealth, self.source) or SourceHealth(source=self.source)
            h.backoff_until = utcnow() + timedelta(seconds=seconds)
            db.merge(h)
            db.commit()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class BudgetedClient:
    """HTTP client that enforces budgets, spacing and 429 back-off for one source."""

    def __init__(self, source: str, limits: dict[str, Any], timeout: float, user_agent: str):
        self.budget = Budget(source, limits)
        self.source = source
        self.spacing = float(limits.get("min_seconds_between_calls", 1.0))
        self._last = 0.0
        self._client = httpx.Client(timeout=timeout, follow_redirects=True,
                                    headers={"User-Agent": user_agent, "Accept": "application/json, */*"})
        self.purpose = "fetch"

    def close(self) -> None:
        self._client.close()

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        self.budget.check()
        wait = self.spacing - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        try:
            resp = self._client.request(method, url, **kw)
        except httpx.HTTPError as exc:
            self.budget.record(False, None, self.purpose)
            raise SourceError(f"network error: {type(exc).__name__}") from None
        self.budget.record(resp.status_code < 400, resp.status_code, self.purpose)
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "3600")
            seconds = float(retry) if retry.replace(".", "", 1).isdigit() else 3600.0
            self.budget.set_backoff(max(seconds, 60))
            raise SourceError(f"rate limited (429); backing off {int(max(seconds, 60))}s")
        if resp.status_code >= 400:
            raise SourceError(f"HTTP {resp.status_code}")
        return resp

    def get_json(self, url: str, **kw) -> Any:
        resp = self.request("GET", url, **kw)
        try:
            return resp.json()
        except ValueError:
            raise SourceError("invalid JSON response") from None

    def get_text(self, url: str, **kw) -> str:
        return self.request("GET", url, **kw).text

    def post_json(self, url: str, payload: dict[str, Any], **kw) -> Any:
        resp = self.request("POST", url, json=payload, **kw)
        try:
            return resp.json()
        except ValueError:
            raise SourceError("invalid JSON response") from None


class Source:
    """Base class for a job source plugin.

    Subclasses implement `fetch(queries)` and optionally `ping()` (cheap health request)
    and `configured()` (API keys present).
    """

    type_name: ClassVar[str] = ""
    requires_keys: ClassVar[tuple[str, ...]] = ()

    def __init__(self, name: str, cfg: dict[str, Any], defaults: dict[str, Any]):
        self.name = name
        self.cfg = cfg or {}
        self.params: dict[str, Any] = self.cfg.get("params", {}) or {}
        self.limits: dict[str, Any] = self.cfg.get("limits", {}) or {}
        self.enabled: bool = bool(self.cfg.get("enabled", True))
        self.active_health: bool = bool(self.cfg.get("active_health", False))
        self.max_jobs = int(defaults.get("max_jobs_per_run", 5000))
        self.http = BudgetedClient(name, self.limits, float(defaults.get("timeout_seconds", 25)),
                                   defaults.get("user_agent", "RemoteHunt/1.0"))

    # -- configuration --------------------------------------------------------
    def configured(self) -> tuple[bool, str]:
        from ..config import get_settings

        s = get_settings()
        missing = [k.upper() for k in self.requires_keys if not getattr(s, k, "")]
        if missing:
            return False, "missing " + ", ".join(missing)
        return True, ""

    # -- contract ---------------------------------------------------------------
    def fetch(self, queries: list[str]) -> list[RawJob]:
        raise NotImplementedError

    def ping(self) -> HealthResult:
        """Cheap live request. Default: fetch() is too expensive, so callers use passive health."""
        raise NotImplementedError

    def health_check(self) -> HealthResult:
        if not self.enabled:
            return HealthResult("disabled", "Disabled in config/sources.yaml")
        ok, why = self.configured()
        if not ok:
            return HealthResult("unconfigured", why)
        rem = self.http.budget.remaining()
        if rem is not None and rem <= 0:
            return HealthResult("budget_exhausted", "Call budget used up for the current window")
        if self.active_health:
            self.http.purpose = "health"
            try:
                return self.ping()
            except NotImplementedError:
                pass
            finally:
                self.http.purpose = "fetch"
        return self.passive_health()

    def passive_health(self) -> HealthResult:
        with SessionLocal() as db:
            h = db.get(SourceHealth, self.name)
        if h is None or h.last_run_at is None:
            return HealthResult("unknown", "Not run yet (health is derived from runs to save API budget)")
        if h.consecutive_failures >= 3:
            return HealthResult("down", f"Last {h.consecutive_failures} runs failed")
        if h.consecutive_failures > 0:
            return HealthResult("degraded", "Last run failed")
        return HealthResult("ok", f"Last run fetched {h.last_fetch_count} jobs")
