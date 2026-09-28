"""Export tailored resume / cover letter to ATS-friendly PDF (reportlab) and DOCX (python-docx)."""
from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


def _contact_line(c: dict[str, Any]) -> list[str]:
    contact = c.get("contact") or {}
    links = contact.get("links") or {}
    parts = [contact.get("phone"), contact.get("email"), links.get("linkedin"), links.get("github"),
             links.get("portfolio")]
    return [p for p in parts if p]


# ----------------------------------------------------------------------------- PDF
def _styles():
    ss = getSampleStyleSheet()
    return {
        "name": ParagraphStyle("name", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=18, spaceAfter=2,
                               alignment=TA_CENTER),
        "contact": ParagraphStyle("contact", parent=ss["Normal"], fontSize=8.5, alignment=TA_CENTER,
                                  textColor=colors.HexColor("#333333")),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=8,
                            spaceAfter=2, textColor=colors.HexColor("#111111")),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontSize=9.5, leading=12.5),
        "entry": ParagraphStyle("entry", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                                spaceBefore=3),
        "meta": ParagraphStyle("meta", parent=ss["Normal"], fontName="Helvetica-Oblique", fontSize=8.5, leading=11,
                               textColor=colors.HexColor("#444444")),
        "letter": ParagraphStyle("letter", parent=ss["Normal"], fontSize=10.5, leading=15, spaceAfter=9),
    }


def _section(story, st, title):
    story.append(Paragraph(escape(title.upper()), st["h"]))
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#999999"), spaceAfter=3))


def _bullets(items, st):
    return ListFlowable([ListItem(Paragraph(escape(b), st["body"]), leftIndent=10) for b in items],
                        bulletType="bullet", start="•", leftIndent=10, bulletFontSize=8)


def resume_pdf(c: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=f"{c.get('name', '')} - Resume", author=c.get("name", ""))
    st = _styles()
    story: list = [Paragraph(escape(c.get("name", "")), st["name"]),
                   Paragraph(escape("  |  ".join(_contact_line(c))), st["contact"])]
    if c.get("summary"):
        _section(story, st, "Summary")
        story.append(Paragraph(escape(c["summary"]), st["body"]))
    if c.get("skills"):
        _section(story, st, "Technical Skills")
        for s in c["skills"]:
            story.append(Paragraph(f"<b>{escape(s['category'])}:</b> {escape(', '.join(s['items']))}", st["body"]))
    if c.get("experience"):
        _section(story, st, "Experience")
        for e in c["experience"]:
            head = " – ".join(x for x in (e.get("title"), e.get("organization")) if x)
            if e.get("dates"):
                head += f"  ({e['dates']})"
            story.append(Paragraph(escape(head), st["entry"]))
            if e.get("technologies"):
                story.append(Paragraph(escape(", ".join(e["technologies"])), st["meta"]))
            story.append(_bullets(e.get("bullets", []), st))
    if c.get("projects"):
        _section(story, st, "Projects")
        for p in c["projects"]:
            head = p.get("name", "") + (f": {p['description']}" if p.get("description") else "")
            story.append(Paragraph(escape(head), st["entry"]))
            if p.get("technologies"):
                story.append(Paragraph(escape(", ".join(p["technologies"])), st["meta"]))
            story.append(_bullets(p.get("bullets", []), st))
    if c.get("education"):
        _section(story, st, "Education")
        for e in c["education"]:
            story.append(Paragraph(escape(e.get("institution", "")) + (f"  ({escape(e['dates'])})" if e.get("dates")
                                                                         else ""), st["entry"]))
            if e.get("degree"):
                story.append(Paragraph(escape(e["degree"] + (f" – {e['grade']}" if e.get("grade") else "")),
                                       st["body"]))
    if c.get("certifications"):
        _section(story, st, "Certifications")
        story.append(_bullets(c["certifications"], st))
    if c.get("extracurricular"):
        _section(story, st, "Activities")
        story.append(_bullets(c["extracurricular"], st))
    doc.build(story)
    return buf.getvalue()


def cover_pdf(c: dict[str, Any], sender: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm,
                            bottomMargin=20 * mm, title="Cover letter")
    st = _styles()
    story: list = [Paragraph(escape(sender.get("name", "")), st["entry"]),
                   Paragraph(escape("  |  ".join(_contact_line(sender))), st["meta"]), Spacer(1, 10)]
    story.append(Paragraph(escape(c.get("greeting", "")), st["letter"]))
    story += [Paragraph(escape(p), st["letter"]) for p in c.get("paragraphs", [])]
    story.append(Paragraph(escape(c.get("closing", "")).replace("\n", "<br/>"), st["letter"]))
    doc.build(story)
    return buf.getvalue()


# ----------------------------------------------------------------------------- DOCX
def _docx():
    import docx
    from docx.shared import Pt

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    for section in d.sections:
        section.left_margin = section.right_margin = Pt(46)
        section.top_margin = section.bottom_margin = Pt(36)
    return d


def _heading(d, text):
    p = d.add_paragraph()
    run = p.add_run(text.upper())
    run.bold = True
    p.paragraph_format.space_before = 8
    p.paragraph_format.space_after = 2


def resume_docx(c: dict[str, Any]) -> bytes:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    d = _docx()
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(c.get("name", ""))
    r.bold = True
    r.font.size = Pt(18)
    p = d.add_paragraph("  |  ".join(_contact_line(c)))
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if c.get("summary"):
        _heading(d, "Summary")
        d.add_paragraph(c["summary"])
    if c.get("skills"):
        _heading(d, "Technical Skills")
        for s in c["skills"]:
            p = d.add_paragraph()
            p.add_run(f"{s['category']}: ").bold = True
            p.add_run(", ".join(s["items"]))
            p.paragraph_format.space_after = 0
    for title, key in (("Experience", "experience"), ("Projects", "projects")):
        if not c.get(key):
            continue
        _heading(d, title)
        for e in c[key]:
            head = " – ".join(x for x in (e.get("title") or e.get("name"), e.get("organization")) if x)
            if e.get("description"):
                head += f": {e['description']}"
            p = d.add_paragraph()
            p.add_run(head).bold = True
            if e.get("dates"):
                p.add_run(f"  ({e['dates']})")
            if e.get("technologies"):
                d.add_paragraph().add_run(", ".join(e["technologies"])).italic = True
            for b in e.get("bullets", []):
                d.add_paragraph(b, style="List Bullet")
    if c.get("education"):
        _heading(d, "Education")
        for e in c["education"]:
            p = d.add_paragraph()
            p.add_run(e.get("institution", "")).bold = True
            if e.get("dates"):
                p.add_run(f"  ({e['dates']})")
            if e.get("degree"):
                d.add_paragraph(e["degree"] + (f" – {e['grade']}" if e.get("grade") else ""))
    for title, key in (("Certifications", "certifications"), ("Activities", "extracurricular")):
        if c.get(key):
            _heading(d, title)
            for item in c[key]:
                d.add_paragraph(item, style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def cover_docx(c: dict[str, Any], sender: dict[str, Any]) -> bytes:
    d = _docx()
    d.add_paragraph().add_run(sender.get("name", "")).bold = True
    d.add_paragraph("  |  ".join(_contact_line(sender)))
    d.add_paragraph(c.get("greeting", ""))
    for para in c.get("paragraphs", []):
        d.add_paragraph(para)
    for line in c.get("closing", "").split("\n"):
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
