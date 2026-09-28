"""New sources (Muse, Hasjob, 4dayweek, RSS feeds, HN jobs), hybrid handling and extra alert parsers."""
from app.gmail.alert_parsers import parse_alert_html
from app.gmail.classify import classify
from app.pipeline.normalize import normalize
from app.pipeline.region import assess
from app.sources.base import RawJob


def raw(**kw):
    base = dict(source="themuse", external_id="1", title="Data Analyst", company="Acme",
                url="https://example.com/job/1", description="Analyse data with Python and SQL. " * 20)
    base.update(kw)
    return RawJob(**base)


def test_work_mode_from_description(profile):
    hyb = normalize(raw(location="Gurugram", description="This is a hybrid role, 3 days a week in office. " * 5))
    assert hyb.remote_type == "hybrid" and assess(hyb, profile).eligible is True
    far = normalize(raw(location="Bengaluru, India", description="Hybrid: 2 days per week in the office. " * 5))
    assert far.remote_type == "hybrid" and assess(far, profile).eligible is False


def test_city_without_work_mode_is_unclear_unless_preferred(profile):
    blr = normalize(raw(location="Bangalore, India"))
    assert blr.remote_type == "unknown"
    assert assess(blr, profile).eligible is None
    noida = normalize(raw(location="Noida, India"))
    assert assess(noida, profile).eligible is True
    remote_blr = normalize(raw(location="Remote - Bengaluru", remote=True))
    assert assess(remote_blr, profile).eligible is True


def test_rss_title_and_author_parsing():
    from app.sources.boards import RSSFeedsSource

    src = RSSFeedsSource("remote_rss", {"params": {}}, {})
    j = src.to_raw({"title": "Junior Data Analyst at Acme Ltd", "link": "https://x/1", "author": "Acme Ltd"},
                   "realworkfromanywhere.com", True)
    assert (j.title, j.company, j.location) == ("Junior Data Analyst", "Acme Ltd", "Worldwide")
    j2 = src.to_raw({"title": "Python Engineer", "link": "https://x/2", "author": "Hopper<br>⚲&nbsp;Various US States"},
                    "jobspresso.co", False)
    assert j2.company == "Hopper" and "US States" in j2.location
    src.http.close()


def test_hn_jobs_title_parsing(monkeypatch):
    from app.sources.boards import HNJobsSource

    src = HNJobsSource("hn_jobs", {"params": {}}, {})
    monkeypatch.setattr(src.http, "get_json", lambda *a, **k: {"hits": [
        {"objectID": "1", "title": "Stable (YC W20) Is Hiring Product Engineers", "url": "https://s.com/jobs",
         "created_at": "2026-09-24T18:29:18Z"},
        {"objectID": "2", "title": "Acme (YC S21) is hiring a remote Python developer", "url": None}]})
    a, b = src.fetch([])
    assert (a.company, a.title) == ("Stable", "Product Engineers")
    assert b.company == "Acme" and b.remote is True and b.url.endswith("id=2")
    src.http.close()


def test_muse_mapping(monkeypatch):
    from app.sources.boards import MuseSource

    src = MuseSource("themuse", {"params": {"pages": 1, "location_groups": [["Flexible / Remote"]]}}, {})
    monkeypatch.setattr(src.http, "get_json", lambda *a, **k: {"page_count": 1, "results": [
        {"id": 7, "name": "Data Analyst", "company": {"name": "Acme"}, "contents": "<p>SQL</p>",
         "locations": [{"name": "Flexible / Remote"}], "levels": [{"name": "Entry Level"}],
         "refs": {"landing_page": "https://www.themuse.com/jobs/acme/data-analyst"},
         "publication_date": "2026-09-20T00:00:00Z"}]})
    (j,) = src.fetch([])
    assert j.remote is True and j.company == "Acme" and "Entry Level" in j.tags
    src.http.close()


def test_new_alert_platforms():
    html = ('<div><a href="https://internshala.com/internship/detail/data-science-internship-at-acme123">'
            'Data Science</a><p>Acme Labs · Work from home</p></div>')
    jobs = parse_alert_html("internshala", html)
    assert len(jobs) == 1 and jobs[0]["title"] == "Data Science" and jobs[0]["remote"] is True
    assert classify("Internshala <no-reply@internshala.com>", "New internships", "") == "job_alert"
    assert classify("Cutshort <jobs@cutshort.io>", "Jobs for you", "") == "job_alert"
