import pytest

from app.pipeline.matcher import HashingEmbedder, Matcher, required_years

DATA_ANALYST_JD = """We are hiring a Junior Data Analyst (remote). You will clean data with Python and Pandas,
write SQL queries against MySQL, build dashboards in Tableau and present insights. Experience with Excel and
statistics is a plus. Fresh graduates welcome."""
IOS_JD = """Senior iOS Engineer. 7+ years of experience building native apps in Swift and Objective-C, deep knowledge
of UIKit, Core Data, and App Store release processes. You will lead a team of mobile engineers."""
SENIOR_PY_JD = """Senior Python Developer. You need 6+ years of experience with Python, Django, PostgreSQL, Docker and
Kubernetes in production."""


@pytest.fixture
def matcher(sample_parsed, sample_text, profile):
    return Matcher(sample_parsed, sample_text, profile, embedder=HashingEmbedder())


def test_relevant_job_scores_higher(matcher):
    good = matcher.score({"title": "Junior Data Analyst", "description": DATA_ANALYST_JD})
    bad = matcher.score({"title": "Senior iOS Engineer", "description": IOS_JD})
    assert good.score > bad.score + 25
    assert 0 <= bad.score <= 100 and 0 <= good.score <= 100


def test_reasons_and_skills(matcher):
    r = matcher.score({"title": "Junior Data Analyst", "description": DATA_ANALYST_JD})
    assert any("skills it mentions" in x for x in r.reasons)
    assert any("Data Analyst" in x for x in r.reasons)
    assert "Python" in r.matched_skills and "Pandas" in r.matched_skills
    assert "Tableau" in r.missing_skills
    assert "Python" not in r.missing_skills
    assert r.role_family == "Data Analyst"


def test_seniority_and_years_penalty(matcher):
    r = matcher.score({"title": "Senior Python Developer", "description": SENIOR_PY_JD})
    assert r.penalty >= 15
    assert any("Senior" in x for x in r.reasons)
    assert any("6+ years" in x for x in r.reasons)
    assert "Kubernetes" in r.missing_skills


def test_entry_level_bonus_reason(matcher):
    r = matcher.score({"title": "Python Developer Intern", "description": "Python, Flask and SQL internship."})
    assert any("Entry-level" in x for x in r.reasons)
    assert r.title >= 1.0


def test_score_many_matches_single(matcher):
    jobs = [{"title": "Junior Data Analyst", "description": DATA_ANALYST_JD},
            {"title": "Senior iOS Engineer", "description": IOS_JD}]
    many = matcher.score_many(jobs)
    assert [m.score for m in many] == [matcher.score(j).score for j in jobs]


@pytest.mark.parametrize("text,expected", [
    ("Requires 3+ years of experience in Python", 3),
    ("2-4 years experience with SQL", 2),
    ("5 years of professional experience", 5),
    ("We have been around for 10 years.", None),
    ("No experience needed", None),
])
def test_required_years(text, expected):
    assert required_years(text) == expected


def test_real_minilm_model_ranks_correctly(sample_parsed, sample_text, profile):
    """Uses the real all-MiniLM-L6-v2 model (downloaded once, cached)."""
    try:
        from app.pipeline.matcher import SentenceTransformerEmbedder

        emb = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    except Exception as exc:  # offline CI without model cache
        pytest.skip(f"model unavailable: {type(exc).__name__}")
    m = Matcher(sample_parsed, sample_text, profile, embedder=emb)
    good = m.score({"title": "Junior Data Analyst", "description": DATA_ANALYST_JD})
    bad = m.score({"title": "Senior iOS Engineer", "description": IOS_JD})
    assert good.semantic > bad.semantic
    assert good.score > bad.score + 25


def test_non_technical_role_penalised(matcher):
    r = matcher.score({"title": "Recruiter, AI/ML Research",
                       "description": "Recruit machine learning researchers. Python familiarity is a plus."})
    assert any("Non-technical" in x for x in r.reasons)
    assert r.score < 40
    eng = matcher.score({"title": "Machine Learning Engineer", "description": "Python, scikit-learn, pandas."})
    assert not any("Non-technical" in x for x in eng.reasons)
