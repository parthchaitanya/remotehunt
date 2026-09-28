"""Tag how you'd apply: direct ATS, company site, email, LinkedIn, Naukri, job board, HN."""
from __future__ import annotations

import re

from .dedupe import ATS_SOURCES, is_direct

EMAIL_APPLY = re.compile(r"\b(send|email|mail|forward)\b[^.\n]{0,40}\b(cv|resume|résumé|application|portfolio)\b"
                         r"[^.\n]{0,40}[\w.+-]+@[\w-]+\.[\w.]+|\b(apply|applications?)\b[^.\n]{0,20}(at|to|via)\s+"
                         r"[\w.+-]+@[\w-]+\.[\w.]+", re.I)

LABELS = {
    "direct_ats": "Apply on company ATS",
    "company_site": "Company careers site",
    "email": "Apply by email",
    "linkedin": "LinkedIn",
    "naukri": "Naukri",
    "hn_comment": "Contact via HN post",
    "job_board": "Via job board",
}


def tag(source: str, url: str, apply_url: str, description: str, platform: str = "") -> str:
    link = apply_url or url or ""
    if source in ATS_SOURCES or is_direct(link):
        return "direct_ats"
    if "linkedin.com" in link or platform == "linkedin":
        return "linkedin"
    if "naukri.com" in link or platform == "naukri":
        return "naukri"
    if EMAIL_APPLY.search(description or ""):
        return "email"
    if source == "hn_whos_hiring":
        return "hn_comment"
    if re.search(r"/(careers?|jobs)/", link) and not re.search(
            r"(remotive|remoteok|weworkremotely|himalayas|jobicy|arbeitnow|workingnomads|adzuna|jooble|careerjet|"
            r"indeed|foundit|instahyre|wellfound)\.", link):
        return "company_site"
    return "job_board"
