"""RawJob -> normalized dict ready for storage."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..sources.base import RawJob
from ..textutil import canonical_url, html_to_text

_COMPANY_SUFFIX = re.compile(
    r"\b(inc|llc|ltd|limited|gmbh|pvt|private|corp|corporation|co|plc|s\.?a\.?|b\.?v\.?|ag|technologies|"
    r"technology|labs|solutions|software|group|holdings|india)\b\.?", re.I)
_TITLE_NOISE = re.compile(r"\s*[\(\[]\s*(remote|hybrid|on-?site|wfh|work from home|[a-z ,/]+only)[^)\]]*[\)\]]\s*",
                          re.I)


@dataclass
class NormJob:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    remote_type: str
    regions: list[str]
    tz_restrictions: list[float]
    description: str
    url: str
    apply_url: str
    salary_min: float | None
    salary_max: float | None
    salary_currency: str
    salary_text: str
    employment_type: str
    tags: list[str]
    posted_at: datetime | None
    fingerprint: str
    extra: dict[str, Any] = field(default_factory=dict)


def norm_company(name: str) -> str:
    n = (name or "").lower().replace("&", " and ")
    n = _COMPANY_SUFFIX.sub(" ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


def norm_title(title: str) -> str:
    t = _TITLE_NOISE.sub(" ", title or "").lower()
    t = re.sub(r"\bsr\.?\b", "senior", t)
    t = re.sub(r"\bjr\.?\b", "junior", t)
    t = re.sub(r"\s[-–|/]\s*(remote|hybrid|india|anywhere|worldwide|global|emea|apac|us|usa|uk|eu)\b.*$", "", t)
    t = re.sub(r"[^a-z0-9+#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fingerprint(company: str, title: str, url: str) -> str:
    c, t = norm_company(company), norm_title(title)
    key = f"{c}|{t}" if c and t else f"url|{canonical_url(url)}"
    return hashlib.sha1(key.encode()).hexdigest()


def _remote_type(raw: RawJob, text: str) -> str:
    blob = f"{raw.title} {raw.location} {raw.employment_type} {' '.join(raw.tags)}".lower()
    if re.search(r"\bhybrid\b", blob):
        return "hybrid"
    if raw.remote is True or re.search(r"\b(remote|work from home|wfh|anywhere|distributed)\b", blob):
        return "remote"
    if raw.remote is False or re.search(r"\b(on-?site|in-?office)\b", blob):
        return "onsite"
    head = text[:4000]
    if re.search(r"\b(fully remote|100% remote|remote-first|remote first|work from anywhere)\b", head, re.I):
        return "remote"
    if re.search(r"\b(hybrid|\d\s*days? (a|per) week (in|at|from) (the )?office|work from office \d|flexible "
                 r"hybrid)\b", head, re.I):
        return "hybrid"
    if re.search(r"\b(work from office|wfo|on-?site role|onsite position|office[- ]based|in[- ]person)\b", head, re.I):
        return "onsite"
    return "unknown"


def normalize(raw: RawJob) -> NormJob | None:
    title = " ".join(html_to_text(raw.title).split())
    if not title or not (raw.url or raw.apply_url):
        return None
    description = html_to_text(raw.description)
    company = " ".join((raw.company or "").split())[:200]
    url = canonical_url(raw.url or raw.apply_url)
    apply_url = canonical_url(raw.apply_url or raw.url)
    regions = [r.strip() for r in raw.region_restrictions if r and r.strip()]
    salary_text = raw.salary_text or ""
    if not salary_text and (raw.salary_min or raw.salary_max):
        lo = f"{raw.salary_min:,.0f}" if raw.salary_min else "?"
        hi = f"{raw.salary_max:,.0f}" if raw.salary_max else "?"
        salary_text = f"{raw.salary_currency} {lo}–{hi}".strip()
    return NormJob(
        source=raw.source, external_id=str(raw.external_id)[:200], title=title[:300], company=company,
        location=(raw.location or "")[:300], remote_type=_remote_type(raw, description), regions=regions[:20],
        tz_restrictions=list(raw.timezone_restrictions or []), description=description[:20000], url=url,
        apply_url=apply_url, salary_min=raw.salary_min, salary_max=raw.salary_max,
        salary_currency=raw.salary_currency or "", salary_text=salary_text[:200],
        employment_type=(raw.employment_type or "")[:50], tags=[t for t in raw.tags if t][:20],
        posted_at=raw.posted_at, fingerprint=fingerprint(company, title, url), extra=raw.extra or {},
    )
