"""Official public job-board APIs of ATS platforms, for companies in config/target_companies.yaml."""
from __future__ import annotations

import logging
from typing import Any

from ..config import load_target_companies
from ..textutil import html_to_text
from .base import HealthResult, RawJob, Source, SourceError, to_dt

log = logging.getLogger(__name__)


class ATSBoardSource(Source):
    """One source per ATS platform; iterates over that platform's target companies.

    A failing company is recorded in the health details and skipped; it never fails the whole run.
    """

    platform = ""

    def companies(self) -> list[dict[str, str]]:
        return [c for c in (load_target_companies().get(self.platform) or []) if c.get("token")]

    def configured(self) -> tuple[bool, str]:
        if not self.companies():
            return False, f"no {self.platform} companies in config/target_companies.yaml"
        return True, ""

    def fetch_company(self, company: dict[str, str]) -> list[RawJob]:
        raise NotImplementedError

    def fetch(self, queries: list[str]) -> list[RawJob]:
        out: list[RawJob] = []
        self.company_status: dict[str, str] = {}
        for c in self.companies():
            try:
                jobs = self.fetch_company(c)
                self.company_status[c["token"]] = f"ok ({len(jobs)})"
                out += jobs
            except SourceError as exc:
                self.company_status[c["token"]] = str(exc)
                log.warning("%s: company board '%s' failed: %s", self.name, c["token"], exc)
        if self.companies() and not out and all(not s.startswith("ok") for s in self.company_status.values()):
            raise SourceError("all company boards failed")
        return out

    def health_details(self) -> dict[str, Any]:
        return {"companies": getattr(self, "company_status", {})}

    def ping(self) -> HealthResult:
        return ping_first_company(self)


class GreenhouseSource(ATSBoardSource):
    type_name = "greenhouse"
    platform = "greenhouse"

    def fetch_company(self, c: dict[str, str]) -> list[RawJob]:
        data = self.http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{c['token']}/jobs",
                                  params={"content": "true"})
        out = []
        for j in data.get("jobs") or []:
            loc = (j.get("location") or {}).get("name", "")
            offices = [o.get("name", "") for o in j.get("offices") or [] if o.get("name")]
            out.append(RawJob(
                source=self.name, external_id=f"{c['token']}:{j.get('id')}", title=j.get("title", ""),
                company=c.get("name") or c["token"], url=j.get("absolute_url", ""), apply_url=j.get("absolute_url", ""),
                description=html_to_text(j.get("content") or ""), location=loc,
                remote=True if "remote" in loc.lower() else None,
                region_restrictions=[loc, *offices] if loc else offices,
                tags=[d.get("name") for d in j.get("departments") or [] if d.get("name")],
                posted_at=to_dt(j.get("first_published") or j.get("updated_at")),
            ))
        return out


class LeverSource(ATSBoardSource):
    type_name = "lever"
    platform = "lever"

    def fetch_company(self, c: dict[str, str]) -> list[RawJob]:
        data = self.http.get_json(f"https://api.lever.co/v0/postings/{c['token']}", params={"mode": "json"})
        out = []
        for j in data if isinstance(data, list) else []:
            cats = j.get("categories") or {}
            loc = cats.get("location") or ""
            all_locs = cats.get("allLocations") or ([loc] if loc else [])
            wp = (j.get("workplaceType") or "").lower()
            lists = "\n".join(f"{x.get('text', '')}\n{html_to_text(x.get('content', ''))}" for x in j.get("lists") or [])
            desc = "\n\n".join(filter(None, [j.get("descriptionPlain") or html_to_text(j.get("description")), lists,
                                             j.get("additionalPlain") or ""]))
            out.append(RawJob(
                source=self.name, external_id=f"{c['token']}:{j.get('id')}", title=j.get("text", ""),
                company=c.get("name") or c["token"], url=j.get("hostedUrl", ""),
                apply_url=j.get("applyUrl") or j.get("hostedUrl", ""), description=desc, location=loc,
                remote=True if wp == "remote" or "remote" in loc.lower() else (False if wp == "on-site" else None),
                region_restrictions=list(all_locs), employment_type=cats.get("commitment") or "",
                tags=[t for t in (cats.get("team"), cats.get("department")) if t], posted_at=to_dt(j.get("createdAt")),
            ))
        return out


class AshbySource(ATSBoardSource):
    type_name = "ashby"
    platform = "ashby"

    def fetch_company(self, c: dict[str, str]) -> list[RawJob]:
        data = self.http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{c['token']}",
                                  params={"includeCompensation": "true"})
        out = []
        for j in data.get("jobs") or []:
            if j.get("isListed") is False:
                continue
            locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            locs = [l for l in locs if l]
            comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            wp = (j.get("workplaceType") or "").lower()
            out.append(RawJob(
                source=self.name, external_id=f"{c['token']}:{j.get('id')}", title=j.get("title", ""),
                company=c.get("name") or c["token"], url=j.get("jobUrl", ""),
                apply_url=j.get("applyUrl") or j.get("jobUrl", ""),
                description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                location=", ".join(locs), remote=bool(j.get("isRemote")) or wp == "remote",
                region_restrictions=locs, salary_text=comp, employment_type=j.get("employmentType") or "",
                tags=[t for t in (j.get("department"), j.get("team")) if t], posted_at=to_dt(j.get("publishedAt")),
            ))
        return out


class WorkableSource(ATSBoardSource):
    type_name = "workable"
    platform = "workable"

    def fetch_company(self, c: dict[str, str]) -> list[RawJob]:
        data = self.http.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{c['token']}",
                                  params={"details": "true"})
        out = []
        for j in data.get("jobs") or []:
            locs = [", ".join(filter(None, [l.get("city"), l.get("country")])) for l in j.get("locations") or []
                    if not l.get("hidden")]
            loc = locs[0] if locs else ", ".join(filter(None, [j.get("city"), j.get("country")]))
            out.append(RawJob(
                source=self.name, external_id=f"{c['token']}:{j.get('shortcode')}", title=j.get("title", ""),
                company=data.get("name") or c.get("name") or c["token"], url=j.get("url", ""),
                apply_url=j.get("application_url") or j.get("url", ""), description=html_to_text(j.get("description")),
                location=loc, remote=bool(j.get("telecommuting")), region_restrictions=locs or [loc],
                employment_type=j.get("employment_type") or "",
                tags=[t for t in (j.get("department"), j.get("function")) if t],
                posted_at=to_dt(j.get("published_on") or j.get("created_at")),
            ))
        return out


class SmartRecruitersSource(ATSBoardSource):
    type_name = "smartrecruiters"
    platform = "smartrecruiters"
    BASE = "https://api.smartrecruiters.com/v1/companies"

    def fetch_company(self, c: dict[str, str]) -> list[RawJob]:
        data = self.http.get_json(f"{self.BASE}/{c['token']}/postings", params={"limit": 100})
        out = []
        detail_budget = int(self.params.get("max_detail_calls_per_company", 15))
        for j in data.get("content") or []:
            loc = j.get("location") or {}
            full = loc.get("fullLocation") or ", ".join(filter(None, [loc.get("city"), loc.get("country")]))
            remote = bool(loc.get("remote"))
            desc = ""
            # Descriptions need one extra call each; only spend them on remote postings.
            if remote and detail_budget > 0:
                detail_budget -= 1
                try:
                    d = self.http.get_json(f"{self.BASE}/{c['token']}/postings/{j.get('id')}")
                    secs = (d.get("jobAd") or {}).get("sections") or {}
                    desc = "\n\n".join(html_to_text((secs.get(k) or {}).get("text")) for k in
                                       ("jobDescription", "qualifications", "additionalInformation"))
                except SourceError:
                    desc = ""
            url = f"https://jobs.smartrecruiters.com/{c['token']}/{j.get('id')}"
            out.append(RawJob(
                source=self.name, external_id=f"{c['token']}:{j.get('id')}", title=j.get("name", ""),
                company=(j.get("company") or {}).get("name") or c.get("name") or c["token"], url=url, apply_url=url,
                description=desc, location=full, remote=remote, region_restrictions=[full] if full else [],
                employment_type=(j.get("typeOfEmployment") or {}).get("label") or "",
                tags=[(j.get("experienceLevel") or {}).get("label", "")], posted_at=to_dt(j.get("releasedDate")),
            ))
        return out


def ping_first_company(src: ATSBoardSource) -> HealthResult:
    companies = src.companies()
    if not companies:
        return HealthResult("unconfigured", "No companies configured")
    src.fetch_company(companies[0])
    return HealthResult("ok", f"{companies[0]['token']} board reachable")
