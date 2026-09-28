"""Job-alert emails in your Gmail (LinkedIn, Naukri, Indeed, foundit, Instahyre, Wellfound)."""
from __future__ import annotations

from ..db import SessionLocal
from ..gmail import client as gmail
from ..gmail.alert_parsers import parse_alert_html
from ..gmail.classify import LABELS, alert_platform, gmail_alert_query
from .base import HealthResult, NotConfigured, RawJob, Source, SourceError


class GmailAlertsSource(Source):
    type_name = "gmail_alerts"

    def configured(self) -> tuple[bool, str]:
        with SessionLocal() as db:
            if not gmail.is_connected(db):
                return False, "Gmail not connected (Settings -> Connect Gmail)"
        return True, ""

    def fetch(self, queries: list[str]) -> list[RawJob]:
        with SessionLocal() as db:
            try:
                svc = gmail.service(db)
            except gmail.GmailNotConnected as exc:
                raise NotConfigured(str(exc)) from None
            q = gmail_alert_query(int(self.params.get("newer_than_days", 3)))
            try:
                listing = svc.users().messages().list(userId="me", q=q,
                                                      maxResults=int(self.params.get("max_messages", 60))).execute()
            except Exception as exc:
                raise SourceError(f"Gmail list failed: {type(exc).__name__}") from None
            self.http.budget.record(True, 200, "fetch")
            out: list[RawJob] = []
            for ref in listing.get("messages", []):
                try:
                    msg = svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
                except Exception:
                    continue
                self.http.budget.record(True, 200, "fetch")
                headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
                platform = alert_platform(headers.get("from", ""))
                if not platform:
                    continue
                html, text = gmail.message_body(msg.get("payload", {}))
                for j in parse_alert_html(platform, html, text):
                    out.append(RawJob(
                        source=self.name, external_id=f"{platform}:{j['id']}", title=j["title"],
                        company=j["company"], url=j["url"], apply_url=j["url"], description="",
                        location=j["location"], remote=True if j["remote"] else None,
                        region_restrictions=[j["location"]] if j["location"] else [],
                        tags=[platform], extra={"platform": platform, "alert_email": True},
                    ))
                try:
                    if "labelIds" in msg and gmail.ensure_label(db, svc, LABELS["job_alert"]) not in msg["labelIds"]:
                        gmail.add_labels(db, svc, ref["id"], [LABELS["job_alert"]])
                except Exception:
                    pass  # labelling is best effort
            return out

    def ping(self) -> HealthResult:
        with SessionLocal() as db:
            gmail.service(db).users().getProfile(userId="me").execute()
        return HealthResult("ok", "Gmail reachable")
