"""Resume parser: PDF (pdfplumber) / DOCX (python-docx) -> structured JSON."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..skills import DISPLAY, expand_implied, extract_skills, normalize_skill_name

SECTION_ALIASES: dict[str, list[str]] = {
    "summary": ["professional summary", "summary", "profile", "profile summary", "about me", "about",
                "objective", "career objective", "career summary"],
    "education": ["education", "academic background", "academics", "education and training", "academic details"],
    "skills": ["technical skills", "skills", "core competencies", "key skills", "tech stack", "skills & tools",
               "skills and tools", "technical proficiency", "technologies"],
    "experience": ["experience", "work experience", "professional experience", "employment history",
                   "internship", "internships", "work history", "internship experience", "employment"],
    "projects": ["projects", "personal projects", "academic projects", "key projects", "selected projects"],
    "certifications": ["certifications", "certificates", "licenses & certifications", "courses",
                       "certifications & courses", "licenses and certifications"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments", "awards & achievements"],
    "extracurricular": ["extracurricular activities", "extracurricular", "extra-curricular activities",
                        "activities", "leadership", "volunteering", "positions of responsibility",
                        "leadership & activities"],
    "publications": ["publications", "research"],
    "languages": ["languages", "spoken languages"],
    "interests": ["interests", "hobbies", "hobbies & interests"],
}
_HEADING_LOOKUP = {alias: name for name, aliases in SECTION_ALIASES.items() for alias in aliases}

BULLET_RE = re.compile(r"^\s*([•●▪◦‣∙·\-\*–]|\d+[.)])\s+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{3,5}")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s|,;]+|(?:github\.com|linkedin\.com|x\.com|twitter\.com)/[^\s|,;]+",
                    re.I)
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RANGE_RE = re.compile(
    rf"((?:{MONTHS}\s+)?\d{{4}})\s*(?:[-–—]|to)\s*((?:{MONTHS}\s+)?\d{{4}}|present|current|now|ongoing)",
    re.I,
)
SINGLE_DATE_RE = re.compile(rf"(?:{MONTHS}\s+)?(?:19|20)\d{{2}}", re.I)
DEGREE_RE = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?e\.?|m\.?e\.?|b\.?sc|m\.?sc|bca|mca|mba|bba|ph\.?d|bachelor|master|diploma|"
    r"associate|high school|higher secondary|senior secondary|class xii|class x|hsc|ssc|cbse|icse)\b",
    re.I,
)


class ResumeParseError(ValueError):
    pass


@dataclass
class Extracted:
    text: str
    links: list[str] = field(default_factory=list)
    pages: int = 1
    file_type: str = ""


# --------------------------------------------------------------------------- extraction
def extract_pdf(data: bytes) -> Extracted:
    import pdfplumber

    texts: list[str] = []
    links: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
                for h in page.hyperlinks or []:
                    uri = h.get("uri")
                    if uri:
                        links.append(uri)
            pages = len(pdf.pages)
    except Exception as exc:
        raise ResumeParseError(f"Could not read PDF: {type(exc).__name__}") from exc
    return Extracted(text="\n".join(texts), links=_dedupe(links), pages=pages, file_type="pdf")


def extract_docx(data: bytes) -> Extracted:
    import docx
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ResumeParseError(f"Could not read DOCX: {type(exc).__name__}") from exc
    lines: list[str] = []
    for block in _iter_docx_blocks(document):
        lines.append(block)
    links = [rel.target_ref for rel in document.part.rels.values() if rel.reltype == RT.HYPERLINK]
    return Extracted(text="\n".join(lines), links=_dedupe(links), pages=1, file_type="docx")


def _iter_docx_blocks(document) -> list[str]:
    """Paragraphs and table cells in document order."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    out: list[str] = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text
            style = (para.style.name or "").lower() if para.style is not None else ""
            if text.strip() and ("list" in style or para._p.pPr is not None and para._p.pPr.numPr is not None):
                if not BULLET_RE.match(text):
                    text = "• " + text
            out.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                seen: set[int] = set()
                cells = []
                for cell in row.cells:
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    if cell.text.strip():
                        cells.append(cell.text.strip())
                if cells:
                    out.append("  ".join(cells))
    return out


def extract(data: bytes, filename: str) -> Extracted:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return extract_pdf(data)
    if ext == ".docx":
        return extract_docx(data)
    raise ResumeParseError("Unsupported file type; upload a .pdf or .docx")


# --------------------------------------------------------------------------- parsing
def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _clean_line(line: str) -> str:
    line = line.replace(" ", " ").replace("", "•").replace("​", "")
    return re.sub(r"[ \t]+", " ", line).strip()


def _heading_of(line: str) -> str | None:
    candidate = re.sub(r"[:\s]+$", "", line).strip().lower()
    candidate = re.sub(r"\s+", " ", candidate)
    if len(candidate) > 45:
        return None
    return _HEADING_LOOKUP.get(candidate)


def _is_bullet(line: str) -> bool:
    return bool(BULLET_RE.match(line))


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line, count=1).strip()


def classify_link(url: str) -> str:
    u = url.lower()
    if "github.com" in u:
        return "github"
    if "linkedin.com" in u:
        return "linkedin"
    if "twitter.com" in u or "//x.com" in u or u.startswith("x.com"):
        return "twitter"
    if u.startswith("mailto:"):
        return "email"
    if u.startswith("tel:"):
        return "phone"
    return "other"


def _parse_contact(header_lines: list[str], full_text: str, links: list[str]) -> dict[str, Any]:
    head = "\n".join(header_lines)
    email_m = EMAIL_RE.search(head) or EMAIL_RE.search(full_text)
    phone = None
    for m in PHONE_RE.finditer(head or full_text):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13:
            phone = m.group(0).strip()
            break
    all_links = list(links) + [m.group(0) for m in URL_RE.finditer(full_text)]
    classified: dict[str, Any] = {"github": None, "linkedin": None, "twitter": None, "portfolio": None, "other": []}
    for url in _dedupe(all_links):
        kind = classify_link(url)
        if kind in ("email", "phone"):
            continue
        if kind == "other":
            if classified["portfolio"] is None and not re.search(r"(github|linkedin)", url, re.I):
                classified["portfolio"] = url
            else:
                classified["other"].append(url)
        elif classified[kind] is None:
            classified[kind] = url
        else:
            classified["other"].append(url)
    # Profile names without URLs (e.g. "Github | Linkedin") still count as present when linked.
    return {"email": email_m.group(0) if email_m else None, "phone": phone, "links": classified}


def _split_title_org(header: str) -> tuple[str, str]:
    header = DATE_RANGE_RE.sub("", header).strip(" ,|–-")
    for sep in (" – ", " — ", " - ", " | ", " at ", " @ ", ", "):
        if sep in header:
            left, right = header.split(sep, 1)
            return left.strip(), right.strip()
    return header.strip(), ""


def _looks_like_header(line: str) -> bool:
    if _is_bullet(line):
        return False
    words = line.split()
    if DATE_RANGE_RE.search(line):
        return True
    if len(words) <= 14 and re.search(r"\s[–—|]\s|:\s", line) and line[:1].isupper():
        return True
    return False


def _group_entries(lines: list[str]) -> list[dict[str, Any]]:
    """Group a section's lines into entries: header, sub-lines, bullets (wrapped lines merged)."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last_kind = None  # "bullet" | "header" | "sub"
    for line in lines:
        if not line:
            continue
        if _is_bullet(line):
            if current is None:
                current = {"header": "", "sub": [], "bullets": []}
                entries.append(current)
            current["bullets"].append(_strip_bullet(line))
            last_kind = "bullet"
            continue
        if last_kind == "bullet" and current and current["bullets"]:
            prev = current["bullets"][-1]
            continuation = line[:1].islower() or not re.search(r"[.!?)]$", prev)
            if continuation and not DATE_RANGE_RE.search(line):
                current["bullets"][-1] = f"{prev} {line}"
                continue
        if current is None or last_kind == "bullet" or (last_kind == "sub" and _looks_like_header(line)
                                                        and current["sub"]):
            current = {"header": line, "sub": [], "bullets": []}
            entries.append(current)
            last_kind = "header"
        else:
            current["sub"].append(line)
            last_kind = "sub"
    return entries


def _entry_dates(text: str) -> str:
    m = DATE_RANGE_RE.search(text)
    if m:
        return f"{m.group(1)} – {m.group(2)}".strip()
    m2 = SINGLE_DATE_RE.search(text)
    return m2.group(0) if m2 else ""


def _techs_from_line(line: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[,|/•]", line) if p.strip()]
    if len(parts) >= 2 and all(len(p.split()) <= 4 for p in parts):
        return parts
    return []


def _parse_experience(lines: list[str]) -> list[dict[str, Any]]:
    out = []
    for e in _group_entries(lines):
        header = e["header"]
        title, org = _split_title_org(header)
        techs: list[str] = []
        extra = []
        for sub in e["sub"]:
            t = _techs_from_line(sub)
            if t and not techs:
                techs = t
            else:
                extra.append(sub)
        dates = _entry_dates(" ".join([header, *e["sub"]]))
        if not header and not e["bullets"]:
            continue
        out.append({"title": title, "organization": org, "dates": dates, "technologies": techs,
                    "details": extra, "bullets": e["bullets"]})
    return out


def _parse_projects(lines: list[str]) -> list[dict[str, Any]]:
    out = []
    for e in _group_entries(lines):
        header = e["header"]
        link_flag = bool(re.search(r"\b(github|demo|live|link)\s*$", header, re.I))
        clean = re.sub(r"\s*\b(github|demo|live|link)\s*$", "", header, flags=re.I).strip()
        name, desc = (clean.split(":", 1) + [""])[:2] if ":" in clean else (clean, "")
        techs: list[str] = []
        extra = []
        for sub in e["sub"]:
            t = _techs_from_line(sub)
            if t and not techs:
                techs = t
            else:
                extra.append(sub)
        out.append({"name": name.strip(), "description": desc.strip(), "technologies": techs,
                    "bullets": e["bullets"], "details": extra, "has_link": link_flag,
                    "dates": _entry_dates(header)})
    return out


def _parse_education(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in _group_entries(lines):
        block = [e["header"], *e["sub"]]
        institution = DATE_RANGE_RE.sub("", e["header"]).strip(" ,|–-")
        institution = SINGLE_DATE_RE.sub("", institution).strip(" ,|–-") if not DEGREE_RE.search(institution) \
            else institution
        degree = next((ln for ln in block if DEGREE_RE.search(ln)), "")
        if degree == e["header"] and e["sub"]:
            institution = e["sub"][0]
        grade = ""
        m = re.search(r"\b(cgpa|gpa|sgpa|percentage|score)\b[:\s]*([\d.]+%?(?:\s*/\s*[\d.]+)?)", " ".join(block), re.I)
        if m:
            grade = f"{m.group(1).upper()} {m.group(2)}"
        out.append({"institution": institution, "degree": DATE_RANGE_RE.sub("", degree).strip(" ,|–-"),
                    "dates": _entry_dates(" ".join(block)), "grade": grade,
                    "details": [b for b in e["bullets"]]})
    return out


def _parse_skills(lines: list[str]) -> dict[str, Any]:
    categories: dict[str, list[str]] = {}
    loose: list[str] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if ":" in line:
            cat, items = line.split(":", 1)
            if len(cat.split()) <= 5:
                vals = [v.strip() for v in re.split(r"[,;|•]", items) if v.strip()]
                categories.setdefault(cat.strip(), []).extend(vals)
                continue
        loose.extend(v.strip() for v in re.split(r"[,;|•]", line) if v.strip())
    if loose:
        categories.setdefault("Other", []).extend(loose)
    flat = _dedupe([v for vals in categories.values() for v in vals])
    return {"categories": categories, "all": flat}


def _paragraph_items(lines: list[str]) -> list[str]:
    """Items for free-text sections (achievements, activities): bullets or merged paragraphs."""
    items: list[str] = []
    for line in lines:
        if _is_bullet(line):
            items.append(_strip_bullet(line))
        elif items and (line[:1].islower() or not re.search(r"[.!?]$", items[-1])):
            items[-1] = f"{items[-1]} {line}"
        else:
            items.append(line)
    return items


def parse_text(text: str, links: list[str] | None = None, pages: int = 1) -> dict[str, Any]:
    lines = [_clean_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        raise ResumeParseError("No text could be extracted (is the file a scanned image?)")

    sections: dict[str, list[str]] = {}
    header_lines: list[str] = []
    current: str | None = None
    order: list[str] = []
    for line in lines:
        heading = _heading_of(line)
        if heading:
            current = heading
            if heading not in sections:
                sections[heading] = []
                order.append(heading)
            continue
        if current is None:
            header_lines.append(line)
        else:
            sections[current].append(line)

    name = ""
    for ln in header_lines[:3]:
        if not EMAIL_RE.search(ln) and not re.search(r"\d{3}", ln) and 1 <= len(ln.split()) <= 5:
            name = ln
            break

    contact = _parse_contact(header_lines, text, links or [])
    skills = _parse_skills(sections.get("skills", []))
    detected = extract_skills(text)
    # Map listed skills onto canonical keys too (keeps skills the taxonomy knows).
    listed_keys = [k for k in (normalize_skill_name(s) for s in skills["all"]) if k]
    skill_keys = _dedupe(listed_keys + detected)

    experience = _parse_experience(sections.get("experience", []))
    projects = _parse_projects(sections.get("projects", []))
    all_bullets = [b for e in experience for b in e["bullets"]] + [b for p in projects for b in p["bullets"]]

    parsed: dict[str, Any] = {
        "name": name,
        "contact": contact,
        "summary": " ".join(sections.get("summary", [])),
        "education": _parse_education(sections.get("education", [])),
        "skills": skills,
        "skill_keys": skill_keys,
        "skills_canonical": [DISPLAY[k] for k in skill_keys],
        "implied_skill_keys": sorted(expand_implied(skill_keys) - set(skill_keys)),
        "experience": experience,
        "projects": projects,
        "certifications": _paragraph_items(sections.get("certifications", [])),
        "achievements": _paragraph_items(sections.get("achievements", [])),
        "extracurricular": _paragraph_items(sections.get("extracurricular", [])),
        "languages": _paragraph_items(sections.get("languages", [])),
        "interests": _paragraph_items(sections.get("interests", [])),
        "sections_found": order,
        "stats": {
            "pages": pages,
            "word_count": len(re.findall(r"\b\w+\b", text)),
            "bullet_count": len(all_bullets),
            "char_count": len(text),
        },
    }
    return parsed


def parse_resume(data: bytes, filename: str) -> tuple[dict[str, Any], str]:
    """Parse an uploaded resume. Returns (parsed_json, raw_text)."""
    ex = extract(data, filename)
    parsed = parse_text(ex.text, ex.links, ex.pages)
    parsed["file_type"] = ex.file_type
    return parsed, ex.text


def all_bullets(parsed: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten resume lines worth reviewing, with their section."""
    out: list[dict[str, str]] = []
    if parsed.get("summary"):
        out.append({"section": "summary", "context": "Summary", "text": parsed["summary"]})
    for e in parsed.get("experience", []):
        ctx = " – ".join(x for x in (e.get("title"), e.get("organization")) if x)
        out += [{"section": "experience", "context": ctx, "text": b} for b in e.get("bullets", [])]
    for p in parsed.get("projects", []):
        out += [{"section": "projects", "context": p.get("name", ""), "text": b} for b in p.get("bullets", [])]
    for a in parsed.get("extracurricular", []) + parsed.get("achievements", []):
        out.append({"section": "activities", "context": "Activities", "text": a})
    return out
