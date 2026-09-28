"""Keyed aggregator APIs: Adzuna, Jooble (weekly, 500-call lifetime budget), Careerjet (off by default)."""
from __future__ import annotations

from ..config import get_settings
from ..textutil import html_to_text
from .base import RawJob, Source, SourceError, to_dt


class AdzunaSource(Source):
    """https://developer.adzuna.com - needs ADZUNA_APP_ID / ADZUNA_APP_KEY."""

    type_name = "adzuna"
    requires_keys = ("adzuna_app_id", "adzuna_app_key")

    def fetch(self, queries: list[str]) -> list[RawJob]:
        s = get_settings()
        country = self.params.get("country", "in")
        out: list[RawJob] = []
        for q in queries:
            data = self.http.get_json(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                params={"app_id": s.adzuna_app_id, "app_key": s.adzuna_app_key, "what": q,
                        "results_per_page": int(self.params.get("results_per_page", 50)),
                        "max_days_old": int(self.params.get("max_days_old", 7)), "content-type": "application/json"},
            )
            for j in data.get("results") or []:
                loc = (j.get("location") or {}).get("display_name", "")
                text = f"{j.get('title', '')} {j.get('description', '')} {loc}".lower()
                out.append(RawJob(
                    source=self.name, external_id=str(j.get("id", "")), title=html_to_text(j.get("title", "")),
                    company=(j.get("company") or {}).get("display_name", ""), url=j.get("redirect_url", ""),
                    apply_url=j.get("redirect_url", ""), description=html_to_text(j.get("description", "")),
                    location=loc, remote=True if ("remote" in text or "work from home" in text) else None,
                    region_restrictions=[loc] if loc else [], salary_min=j.get("salary_min"),
                    salary_max=j.get("salary_max"),
                    salary_currency="INR" if country == "in" else "", employment_type=j.get("contract_time") or "",
                    tags=[(j.get("category") or {}).get("label", "")], posted_at=to_dt(j.get("created")),
                ))
        return out


class JoobleSource(Source):
    """https://jooble.org/api/about - key has a 500-request lifetime budget, so this runs weekly."""

    type_name = "jooble"
    requires_keys = ("jooble_api_key",)

    def fetch(self, queries: list[str]) -> list[RawJob]:
        key = get_settings().jooble_api_key
        out: list[RawJob] = []
        for q in queries:
            data = self.http.post_json(f"https://jooble.org/api/{key}",
                                       {"keywords": f"{q} remote", "location": self.params.get("location", ""),
                                        "page": "1"})
            for j in data.get("jobs") or []:
                loc = j.get("location") or ""
                text = f"{j.get('title', '')} {j.get('snippet', '')} {loc} {j.get('type', '')}".lower()
                out.append(RawJob(
                    source=self.name, external_id=str(j.get("id", "")), title=html_to_text(j.get("title", "")),
                    company=j.get("company") or "", url=j.get("link", ""), apply_url=j.get("link", ""),
                    description=html_to_text(j.get("snippet", "")), location=loc,
                    remote=True if ("remote" in text or "work from home" in text) else None,
                    region_restrictions=[loc] if loc else [], salary_text=j.get("salary") or "",
                    employment_type=j.get("type") or "", posted_at=to_dt(j.get("updated")),
                    extra={"via": j.get("source", "")},
                ))
        return out


class CareerjetSource(Source):
    """Careerjet partner API (disabled by default). Needs CAREERJET_AFFID."""

    type_name = "careerjet"
    requires_keys = ("careerjet_affid",)

    def fetch(self, queries: list[str]) -> list[RawJob]:
        s = get_settings()
        endpoint = self.params.get("endpoint", "http://public.api.careerjet.net/search")
        out: list[RawJob] = []
        for q in queries:
            data = self.http.get_json(endpoint, params={
                "locale_code": self.params.get("locale_code", "en_IN"), "keywords": q,
                "location": self.params.get("location", "India"), "affid": s.careerjet_affid,
                "user_ip": self.params.get("user_ip", "127.0.0.1"), "user_agent": "RemoteHunt/1.0",
                "url": s.frontend_url, "pagesize": 50, "sort": "date"})
            if data.get("type") == "ERROR":
                raise SourceError(f"Careerjet error: {str(data.get('error', ''))[:120]}")
            for j in data.get("jobs") or []:
                loc = j.get("locations") or ""
                text = f"{j.get('title', '')} {j.get('description', '')} {loc}".lower()
                out.append(RawJob(
                    source=self.name, external_id=j.get("url", ""), title=html_to_text(j.get("title", "")),
                    company=j.get("company") or "", url=j.get("url", ""), apply_url=j.get("url", ""),
                    description=html_to_text(j.get("description", "")), location=loc,
                    remote=True if "remote" in text or "work from home" in text else None,
                    region_restrictions=[loc] if loc else [], salary_text=j.get("salary") or "",
                    posted_at=to_dt(j.get("date")), extra={"via": j.get("site", "")},
                ))
        return out
