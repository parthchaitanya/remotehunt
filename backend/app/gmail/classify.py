"""Classify emails into job-alert / recruiter categories from headers + snippet (pure, testable)."""
from __future__ import annotations

import re

ALERT_SENDERS: dict[str, list[str]] = {
    "linkedin": [r"jobalerts-noreply@linkedin\.com", r"jobs-noreply@linkedin\.com", r"jobs-listings@linkedin\.com"],
    "naukri": [r"@naukri\.com", r"naukrialerts"],
    "indeed": [r"@indeed\.com", r"@indeedemail\.com", r"@match\.indeed\.com"],
    "foundit": [r"@foundit\.in", r"@monsterindia\.com", r"@mail\.foundit\.in"],
    "instahyre": [r"@instahyre\.com"],
    "wellfound": [r"@wellfound\.com", r"@angel\.co", r"@angellist\.com"],
    "internshala": [r"@internshala\.com"],
    "cutshort": [r"@cutshort\.io"],
    "glassdoor": [r"@glassdoor\.com", r"@glassdoor\.co\.in"],
    "hirist": [r"@hirist\.(com|tech)"],
}

ATS_DOMAINS = [r"greenhouse\.io", r"greenhouse-mail\.io", r"lever\.co", r"hire\.lever\.co", r"ashbyhq\.com",
               r"workablemail\.com", r"workable\.com", r"smartrecruiters\.com", r"myworkday\.com", r"icims\.com",
               r"jobvite\.com", r"bamboohr\.com", r"recruitee\.com", r"teamtailor\.com", r"breezy\.hr",
               r"freshteam\.com", r"zohorecruit\.com", r"darwinbox\.in", r"keka\.com"]

INTERVIEW = re.compile(r"\b(interview|schedule a (call|chat)|your availability|next round|technical round|"
                       r"assessment|coding (test|challenge)|take[- ]home|hackerrank|codility|calendly)\b", re.I)
REJECTION = re.compile(r"\b(unfortunately|not (be )?moving forward|decided to (move|proceed) with other|"
                       r"other candidates|regret to inform|not selected|position has been filled|won't be progressing|"
                       r"will not be proceeding)\b", re.I)
APPLICATION = re.compile(r"\b(thank(s| you) for (applying|your application|your interest)|application (received|"
                         r"for|status|update)|we('ve| have) received your application|your application to)\b", re.I)
RECRUITER = re.compile(r"\b(recruit(er|ing|ment)|talent acquisition|hiring (manager|team)|opportunity at|"
                       r"role at|position at|job opportunity|are you open to|came across your (profile|resume)|"
                       r"your profile|job offer|offer letter)\b", re.I)
NEWSLETTER = re.compile(r"\b(newsletter|digest|webinar|unsubscribe from this|weekly roundup|% off|sale)\b", re.I)


def alert_platform(from_header: str) -> str | None:
    f = (from_header or "").lower()
    for platform, pats in ALERT_SENDERS.items():
        if any(re.search(p, f) for p in pats):
            return platform
    return None


def gmail_alert_query(newer_than_days: int = 3) -> str:
    senders = ["jobalerts-noreply@linkedin.com", "jobs-noreply@linkedin.com", "naukri.com", "indeed.com",
               "indeedemail.com", "foundit.in", "monsterindia.com", "instahyre.com", "wellfound.com", "angel.co",
               "internshala.com", "cutshort.io", "glassdoor.com", "glassdoor.co.in", "hirist.com", "hirist.tech"]
    return f"from:({' OR '.join(senders)}) newer_than:{int(newer_than_days)}d"


def classify(from_header: str, subject: str, snippet: str, has_list_unsubscribe: bool = False) -> str | None:
    """Return job_alert | interview | rejection | application_update | recruiter | None."""
    if alert_platform(from_header):
        return "job_alert"
    text = f"{subject}\n{snippet}"
    sender = (from_header or "").lower()
    from_ats = any(re.search(d, sender) for d in ATS_DOMAINS)
    if REJECTION.search(text) and (from_ats or APPLICATION.search(text) or RECRUITER.search(text)
                                   or re.search(r"application|candidacy|role|position", text, re.I)):
        return "rejection"
    if INTERVIEW.search(text) and (from_ats or RECRUITER.search(text) or not has_list_unsubscribe):
        return "interview"
    if APPLICATION.search(text):
        return "application_update"
    if from_ats:
        return "application_update"
    if RECRUITER.search(text) and not (has_list_unsubscribe and NEWSLETTER.search(text)):
        return "recruiter"
    return None


LABELS = {
    "job_alert": "RemoteHunt/Job Alert",
    "recruiter": "RemoteHunt/Recruiter",
    "interview": "RemoteHunt/Interview",
    "rejection": "RemoteHunt/Rejection",
    "application_update": "RemoteHunt/Application Update",
}
