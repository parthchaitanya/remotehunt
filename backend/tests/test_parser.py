import io
from pathlib import Path

import pytest

from app.resume.ats import score_resume
from app.resume.parser import ResumeParseError, parse_resume, parse_text

ROOT = Path(__file__).resolve().parents[2]


def _make_docx(text: str) -> bytes:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        if line.startswith("• "):
            d.add_paragraph(line[2:], style="List Bullet")
        else:
            d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _make_pdf(text: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.splitlines():
        c.drawString(40, y, line)
        y -= 14
    c.save()
    return buf.getvalue()


def test_sections_and_contact(sample_parsed):
    p = sample_parsed
    assert p["name"] == "Asha Verma"
    assert p["contact"]["email"] == "asha.verma@example.com"
    assert p["contact"]["phone"]
    assert p["contact"]["links"]["github"].startswith("github.com/")
    assert p["contact"]["links"]["linkedin"]
    for sec in ("summary", "education", "skills", "projects", "experience", "extracurricular"):
        assert sec in p["sections_found"]


def test_skills_categories_and_canonical(sample_parsed):
    cats = sample_parsed["skills"]["categories"]
    assert cats["Programming"] == ["Python", "Java"]
    assert "MySQL" in cats["Databases"]
    keys = set(sample_parsed["skill_keys"])
    assert {"python", "pandas", "scikit_learn", "mysql", "flask", "git"} <= keys
    # implied skills are tracked separately, not claimed
    assert "sql" in keys or "sql" in sample_parsed["implied_skill_keys"]


def test_experience_entry_with_wrapped_bullets(sample_parsed):
    exp = sample_parsed["experience"]
    assert len(exp) == 1
    e = exp[0]
    assert e["title"] == "Data Intern"
    assert e["organization"].startswith("Acme Analytics")
    assert "2024" in e["dates"]
    assert e["technologies"] == ["Python", "SQL", "Excel"]
    assert len(e["bullets"]) == 2


def test_project_bullet_continuation_is_merged(sample_parsed):
    proj = sample_parsed["projects"][0]
    assert proj["name"] == "Sales Forecaster"
    assert proj["has_link"] is True
    assert len(proj["bullets"]) == 2
    assert proj["bullets"][0].endswith("18% versus the baseline.")


def test_education(sample_parsed):
    edu = sample_parsed["education"][0]
    assert "Example Institute" in edu["institution"]
    assert "Bachelor" in edu["degree"]
    assert edu["dates"].startswith("2023")


def test_docx_roundtrip(sample_text):
    parsed, raw = parse_resume(_make_docx(sample_text), "resume.docx")
    assert parsed["file_type"] == "docx"
    assert parsed["experience"][0]["title"] == "Data Intern"
    assert len(parsed["experience"][0]["bullets"]) == 2
    assert "python" in parsed["skill_keys"]


def test_pdf_roundtrip(sample_text):
    parsed, raw = parse_resume(_make_pdf(sample_text), "resume.pdf")
    assert parsed["file_type"] == "pdf"
    assert parsed["contact"]["email"] == "asha.verma@example.com"
    assert "experience" in parsed["sections_found"]
    assert parsed["projects"][0]["name"] == "Sales Forecaster"


def test_rejects_unsupported_and_empty():
    with pytest.raises(ResumeParseError):
        parse_resume(b"hello", "resume.txt")
    with pytest.raises(ResumeParseError):
        parse_text("   \n  ")


def test_ats_score_breakdown(sample_parsed, sample_text):
    ats = score_resume(sample_parsed, sample_text, ["Python Developer", "Data Analyst"])
    assert 0 <= ats["score"] <= 100
    assert sum(c["max"] for c in ats["breakdown"]) == 100
    assert round(sum(c["score"] for c in ats["breakdown"])) == ats["score"]
    names = {c["category"] for c in ats["breakdown"]}
    assert {"Contact information", "Quantified impact", "Action verbs"} <= names
    assert ats["score"] >= 55  # a reasonable, well-structured resume


def test_ats_penalises_weak_resume():
    weak = parse_text("John\nSkills\nPython\nExperience\nWorked on things\n• Responsible for stuff\n")
    ats = score_resume(weak, "John\nSkills\nPython", ["Python Developer"])
    assert ats["score"] < 40
    assert ats["top_tips"]


@pytest.mark.skipif(not (ROOT / "Resume-Parth.pdf").exists(), reason="personal resume not present")
def test_real_resume_pdf_and_docx_agree():
    pdf = parse_resume((ROOT / "Resume-Parth.pdf").read_bytes(), "r.pdf")[0]
    assert pdf["experience"] and pdf["projects"] and pdf["education"]
    assert len(pdf["experience"][0]["bullets"]) == 4
    docx_path = ROOT / "Resume-Parth.docx"
    if docx_path.exists():
        dx = parse_resume(docx_path.read_bytes(), "r.docx")[0]
        assert set(dx["skill_keys"]) == set(pdf["skill_keys"])
