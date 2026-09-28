"""Parsers for job-alert emails you receive (LinkedIn, Naukri, Indeed, foundit, Instahyre, Wellfound).

These read your own mailbox through the Gmail API - no website is scraped.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from bs4 import BeautifulSoup

from ..textutil import canonical_url

JOB_LINK: dict[str, re.Pattern[str]] = {
    "linkedin": re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", re.I),
    "naukri": re.compile(r"naukri\.com/(?:job-listings-[\w-]+?-(\d{6,})|.*?[?&]jobid=(\w+))", re.I),
    "indeed": re.compile(r"indeed\.(?:com|co\.in)/(?:rc/clk|viewjob|m/viewjob|pagead/clk|applystart)[^\s\"'<>]*?"
                         r"[?&](?:jk|vjk)=([0-9a-f]+)", re.I),
    "foundit": re.compile(r"foundit\.in/(?:job/[\w-]+-(\d{5,})|seeker/job-details\?[^\s\"'<>]*?id=(\d+))", re.I),
    "instahyre": re.compile(r"instahyre\.com/(?:job-(\d+)|jobs?/[^\s\"'<>]*?(\d{3,}))", re.I),
    "wellfound": re.compile(r"(?:wellfound\.com|angel\.co)/(?:jobs|company/[\w-]+/jobs)/(\d+)", re.I),
    "internshala": re.compile(r"internshala\.com/(?:internship|job|jobs)/detail/([\w-]+)", re.I),
    "cutshort": re.compile(r"cutshort\.io/job/([\w-]+)", re.I),
    "glassdoor": re.compile(r"glassdoor\.(?:com|co\.in)/(?:job-listing/[^\s\"'<>?]*|partner/jobListing\.htm)"
                            r"[^\s\"'<>]*?[?&](?:jl|jobListingId)=(\d+)", re.I),
    "hirist": re.compile(r"hirist\.(?:com|tech)/j/([\w-]+)", re.I),
}
NOISE_TEXT = re.compile(r"^(view( job| all| more| details)?|apply( now)?|easy apply|see (all|more) jobs?|"
                        r"unsubscribe|manage (alerts|settings)|search( for)? jobs|learn more|help|privacy|"
                        r"see jobs|jobs? you may be interested in|save|share|\d+ (new )?jobs?.*)$", re.I)
REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|anywhere)\b", re.I)


def _unwrap(href: str) -> str:
    """Follow common click-tracking wrappers to the real URL (without making requests)."""
    h = unquote(href or "")
    try:
        qs = parse_qs(urlsplit(h).query)
    except ValueError:
        return h
    for key in ("url", "u", "redirect", "dest", "target", "q"):
        for v in qs.get(key, []):
            if v.startswith("http"):
                return unquote(v)
    return h


def _job_id(platform: str, url: str) -> str | None:
    m = JOB_LINK[platform].search(url)
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def _split_meta(line: str) -> tuple[str, str]:
    """'Acme Corp · Bengaluru (Remote)' -> ('Acme Corp', 'Bengaluru (Remote)')"""
    for sep in (" · ", " • ", " | ", " - ", " – "):
        if sep in line:
            a, b = line.split(sep, 1)
            return a.strip(), b.strip()
    return line.strip(), ""


def parse_alert_html(platform: str, html: str, text: str = "") -> list[dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    if html:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            url = _unwrap(a["href"])
            jid = _job_id(platform, url)
            if not jid:
                continue
            label = " ".join(a.get_text(" ").split())
            entry = jobs.setdefault(jid, {"id": jid, "url": url, "title": "", "company": "", "location": ""})
            if label and not NOISE_TEXT.match(label) and len(label) > len(entry["title"]) and len(label) < 150:
                entry["title"] = label
                entry["_anchor"] = a
        for entry in jobs.values():
            a = entry.pop("_anchor", None)
            if a is None or not entry["title"]:
                continue
            container = a
            for _ in range(5):  # climb to the job "card"
                if container.parent is None:
                    break
                container = container.parent
                if len(list(container.stripped_strings)) >= 3:
                    break
            lines = [" ".join(s.split()) for s in container.stripped_strings]
            lines = [ln for ln in lines if ln and not NOISE_TEXT.match(ln)]
            try:
                idx = lines.index(entry["title"])
            except ValueError:
                idx = -1
            after = lines[idx + 1: idx + 4] if idx >= 0 else lines[:3]
            if after:
                company, loc = _split_meta(after[0])
                entry["company"] = company[:120]
                entry["location"] = (loc or (after[1] if len(after) > 1 and len(after[1]) < 80 else ""))[:120]
    elif text:
        lines = [ln.strip() for ln in text.splitlines()]
        for i, ln in enumerate(lines):
            for url in re.findall(r"https?://\S+", ln):
                url = _unwrap(url)
                jid = _job_id(platform, url)
                if not jid or jid in jobs:
                    continue
                prev = [p for p in lines[max(0, i - 3):i] if p and not p.startswith("http")]
                title = prev[0] if prev else ""
                company, loc = _split_meta(prev[1]) if len(prev) > 1 else ("", "")
                jobs[jid] = {"id": jid, "url": url, "title": title, "company": company, "location": loc}

    out = []
    for e in jobs.values():
        if not e["title"]:
            continue
        e["url"] = canonical_url(e["url"])
        e["remote"] = bool(REMOTE_RE.search(f"{e['title']} {e['location']}"))
        e["platform"] = platform
        out.append(e)
    return out
