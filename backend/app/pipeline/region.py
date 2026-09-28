"""Region / time-zone eligibility for a candidate in India (UTC+5:30), plus the paid-only filter."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

POSITIVE = re.compile(
    r"\b(worldwide|anywhere|global(ly)?|international|any (location|country|timezone)|work from anywhere|"
    r"india|indian|asia|apac|asia[- ]pacific|south asia|ist\b|utc\s?\+\s?5:?30|gmt\s?\+\s?5:?30|"
    r"bengaluru|bangalore|mumbai|pune|hyderabad|chennai|delhi|noida|gurgaon|gurugram|kolkata)\b", re.I)
INDIA_CITY = re.compile(r"\b(bengaluru|bangalore|mumbai|pune|hyderabad|chennai|delhi|noida|gurgaon|gurugram|"
                        r"kolkata|ahmedabad|jaipur|kochi|chandigarh|indore|coimbatore)\b", re.I)

RESTRICTED = {
    "US": r"\b(us|u\.s\.a?\.?|usa|united states|america|north america|us[- ]only|us[- ]based)\b",
    "Canada": r"\bcanada\b",
    "UK": r"\b(uk|u\.k\.|united kingdom|england|britain)\b",
    "Europe": r"\b(europe|european union|eu|eea|emea|cet|cest|gmt\b)",
    "LATAM": r"\b(latam|latin america|south america|brazil|mexico|argentina|colombia|chile)\b",
    "Oceania": r"\b(australia|new zealand|aus|nz|anz)\b",
    "Africa": r"\b(africa|nigeria|kenya|south africa|egypt)\b",
    "Specific country": r"\b(germany|france|spain|portugal|netherlands|poland|ireland|italy|sweden|norway|denmark|"
                        r"finland|switzerland|austria|belgium|israel|japan|singapore|philippines|vietnam|"
                        r"indonesia|malaysia|pakistan|bangladesh|uae|dubai|saudi|turkey|romania|ukraine|czech|"
                        r"são paulo|sao paulo|bogota|buenos aires|lagos|nairobi|cape town)\b",
    "US city/state": r"\b(san francisco|bay area|mountain view|palo alto|menlo park|sunnyvale|san jose|oakland|"
                     r"los angeles|san diego|seattle|portland|new york|nyc|brooklyn|boston|chicago|austin|dallas|"
                     r"houston|denver|atlanta|miami|washington,? d\.?c|philadelphia|pittsburgh|salt lake|phoenix|"
                     r"minneapolis|detroit|columbus|nashville|raleigh|california|texas|washington state|colorado|"
                     r"florida|massachusetts|illinois|virginia|georgia|oregon|arizona|utah|ohio|michigan|"
                     r"pacific time|eastern time|central time|mountain time|pst|est|cst|mst)\b",
    "Europe/other city": r"\b(london|manchester|edinburgh|berlin|munich|hamburg|frankfurt|paris|amsterdam|"
                         r"rotterdam|dublin|madrid|barcelona|lisbon|porto|warsaw|krakow|prague|vienna|zurich|"
                         r"geneva|stockholm|copenhagen|oslo|helsinki|brussels|milan|rome|athens|budapest|"
                         r"bucharest|tallinn|toronto|vancouver|montreal|sydney|melbourne|tokyo|seoul|tel aviv|"
                         r"cairo|istanbul)\b",
}
US_STATE_CODE = re.compile(r",\s?(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|"
                           r"NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b")
DESC_RESTRICT = re.compile(
    r"(must|need to|should|required to)\s+(be\s+)?(located|based|reside|residing|live|living)\s+(in|within)\s+"
    r"(the\s+)?(us|u\.s\.|usa|united states|uk|europe|eu|canada|north america|latam)\b"
    r"|(us|u\.s\.|usa|uk|eu)[- ]based\s+(candidates\s+)?only"
    r"|only\s+(open|accepting|considering)\s+(to\s+)?(candidates|applicants)\s+(in|from|based in)\s+(the\s+)?"
    r"(us|usa|united states|uk|europe|eu|canada)"
    r"|(authori[sz]ed|eligible)\s+to\s+work\s+in\s+the\s+(us|united states|uk)\b"
    r"|(us|u\.s\.)\s+citizens?(hip)?\s+(only|required)"
    r"|(security|government)\s+clearance", re.I)
TZ_RANGE = re.compile(r"(?:utc|gmt)\s?([+-]\s?\d{1,2}(?::?\d{2})?)\s*(?:to|-|–|and)\s*(?:utc|gmt)?\s?([+-]\s?\d{1,2}"
                      r"(?::?\d{2})?)", re.I)
UNPAID = re.compile(r"\b(unpaid|no stipend|without stipend|volunteer(ing)? (role|position|opportunity)|"
                    r"equity[- ]only|no salary|pro bono|for exposure)\b", re.I)


@dataclass
class Eligibility:
    eligible: bool | None  # None = remote but region unspecified (shown with a warning)
    reason: str


def _tz(value: str) -> float:
    v = value.replace(" ", "")
    sign = -1 if v.startswith("-") else 1
    v = v.lstrip("+-")
    if ":" in v:
        h, m = v.split(":", 1)
    elif len(v) > 2:
        h, m = v[:-2], v[-2:]
    else:
        h, m = v, "0"
    return sign * (int(h) + int(m) / 60)


def is_unpaid(title: str, description: str) -> bool:
    return bool(UNPAID.search(f"{title}\n{description[:4000]}"))


def assess(job: Any, profile: dict[str, Any]) -> Eligibility:
    """job: NormJob-like object (title, location, regions, tz_restrictions, remote_type, description)."""
    cand = profile.get("candidate", {})
    my_off = float(cand.get("utc_offset", 5.5))
    tol = float(cand.get("timezone_tolerance_hours", 3.5))
    onsite_ok = [c.lower() for c in cand.get("onsite_ok_locations", [])]

    if is_unpaid(job.title, job.description):
        return Eligibility(False, "Unpaid / volunteer role (you want paid roles)")

    loc_blob = " ; ".join([job.location or "", *job.regions]).strip(" ;")
    loc_lower = loc_blob.lower()

    if job.remote_type in ("onsite", "hybrid"):
        if any(c in loc_lower for c in onsite_ok):
            return Eligibility(True, f"{job.remote_type.title()} in a preferred location ({job.location})")
        return Eligibility(False, f"{job.remote_type.title()} outside your preferred cities ({job.location or 'n/a'})")

    # Numeric time-zone restrictions (e.g. Himalayas)
    tzs = job.tz_restrictions or []
    if tzs:
        if any(abs(t - my_off) <= tol for t in tzs):
            if not loc_blob or POSITIVE.search(loc_blob) or loc_lower in ("worldwide", "anywhere"):
                return Eligibility(True, "Time-zone range includes IST")
        else:
            return Eligibility(False, f"Time zones UTC{min(tzs):+g}..UTC{max(tzs):+g} are far from IST")

    def tz_window(text: str) -> Eligibility | None:
        m = TZ_RANGE.search(text or "")
        if not m:
            return None
        try:
            lo, hi = sorted((_tz(m.group(1)), _tz(m.group(2))))
        except ValueError:
            return None
        if lo - tol <= my_off <= hi + tol:
            return Eligibility(True, f"Time-zone window UTC{lo:+g}..UTC{hi:+g} is workable from IST")
        return Eligibility(False, f"Requires overlap with UTC{lo:+g}..UTC{hi:+g}")

    if (w := tz_window(loc_blob)) is not None:
        return w

    if job.remote_type == "unknown" and INDIA_CITY.search(loc_blob) and not re.search(
            r"\b(remote|anywhere|worldwide|wfh|work from home)\b", loc_lower):
        # A city with no stated work mode is usually an office job: fine only if it's a city you'd commute to.
        if any(c in loc_lower for c in onsite_ok):
            return Eligibility(True, f"Located in a preferred city ({job.location}); work mode not stated")
        return Eligibility(None, f"Work mode not stated; based in {job.location[:60]} - may need relocation")

    if loc_blob and POSITIVE.search(loc_blob):
        return Eligibility(True, "Open to India / worldwide")

    restricted = [name for name, pat in RESTRICTED.items() if loc_blob and re.search(pat, loc_blob, re.I)]
    if loc_blob and US_STATE_CODE.search(loc_blob) and "US city/state" not in restricted:
        restricted.append("US city/state")
    if restricted:
        return Eligibility(False, f"Restricted to {', '.join(restricted)} ({loc_blob[:80]})")

    if (w := tz_window((job.description or "")[:3000])) is not None:
        return w

    desc = job.description or ""
    dm = DESC_RESTRICT.search(desc[:6000])
    if dm:
        return Eligibility(False, f"Description restricts location: \"{dm.group(0)[:80]}\"")

    if job.remote_type == "remote":
        if re.search(r"\b(worldwide|anywhere in the world|work from anywhere|all countries)\b", desc[:6000], re.I):
            return Eligibility(True, "Remote, open worldwide")
        return Eligibility(None, "Remote; location eligibility not stated - check before applying")

    if any(c in loc_lower for c in onsite_ok):
        return Eligibility(True, f"Located in a preferred city ({job.location})")
    if not loc_blob:
        return Eligibility(None, "Work location not stated")
    return Eligibility(False, f"Not remote and outside your preferred cities ({job.location})")
