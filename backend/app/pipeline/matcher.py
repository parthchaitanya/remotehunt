"""Job <-> resume match score (0-100) with reasons and missing skills.

score = 45% semantic similarity (sentence-transformers all-MiniLM-L6-v2)
      + 35% skill keyword overlap
      + 20% title fit with target roles
      - experience/seniority penalty
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from ..skills import DISPLAY, expand_implied, extract_skills, role_family, skill_counts

log = logging.getLogger(__name__)

SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|staff|principal|lead|head of|director|vp|vice president|manager|"
                          r"architect|chief)\b", re.I)
JUNIOR_TITLE = re.compile(r"\b(intern(ship)?|junior|jr\.?|entry[- ]level|graduate|fresher|trainee|associate|new grad|"
                          r"apprentice)\b", re.I)
NON_TECH_TITLE = re.compile(
    r"\b(recruit(er|ing|ment)|talent|sales|account (executive|manager|director)|business development|marketing|"
    r"customer (success|support|service)|support specialist|designer|legal|counsel|attorney|paralegal|finance|"
    r"accountant|accounting|controller|payroll|hr|people partner|people ops|office manager|executive assistant|"
    r"operations (manager|associate|specialist)|supply chain|procurement|copywriter|content writer|social media|"
    r"community manager|partnerships?|revenue|bookkeeper|nurse|physician|therapist|driver|warehouse|teacher|tutor)\b",
    re.I)
YEARS_RE = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)\b[^.\n]{0,40}?"
                      r"\b(experience|exp\b|professional|industry|in\s+(a|an)?\s*\w+)", re.I)


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    cos_range = (0.15, 0.65)  # typical resume<->JD cosine spread for MiniLM

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        try:  # use the local cache without any network round-trips when the model is already downloaded
            self.model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
        except Exception:
            self.model = SentenceTransformer(model_name, device="cpu")
        self.name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, batch_size=32, normalize_embeddings=True,
                                            show_progress_bar=False))


class HashingEmbedder:
    """Dependency-free fallback (bag of hashed word uni/bi-grams). Used if the model can't load."""

    name = "hashing-fallback"
    cos_range = (0.12, 0.42)  # measured on real postings: p10 ~0.10, median ~0.33, p99 ~0.38

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            words = re.findall(r"[a-z0-9+#]+", (t or "").lower())
            grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
            for g in grams:
                h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16)
                out[i, h % self.dim] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


_embedder: Embedder | None = None
_emb_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    with _emb_lock:
        if _embedder is None:
            from ..config import get_settings

            if get_settings().embedding_backend == "hashing":
                _embedder = HashingEmbedder()
                return _embedder
            try:
                _embedder = SentenceTransformerEmbedder(get_settings().embedding_model)
                log.info("Loaded embedding model %s", _embedder.name)
            except Exception as exc:
                log.warning("Embedding model unavailable (%s); using hashing fallback", type(exc).__name__)
                _embedder = HashingEmbedder()
        return _embedder


@dataclass
class MatchResult:
    score: int
    semantic: float
    keyword: float
    title: float
    penalty: int
    role_family: str
    reasons: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    job_skills: list[str] = field(default_factory=list)

    def breakdown(self) -> dict[str, Any]:
        return {"semantic": round(self.semantic, 3), "keyword": round(self.keyword, 3), "title": round(self.title, 3),
                "penalty": self.penalty}


def required_years(text: str) -> int | None:
    years = []
    for m in YEARS_RE.finditer(text or ""):
        lo = int(m.group(1))
        if 0 < lo <= 20:
            years.append(lo)
    return min(years) if years else None


class Matcher:
    def __init__(self, resume_parsed: dict[str, Any], resume_text: str, profile: dict[str, Any],
                 embedder: Embedder | None = None):
        self.profile = profile
        cand = profile.get("candidate", {})
        self.target_roles: list[str] = cand.get("target_roles") or []
        self.role_keywords: dict[str, list[str]] = profile.get("search", {}).get("role_keywords") or {}
        self.max_years = int(cand.get("max_years_required", 2))
        self.embedder = embedder or get_embedder()
        self.resume_skills = expand_implied(set(resume_parsed.get("skill_keys", [])) | set(extract_skills(resume_text)))
        focus = " ".join(self.target_roles)
        self.resume_vec = self.embedder.encode([f"{focus}. {resume_text[:4000]}"])[0]

    @staticmethod
    def job_text(title: str, description: str) -> str:
        return f"{title}. {title}. {(description or '')[:3000]}"

    def score_many(self, jobs: list[dict[str, Any]]) -> list[MatchResult]:
        if not jobs:
            return []
        vecs = self.embedder.encode([self.job_text(j["title"], j.get("description", "")) for j in jobs])
        return [self._score(j, float(np.dot(v, self.resume_vec))) for j, v in zip(jobs, vecs)]

    def score(self, job: dict[str, Any]) -> MatchResult:
        return self.score_many([job])[0]

    def _title_fit(self, title: str) -> tuple[float, str, str]:
        t = title.lower()
        fam = role_family(title, self.role_keywords)
        for role in self.target_roles:
            if role.lower() in t:
                return 1.0, role, f"Title matches your target role '{role}'"
        if fam and fam in self.target_roles:
            return 0.7, fam, f"Title fits the {fam} track"
        if re.search(r"\b(engineer|developer|analyst|scientist)\b", t):
            return 0.3, fam, ""
        return 0.0, fam, ""

    def _score(self, job: dict[str, Any], cos: float) -> MatchResult:
        title = job["title"]
        desc = job.get("description", "") or ""
        reasons: list[str] = []

        # Semantic similarity, rescaled by the embedder's typical resume<->JD cosine range.
        lo, hi = getattr(self.embedder, "cos_range", (0.15, 0.65))
        sem = float(np.clip((cos - lo) / (hi - lo), 0, 1))
        if sem >= 0.6:
            reasons.append(f"Strong semantic match with your resume ({cos:.2f})")
        elif sem >= 0.35:
            reasons.append(f"Moderate semantic match with your resume ({cos:.2f})")

        # Keyword / skill overlap (skills in the title count double).
        counts = skill_counts(f"{title}\n{desc}")
        title_sk = set(extract_skills(title))
        tags_sk = set(extract_skills(" ".join(job.get("tags") or [])))
        job_sk = set(counts) | title_sk | tags_sk
        job_sk.discard("communication")
        if job_sk:
            weights = {k: (2.0 if k in title_sk else 1.0) + min(counts.get(k, 0), 3) * 0.25 for k in job_sk}
            total = sum(weights.values())
            matched = {k for k in job_sk if k in self.resume_skills}
            kw = sum(weights[k] for k in matched) / total
        else:
            matched, weights, kw = set(), {}, 0.35
        missing = sorted(job_sk - self.resume_skills, key=lambda k: -weights.get(k, 0))
        if matched:
            top = sorted(matched, key=lambda k: -weights.get(k, 0))[:6]
            reasons.append(f"You have {len(matched)}/{len(job_sk)} skills it mentions: "
                           + ", ".join(DISPLAY.get(k, k) for k in top))

        tfit, fam, treason = self._title_fit(title)
        if treason:
            reasons.append(treason)

        # Experience / seniority / function
        penalty = 0
        if NON_TECH_TITLE.search(title) and not re.search(r"\b(engineer|developer|scientist|data analyst)\b",
                                                           title, re.I):
            tfit = 0.0
            fam = ""
            penalty += 25
            reasons.append("Non-technical role (outside your target roles)")
        years = required_years(desc)
        if JUNIOR_TITLE.search(title):
            reasons.append("Entry-level / internship friendly")
            tfit = min(1.0, tfit + 0.15)
        if SENIOR_TITLE.search(title) and not JUNIOR_TITLE.search(title):
            penalty += 15
            reasons.append("Senior-level title (you're early-career)")
        if years is not None and years > self.max_years:
            p = 8 if years <= 3 else 15 if years <= 5 else 22
            penalty += p
            reasons.append(f"Asks for {years}+ years of experience")
        penalty = min(penalty, 40)

        raw = 100 * (0.45 * sem + 0.35 * kw + 0.20 * tfit)
        score = int(round(max(0.0, min(100.0, raw - penalty))))
        return MatchResult(score=score, semantic=sem, keyword=kw, title=tfit, penalty=penalty, role_family=fam,
                           reasons=reasons, matched_skills=[DISPLAY.get(k, k) for k in sorted(matched)],
                           missing_skills=[DISPLAY.get(k, k) for k in missing[:12]],
                           job_skills=sorted(job_sk))
