"""Remote job boards with public APIs / RSS feeds (no keys required)."""
from __future__ import annotations

import re
from urllib.parse import quote_plus

import feedparser

from ..textutil import html_to_text
from .base import HealthResult, RawJob, Source, SourceError, to_dt


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


class RemotiveSource(Source):
    """https://remotive.com/api/remote-jobs - max 4 calls/day (one per scheduled run)."""

    type_name = "remotive"
    URL = "https://remotive.com/api/remote-jobs"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        data = self.http.get_json(self.URL, params={"limit": int(self.params.get("limit", 300))})
        out = []
        for j in data.get("jobs", []) if isinstance(data, dict) else []:
            loc = j.get("candidate_required_location") or ""
            out.append(RawJob(
                source=self.name, external_id=str(j.get("id", "")), title=j.get("title", ""),
                company=j.get("company_name", ""), url=j.get("url", ""), apply_url=j.get("url", ""),
                description=j.get("description", ""), location=loc, remote=True,
                region_restrictions=[p.strip() for p in re.split(r"[,;/]", loc) if p.strip()],
                salary_text=j.get("salary") or "", employment_type=j.get("job_type") or "",
                tags=list(j.get("tags") or []) + ([j["category"]] if j.get("category") else []),
                posted_at=to_dt(j.get("publication_date")),
            ))
        return out


class RemoteOKSource(Source):
    """https://remoteok.com/api - attribution: jobs link back to Remote OK."""

    type_name = "remoteok"
    URL = "https://remoteok.com/api"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        data = self.http.get_json(self.URL)
        out = []
        for j in data if isinstance(data, list) else []:
            if not isinstance(j, dict) or not j.get("id") or not j.get("position"):
                continue  # first element is the legal notice
            loc = j.get("location") or ""
            out.append(RawJob(
                source=self.name, external_id=str(j["id"]), title=j.get("position", ""),
                company=j.get("company", ""), url=j.get("url", ""), apply_url=j.get("apply_url") or j.get("url", ""),
                description=j.get("description", ""), location=loc, remote=True,
                region_restrictions=[p.strip() for p in re.split(r"[,;/]", loc) if p.strip()],
                salary_min=_num(j.get("salary_min")), salary_max=_num(j.get("salary_max")),
                salary_currency="USD" if _num(j.get("salary_min")) else "",
                tags=list(j.get("tags") or []), posted_at=to_dt(j.get("epoch") or j.get("date")),
            ))
        return out


class WWRSource(Source):
    """We Work Remotely category RSS feeds."""

    type_name = "wwr_rss"

    def _feeds(self) -> list[str]:
        return self.params.get("feeds") or ["https://weworkremotely.com/remote-jobs.rss"]

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        errors = []
        for feed_url in self._feeds():
            try:
                text = self.http.get_text(feed_url)
            except SourceError as exc:
                errors.append(str(exc))
                continue
            feed = feedparser.parse(text)
            for e in feed.entries:
                raw_title = e.get("title", "")
                company, _, title = raw_title.partition(":")
                if not title:
                    company, title = "", raw_title
                region = e.get("region", "") or ""
                out.append(RawJob(
                    source=self.name, external_id=e.get("id") or e.get("link", ""), title=title.strip(),
                    company=company.strip(), url=e.get("link", ""), apply_url=e.get("link", ""),
                    description=e.get("summary", "") or e.get("description", ""),
                    location=region or e.get("country", "") or "", remote=True,
                    region_restrictions=[p.strip() for p in re.split(r"[,;/]", region) if p.strip()],
                    employment_type=e.get("type", "") or "",
                    tags=[t.get("term") for t in e.get("tags", []) if t.get("term")],
                    posted_at=to_dt(e.get("published")),
                ))
        if errors and not out:
            raise SourceError("; ".join(errors))
        return out

    def ping(self) -> HealthResult:
        text = self.http.get_text(self._feeds()[0])
        feed = feedparser.parse(text)
        if feed.bozo and not feed.entries:
            return HealthResult("degraded", "Feed returned but could not be parsed")
        return HealthResult("ok", f"Feed reachable ({len(feed.entries)} items)")


class HimalayasSource(Source):
    """https://himalayas.app/jobs/api/search - includes timezone/location restrictions."""

    type_name = "himalayas"
    URL = "https://himalayas.app/jobs/api/search"

    def _to_raw(self, j: dict) -> RawJob:
        locs = j.get("locationRestrictions") or []
        tzs = [float(t) for t in (j.get("timezoneRestrictions") or []) if isinstance(t, (int, float))]
        link = j.get("applicationLink") or j.get("guid") or ""
        return RawJob(
            source=self.name, external_id=j.get("guid") or link, title=j.get("title", ""),
            company=j.get("companyName", ""), url=j.get("guid") or link, apply_url=link,
            description=j.get("description") or j.get("excerpt") or "",
            location=", ".join(locs) if locs else "Worldwide", remote=True,
            region_restrictions=list(locs) if locs else ["Worldwide"], timezone_restrictions=tzs,
            salary_min=_num(j.get("minSalary")), salary_max=_num(j.get("maxSalary")),
            salary_currency=j.get("currency") or "", employment_type=j.get("employmentType") or "",
            tags=list(j.get("categories") or []) + list(j.get("seniority") or []), posted_at=to_dt(j.get("pubDate")),
        )

    FEED = "https://himalayas.app/jobs/api"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        limit = int(self.params.get("per_query_limit", 20))
        for q in queries:
            try:
                data = self.http.get_json(self.URL, params={"q": q, "limit": limit})
            except SourceError as exc:
                if "HTTP 404" not in str(exc):
                    raise
                # The search endpoint is sometimes served as a cached 404; use the documented feed instead.
                return out + self._feed()
            out += [self._to_raw(j) for j in (data.get("jobs") or [])]
        return out

    def _feed(self) -> list[RawJob]:
        """Newest jobs via cursor pagination (max 20 per page)."""
        out: list[RawJob] = []
        cursor = None
        for _ in range(int(self.params.get("feed_pages", 5))):
            params = {"limit": 20, **({"cursor": cursor} if cursor else {})}
            data = self.http.get_json(self.FEED, params=params)
            out += [self._to_raw(j) for j in (data.get("jobs") or [])]
            cursor = data.get("nextCursor")
            if not cursor:
                break
        return out

    def ping(self) -> HealthResult:
        data = self.http.get_json(self.FEED, params={"limit": 1})
        return HealthResult("ok", "API reachable") if "jobs" in data else HealthResult("degraded", "Unexpected shape")


class JobicySource(Source):
    """https://jobicy.com/api/v2/remote-jobs - credit Jobicy; apply buttons go to the original URL."""

    type_name = "jobicy"
    URL = "https://jobicy.com/api/v2/remote-jobs"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        for tag in self.params.get("tags") or ["python"]:
            data = self.http.get_json(self.URL, params={"count": int(self.params.get("count", 50)), "tag": tag})
            for j in data.get("jobs") or []:
                geo = j.get("jobGeo") or ""
                out.append(RawJob(
                    source=self.name, external_id=str(j.get("id", "")), title=html_to_text(j.get("jobTitle", "")),
                    company=j.get("companyName", ""), url=j.get("url", ""), apply_url=j.get("url", ""),
                    description=j.get("jobDescription") or j.get("jobExcerpt") or "", location=geo, remote=True,
                    region_restrictions=[p.strip() for p in geo.split(",") if p.strip()],
                    salary_min=_num(j.get("annualSalaryMin")), salary_max=_num(j.get("annualSalaryMax")),
                    salary_currency=j.get("salaryCurrency") or "",
                    employment_type=", ".join(j.get("jobType") or []),
                    tags=list(j.get("jobIndustry") or []) + ([j["jobLevel"]] if j.get("jobLevel") else []),
                    posted_at=to_dt(j.get("pubDate")),
                ))
        return out


class ArbeitnowSource(Source):
    """https://www.arbeitnow.com/api/job-board-api"""

    type_name = "arbeitnow"
    URL = "https://www.arbeitnow.com/api/job-board-api"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        for page in range(1, int(self.params.get("pages", 2)) + 1):
            data = self.http.get_json(self.URL, params={"page": page})
            for j in data.get("data") or []:
                out.append(RawJob(
                    source=self.name, external_id=j.get("slug", ""), title=j.get("title", ""),
                    company=j.get("company_name", ""), url=j.get("url", ""), apply_url=j.get("url", ""),
                    description=j.get("description", ""), location=j.get("location") or "",
                    remote=bool(j.get("remote")), employment_type=", ".join(j.get("job_types") or []),
                    tags=list(j.get("tags") or []), posted_at=to_dt(j.get("created_at")),
                ))
            if not (data.get("links") or {}).get("next"):
                break
        return out

    def ping(self) -> HealthResult:
        data = self.http.get_json(self.URL, params={"page": 1})
        return HealthResult("ok", f"API reachable ({len(data.get('data') or [])} jobs on page 1)")


class WorkingNomadsSource(Source):
    """https://www.workingnomads.com/api/exposed_jobs/"""

    type_name = "workingnomads"
    URL = "https://www.workingnomads.com/api/exposed_jobs/"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        data = self.http.get_json(self.URL)
        out = []
        for j in data if isinstance(data, list) else []:
            loc = j.get("location") or ""
            out.append(RawJob(
                source=self.name, external_id=j.get("url", ""), title=j.get("title", ""),
                company=j.get("company_name", ""), url=j.get("url", ""), apply_url=j.get("url", ""),
                description=j.get("description", ""), location=loc, remote=True,
                region_restrictions=[p.strip() for p in re.split(r"[,;/]", loc) if p.strip() and p.strip() != "Remote"],
                tags=[t.strip() for t in (j.get("tags") or "").split(",") if t.strip()]
                + ([j["category_name"]] if j.get("category_name") else []),
                posted_at=to_dt(j.get("pub_date")),
            ))
        return out


class HNWhosHiringSource(Source):
    """Latest 'Ask HN: Who is hiring?' thread via the official Algolia HN API."""

    type_name = "hn_algolia"
    SEARCH = "https://hn.algolia.com/api/v1/search_by_date"

    def _latest_story(self) -> dict:
        data = self.http.get_json(self.SEARCH, params={"tags": "story,author_whoishiring", "hitsPerPage": 10})
        for h in data.get("hits") or []:
            if "who is hiring" in (h.get("title") or "").lower():
                return h
        raise SourceError("could not find the latest Who is hiring thread")

    def fetch(self, queries: list[str]) -> list[RawJob]:
        story = self._latest_story()
        sid = story["objectID"]
        max_comments = int(self.params.get("max_comments", 1000))
        remote_only = bool(self.params.get("remote_only", True))
        out: list[RawJob] = []
        page, fetched = 0, 0
        while fetched < max_comments:
            data = self.http.get_json("https://hn.algolia.com/api/v1/search",
                                      params={"tags": f"comment,story_{sid}", "hitsPerPage": 500, "page": page})
            hits = data.get("hits") or []
            for h in hits:
                fetched += 1
                if str(h.get("parent_id")) != str(sid):
                    continue  # top-level comments only
                job = self._parse_comment(h, sid)
                if job and (not remote_only or job.remote):
                    out.append(job)
            page += 1
            if page >= int(data.get("nbPages") or 0) or not hits:
                break
        return out

    @staticmethod
    def _parse_comment(h: dict, story_id: str) -> RawJob | None:
        text = html_to_text(h.get("comment_text") or "")
        if not text:
            return None
        first = text.split("\n", 1)[0]
        parts = [p.strip() for p in re.split(r"\s[|•]\s|\s\|\s?", first) if p.strip()]
        if len(parts) < 2:
            return None
        is_url = re.compile(r"^(https?://|www\.)|\.(com|io|ai|co|dev|org|net|app)(/|$)", re.I)
        loc_word = re.compile(r"^(remote|onsite|on-site|hybrid|full[- ]?time|part[- ]?time|contract|intern(ship)?|"
                              r"visa|\$|€|£|\d)", re.I)
        company = re.sub(r"\s*\(.*?\)\s*$", "", parts[0])
        company = re.sub(r"^https?://(www\.)?", "", company).rstrip("/")[:120]
        candidates = [p for p in parts[1:] if not is_url.search(p) and not loc_word.match(p) and len(p) < 160]
        role_part = next((p for p in candidates if re.search(
            r"engineer|developer|scientist|analyst|intern|\bml\b|\bai\b|data|python|backend|full.?stack|devops|sre",
            p, re.I)), candidates[0] if candidates else "")
        if not role_part:
            return None
        location = next((p for p in parts[1:] if p != role_part and (
            re.search(r"\b(remote|onsite|on-site|hybrid|worldwide|anywhere|london|berlin|new york|nyc|bay area|"
                      r"san francisco|india|europe|emea|apac|us|usa|uk|canada)\b", p, re.I)
            or re.search(r"[A-Z][a-z]+,\s?[A-Z]{2}\b", p))), "")
        remote = bool(re.search(r"\bremote\b", first, re.I))
        links = re.findall(r"https?://[^\s)\"'<>]+", h.get("comment_text") or "")
        link = next((l for l in links if "news.ycombinator.com" not in l), "")
        return RawJob(
            source="hn_whos_hiring", external_id=str(h.get("objectID")), title=role_part[:200], company=company,
            url=f"https://news.ycombinator.com/item?id={h.get('objectID')}", apply_url=link, description=text,
            location=location or ("Remote" if remote else ""), remote=remote,
            region_restrictions=[location] if location else [], posted_at=to_dt(h.get("created_at")),
            extra={"story_id": story_id},
        )

    def ping(self) -> HealthResult:
        story = self._latest_story()
        return HealthResult("ok", f"Found thread: {story.get('title')}")


# ----------------------------------------------------------------------------- additional boards
class MuseSource(Source):
    """The Muse public jobs API (https://www.themuse.com/developers/api/v2). Covers remote + Indian city jobs."""

    type_name = "themuse"
    URL = "https://www.themuse.com/api/public/jobs"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        cats = self.params.get("categories") or ["Software Engineering", "Data and Analytics", "Data Science"]
        levels = self.params.get("levels") or ["Entry Level", "Internship", "Mid Level"]
        out: list[RawJob] = []
        for loc_group in self.params.get("location_groups") or [["Flexible / Remote"]]:
            for page in range(int(self.params.get("pages", 2))):
                params = [("page", page)] + [("category", c) for c in cats] + [("level", lv) for lv in levels] + \
                    [("location", loc) for loc in loc_group]
                data = self.http.get_json(self.URL, params=params)
                for j in data.get("results") or []:
                    locs = [x.get("name", "") for x in j.get("locations") or [] if x.get("name")]
                    remote = any("remote" in l.lower() or "flexible" in l.lower() for l in locs)
                    url = (j.get("refs") or {}).get("landing_page", "")
                    out.append(RawJob(
                        source=self.name, external_id=str(j.get("id", "")), title=j.get("name", ""),
                        company=(j.get("company") or {}).get("name", ""), url=url, apply_url=url,
                        description=j.get("contents", ""), location=", ".join(locs),
                        remote=True if remote else None,
                        region_restrictions=[l for l in locs if "flexible" not in l.lower()] or ["Remote"],
                        employment_type=j.get("type") or "",
                        tags=[c.get("name", "") for c in j.get("categories") or []]
                        + [lv.get("name", "") for lv in j.get("levels") or []],
                        posted_at=to_dt(j.get("publication_date")),
                    ))
                if page + 1 >= int(data.get("page_count") or 0):
                    break
        return out

    def ping(self) -> HealthResult:
        data = self.http.get_json(self.URL, params={"page": 0, "location": "Flexible / Remote"})
        return HealthResult("ok", f"API reachable ({data.get('total', 0)} remote jobs)")


class HasjobSource(Source):
    """Hasjob (hasjob.co) Atom feed - Indian startup jobs, many hybrid/on-site."""

    type_name = "hasjob"
    URL = "https://hasjob.co/feed"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        feed = feedparser.parse(self.http.get_text(self.URL))
        out = []
        for e in feed.entries:
            title = e.get("title", "")
            loc = e.get("location", "") or ""
            if loc and title.endswith(f"| {loc}"):
                title = title[: -len(f"| {loc}")].strip()
            parts = e.get("link", "").split("/")
            company = parts[3] if len(parts) > 4 else ""
            desc = (e.get("content") or [{}])[0].get("value", "") or e.get("summary", "")
            out.append(RawJob(
                source=self.name, external_id=e.get("id") or e.get("link", ""), title=title.strip(" |"),
                company=company, url=e.get("link", ""), apply_url=e.get("link", ""), description=desc,
                location=loc, remote=True if re.search(r"\b(anywhere|remote)\b", loc, re.I) else None,
                region_restrictions=[loc] if loc else [], posted_at=to_dt(e.get("published")),
            ))
        return out

    def ping(self) -> HealthResult:
        feed = feedparser.parse(self.http.get_text(self.URL))
        return HealthResult("ok", f"Feed reachable ({len(feed.entries)} items)")


class FourDayWeekSource(Source):
    """4dayweek.io public API - link back to 4dayweek.io (shown as the job source)."""

    type_name = "fourdayweek"
    URL = "https://4dayweek.io/api/v1"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        for page in range(1, int(self.params.get("pages", 3)) + 1):
            data = self.http.get_json(self.URL, params={"page": page})
            for j in data.get("jobs") or []:
                city, country = j.get("location_city") or "", j.get("location_country") or ""
                loc = j.get("location_original") or ", ".join(x for x in (city, country) if x)
                remote = j.get("is_remote")
                out.append(RawJob(
                    source=self.name, external_id=str(j.get("id_str") or j.get("slug", "")), title=j.get("title", ""),
                    company=j.get("company_name", ""), url=j.get("url", ""), apply_url=j.get("url", ""),
                    description=j.get("description", "") or "", location=loc or ("Remote" if remote else ""),
                    remote=True if remote else None, region_restrictions=[x for x in (loc,) if x],
                    tags=[t for t in (j.get("category"), j.get("role"), j.get("level")) if isinstance(t, str) and t],
                    posted_at=to_dt(j.get("posted")),
                ))
            if not data.get("has_more"):
                break
        return out


class RSSFeedsSource(Source):
    """Generic remote-job RSS feeds (e.g. Jobspresso, Real Work From Anywhere).

    params.feeds: list of {url, worldwide: bool}. Titles like "Role at Company" / "Company: Role" are split.
    """

    type_name = "rss_feeds"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        errors = []
        for f in self.params.get("feeds") or []:
            try:
                feed = feedparser.parse(self.http.get_text(f["url"]))
            except SourceError as exc:
                errors.append(str(exc))
                continue
            host = f["url"].split("/")[2].replace("www.", "")
            for e in feed.entries:
                out.append(self.to_raw(e, host, bool(f.get("worldwide"))))
        if errors and not out:
            raise SourceError("; ".join(errors))
        return out

    def to_raw(self, e, host: str, worldwide: bool) -> RawJob:
        title = e.get("title", "")
        author = html_to_text((e.get("author") or "").replace("<br>", "\n"))
        company, _, loc = author.partition("\n")
        loc = loc.replace("⚲", "").strip()
        m = re.match(r"^(.*)\s+at\s+(.+)$", title)
        if m:
            title, company = m.group(1), company or m.group(2)
        elif ":" in title and not company:
            company, title = (s.strip() for s in title.split(":", 1))
        desc = (e.get("content") or [{}])[0].get("value", "") or e.get("summary", "")
        return RawJob(
            source=self.name, external_id=e.get("id") or e.get("link", ""), title=title.strip(),
            company=company.strip(), url=e.get("link", ""), apply_url=e.get("link", ""), description=desc,
            location=loc or ("Worldwide" if worldwide else "Remote"), remote=True,
            region_restrictions=[loc] if loc else (["Worldwide"] if worldwide else []),
            tags=[host], posted_at=to_dt(e.get("published")),
        )

    def ping(self) -> HealthResult:
        feeds = self.params.get("feeds") or []
        if not feeds:
            return HealthResult("unconfigured", "No feeds configured")
        feed = feedparser.parse(self.http.get_text(feeds[0]["url"]))
        return HealthResult("ok", f"Feed reachable ({len(feed.entries)} items)")


class HNJobsSource(Source):
    """Y Combinator startup job posts on Hacker News (official Algolia API, tags=job)."""

    type_name = "hn_jobs"
    URL = "https://hn.algolia.com/api/v1/search_by_date"

    def fetch(self, queries: list[str]) -> list[RawJob]:
        data = self.http.get_json(self.URL, params={"tags": "job", "hitsPerPage": int(self.params.get("limit", 200))})
        out = []
        for h in data.get("hits") or []:
            t = h.get("title") or ""
            m = re.match(r"^(.*?)(?:\s*\((?:YC|yc)[^)]*\))?\s+(?:is\s+)?hiring:?\s*(?:an?\s+)?(.+)$", t, re.I)
            company, role = (m.group(1).strip(), m.group(2).strip()) if m else ("", t)
            text = html_to_text(h.get("story_text") or "")
            item = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            remote = bool(re.search(r"\bremote\b", f"{t} {text[:2000]}", re.I))
            out.append(RawJob(
                source=self.name, external_id=str(h.get("objectID")), title=role[:200], company=company[:120],
                url=h.get("url") or item, apply_url=h.get("url") or item, description=text or t,
                location="Remote" if remote else "", remote=True if remote else None,
                posted_at=to_dt(h.get("created_at")), tags=["YC startup"],
            ))
        return out
