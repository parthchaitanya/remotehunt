"""Duplicate detection across sources; the direct ATS link wins."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .normalize import NormJob

DIRECT_ATS = re.compile(
    r"(boards\.greenhouse\.io|job-boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com|apply\.workable\.com|"
    r"jobs\.smartrecruiters\.com|\.recruitee\.com|\.bamboohr\.com|\.breezy\.hr|\.teamtailor\.com|\.personio\.|"
    r"jobs\.jobvite\.com|\.myworkdayjobs\.com|\.icims\.com|\.freshteam\.com|\.zohorecruit\.|\.darwinbox\.in|"
    r"\.keka\.com/careers|careers\.[\w-]+\.\w+|/careers?/)", re.I)
ATS_SOURCES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}


def is_direct(url: str) -> bool:
    return bool(url and DIRECT_ATS.search(url))


def link_rank(job: NormJob) -> int:
    """Higher is better: official ATS source > direct ATS link > aggregator."""
    if job.source in ATS_SOURCES:
        return 3
    if is_direct(job.apply_url) or is_direct(job.url):
        return 2
    if job.apply_url and urlsplit(job.apply_url).netloc and "remoteok" not in job.apply_url:
        return 1
    return 0


def choose(a: NormJob, b: NormJob) -> tuple[NormJob, NormJob]:
    """Return (primary, secondary)."""
    ra, rb = link_rank(a), link_rank(b)
    if ra != rb:
        return (a, b) if ra > rb else (b, a)
    # Prefer the richer description
    return (a, b) if len(a.description) >= len(b.description) else (b, a)


def dedupe_batch(jobs: list[NormJob]) -> tuple[list[NormJob], dict[str, list[dict[str, str]]]]:
    """Collapse duplicates inside one batch. Returns (unique jobs, fingerprint -> other sightings)."""
    best: dict[str, NormJob] = {}
    seen: dict[str, list[dict[str, str]]] = {}
    for j in jobs:
        cur = best.get(j.fingerprint)
        if cur is None:
            best[j.fingerprint] = j
            continue
        primary, secondary = choose(cur, j)
        best[j.fingerprint] = primary
        seen.setdefault(j.fingerprint, []).append({"source": secondary.source, "url": secondary.url})
    return list(best.values()), seen
