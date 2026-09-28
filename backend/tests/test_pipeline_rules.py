"""Region eligibility, dedupe, guardrail, budgets and alert-email parsing."""
from datetime import datetime, timezone

from app.gmail.alert_parsers import parse_alert_html
from app.gmail.classify import classify
from app.pipeline.dedupe import dedupe_batch
from app.pipeline.normalize import normalize
from app.pipeline.region import assess
from app.sources.base import Budget, BudgetExceeded, RawJob
from app.tailor.guardrail import build_allowed, check_text


def raw(**kw):
    base = dict(source="remotive", external_id="1", title="Python Developer", company="Acme",
                url="https://remotive.com/job/1", description="Build APIs in Python. " * 20, remote=True)
    base.update(kw)
    return RawJob(**base)


# ---------------------------------------------------------------- region
def test_worldwide_eligible(profile):
    n = normalize(raw(location="Worldwide", region_restrictions=["Worldwide"]))
    assert assess(n, profile).eligible is True


def test_us_only_ineligible(profile):
    n = normalize(raw(location="USA Only", region_restrictions=["USA Only"]))
    e = assess(n, profile)
    assert e.eligible is False and "US" in e.reason


def test_timezone_numbers(profile):
    far = normalize(raw(location="", region_restrictions=[], timezone_restrictions=[-8, -7, -6, -5]))
    near = normalize(raw(location="Worldwide", region_restrictions=["Worldwide"], timezone_restrictions=[3, 4, 5.5]))
    assert assess(far, profile).eligible is False
    assert assess(near, profile).eligible is True


def test_timezone_text_window(profile):
    n = normalize(raw(location="Remote (UTC-1 to UTC+3)", region_restrictions=[]))
    assert assess(n, profile).eligible is True  # within 3.5h tolerance of IST
    n2 = normalize(raw(location="Remote (UTC-8 to UTC-5)", region_restrictions=[]))
    assert assess(n2, profile).eligible is False


def test_description_restriction(profile):
    n = normalize(raw(location="Remote", description="Great role. You must be located in the United States."))
    assert assess(n, profile).eligible is False


def test_onsite_rules(profile):
    ok = normalize(raw(remote=False, location="Noida, Uttar Pradesh"))
    far = normalize(raw(remote=False, location="Berlin, Germany"))
    assert assess(ok, profile).eligible is True
    assert assess(far, profile).eligible is False


def test_unpaid_rejected(profile):
    n = normalize(raw(location="Worldwide", title="Unpaid Data Analyst Intern"))
    assert assess(n, profile).eligible is False


def test_remote_unspecified_is_unknown(profile):
    n = normalize(raw(location="Remote", region_restrictions=[]))
    assert assess(n, profile).eligible is None


# ---------------------------------------------------------------- dedupe
def test_dedupe_prefers_direct_ats():
    agg = normalize(raw(source="remotive", company="Acme Inc.", title="Python Developer (Remote)",
                        url="https://remotive.com/job/1?utm_source=x"))
    ats = normalize(raw(source="greenhouse", company="ACME", title="Python Developer",
                        url="https://boards.greenhouse.io/acme/jobs/9", description="short"))
    assert agg.fingerprint == ats.fingerprint
    uniq, seen = dedupe_batch([agg, ats])
    assert len(uniq) == 1 and uniq[0].source == "greenhouse"
    assert seen[agg.fingerprint][0]["source"] == "remotive"
    assert "utm_source" not in agg.url


# ---------------------------------------------------------------- guardrail
def test_guardrail(sample_parsed, sample_text):
    allowed = build_allowed(sample_parsed, sample_text, ["Kubernetes Platform Engineer", "Acme"])
    assert check_text("Built a regression model in Python for 1,200 stores.", allowed) == []
    v = check_text("Built Kubernetes clusters with 5 years of experience as a Senior engineer.", allowed)
    types = {x["type"] for x in v}
    assert {"skill", "number", "experience", "title"} <= types
    assert check_text("Applying for the Kubernetes Platform Engineer role at Acme.", allowed) == []
    assert check_text("Improved accuracy by [X%] using Pandas.", allowed) == []
    assert any(x["type"] == "credential" for x in check_text("AWS Certified developer", allowed))


# ---------------------------------------------------------------- budgets
def test_budget_blocks_after_limit():
    from app.db import SessionLocal
    from app.models import ApiCall

    b = Budget("test_budget_src", {"max_calls_per_day": 2, "lifetime_budget": 3})
    assert b.remaining() == 2
    b.record(True, 200, "fetch")
    b.record(True, 200, "fetch")
    assert b.remaining() == 0
    try:
        b.check()
        raise AssertionError("expected BudgetExceeded")
    except BudgetExceeded:
        pass
    # lifetime counts old calls too
    with SessionLocal() as db:
        db.add(ApiCall(source="test_budget_src", ts=datetime(2020, 1, 1, tzinfo=timezone.utc)))
        db.commit()
    assert Budget("test_budget_src", {"lifetime_budget": 3}).remaining() == 0


# ---------------------------------------------------------------- gmail parsing / classification
LINKEDIN_HTML = """<table><tr><td>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc&refId=x">Data Analyst</a>
<p>Acme Corp · Bengaluru, Karnataka, India (Remote)</p>
<a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc">View job</a>
</td></tr><tr><td>
<a href="https://www.linkedin.com/comm/jobs/view/4099999999/">Python Developer</a>
<p>Beta Labs · Noida, Uttar Pradesh, India</p>
</td></tr><tr><td><a href="https://www.linkedin.com/jobs/search">See all jobs</a></td></tr></table>"""


def test_linkedin_alert_parser():
    jobs = parse_alert_html("linkedin", LINKEDIN_HTML)
    assert len(jobs) == 2
    j = {x["id"]: x for x in jobs}["4012345678"]
    assert j["title"] == "Data Analyst"
    assert j["company"] == "Acme Corp"
    assert "Remote" in j["location"] and j["remote"] is True
    assert "trackingId" not in j["url"]


def test_classify_emails():
    assert classify("LinkedIn <jobalerts-noreply@linkedin.com>", "New jobs", "") == "job_alert"
    assert classify("Acme <no-reply@greenhouse.io>", "Your application to Acme", "Thank you for applying") \
        == "application_update"
    assert classify("Recruiter <jane@acme.com>", "Interview for Data Analyst",
                    "Could you share your availability for an interview?") == "interview"
    assert classify("Acme <no-reply@lever.co>", "Update on your application",
                    "Unfortunately we have decided to move forward with other candidates") == "rejection"
    assert classify("Shop <deals@shop.com>", "50% off sale", "Big sale this weekend", True) is None


def test_city_only_locations_are_restricted(profile):
    for loc in ("San Francisco", "New York City", "London", "Austin, TX", "São Paulo"):
        n = normalize(raw(location=loc, region_restrictions=[loc]))
        assert assess(n, profile).eligible is False, loc
    n = normalize(raw(location="Remote - Bengaluru", region_restrictions=["Bengaluru"]))
    assert assess(n, profile).eligible is True


def test_hn_comment_parsing():
    from app.sources.boards import HNWhosHiringSource

    h = {"objectID": "1", "created_at": "2026-09-01T00:00:00Z",
         "comment_text": "https://cyberatlas.ai | ML Engineer | REMOTE (Worldwide) | Full-time<p>We build things.</p>"}
    job = HNWhosHiringSource._parse_comment(h, "9")
    assert job.title == "ML Engineer" and job.company == "cyberatlas.ai" and job.remote is True
    h2 = {"objectID": "2", "comment_text": "Acme | Remote | Full-time | https://acme.com/jobs"}
    assert HNWhosHiringSource._parse_comment(h2, "9") is None


def test_region_in_location_beats_description_timezone(profile):
    n = normalize(raw(location="REMOTE: North America / Europe",
                      description="We work across UTC-8 to UTC+2 hours. " * 10))
    assert assess(n, profile).eligible is False


def test_hn_location_not_confused_with_role():
    from app.sources.boards import HNWhosHiringSource

    h = {"objectID": "3", "comment_text": "Lokker.com | Data Scientist, Classification and Scoring | REMOTE: "
                                          "North America / Europe, UTC-8 to UTC+2 | Full-time"}
    job = HNWhosHiringSource._parse_comment(h, "9")
    assert job.title == "Data Scientist, Classification and Scoring"
    assert job.location.startswith("REMOTE")
