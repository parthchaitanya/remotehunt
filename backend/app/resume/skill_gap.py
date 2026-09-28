"""Skill-gap analysis: your skills vs. what target roles (and the live job market) ask for."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, utcnow
from ..skills import DISPLAY, ROLE_SKILLS, expand_implied

LEARNING_HINTS = {
    "sql": "Practice joins/window functions (e.g. SQLBolt, LeetCode SQL 50).",
    "excel": "Pivot tables, XLOOKUP and charts; build one analysis workbook.",
    "power_bi": "Build and publish one Power BI dashboard from a public dataset.",
    "tableau": "Publish a Tableau Public dashboard.",
    "statistics": "Descriptive stats, distributions, hypothesis tests, A/B testing basics.",
    "fastapi": "Wrap your FFI model in a FastAPI endpoint and deploy it.",
    "django": "Build a small CRUD app with auth using Django.",
    "rest_api": "Design and document a REST API (OpenAPI) for one of your projects.",
    "docker": "Containerize an existing project with a Dockerfile.",
    "aws": "Deploy a project on AWS (EC2 / Elastic Beanstalk / Lambda free tier).",
    "pytorch": "Train a small neural net in PyTorch; reproduce a tutorial end to end.",
    "deep_learning": "Complete a deep-learning course and ship one model project.",
    "rag": "Build a RAG app over your own documents (embeddings + vector store + LLM).",
    "embeddings": "Use sentence-transformers to build semantic search over a dataset.",
    "vector_db": "Store embeddings in FAISS/Chroma/pgvector for a RAG project.",
    "langchain": "Rebuild your LLM document reader with LangChain or LlamaIndex.",
    "prompt_engineering": "Write evals for prompts in your LLM project; iterate on them.",
    "testing": "Add pytest tests with coverage to an existing repo.",
    "pytest": "Add pytest tests with coverage to an existing repo.",
    "postgresql": "Swap MySQL for PostgreSQL in a project; learn indexes and EXPLAIN.",
    "git": "Keep all projects on GitHub with clear READMEs.",
    "data_cleaning": "Document a data-cleaning notebook on a messy public dataset.",
}


def market_demand(db: Session, role: str, days: int = 60) -> tuple[Counter, int]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(select(Job.job_skills).where(Job.role_family == role, Job.first_seen_at >= since)).all()
    c: Counter = Counter()
    for (skills,) in rows:
        c.update(set(skills or []))
    return c, len(rows)


def skill_gap(db: Session, parsed: dict[str, Any], target_roles: list[str]) -> list[dict[str, Any]]:
    have = expand_implied(set(parsed.get("skill_keys", [])))
    out = []
    for role in target_roles:
        rs = ROLE_SKILLS.get(role, {"core": [], "nice": []})
        demand, n_jobs = market_demand(db, role)
        wanted = set(rs["core"]) | set(rs["nice"])
        missing_core = [k for k in rs["core"] if k not in have]
        missing_nice = [k for k in rs["nice"] if k not in have]
        in_demand = [
            {"skill": DISPLAY.get(k, k), "key": k, "jobs": cnt, "pct": round(100 * cnt / n_jobs) if n_jobs else 0}
            for k, cnt in demand.most_common(40) if k not in have and cnt >= 2
        ][:12]
        coverage = len(wanted & have) / len(wanted) if wanted else 0
        priorities = []
        for k in sorted(missing_core, key=lambda k: -demand.get(k, 0)) + \
                [d["key"] for d in in_demand if d["key"] not in missing_core]:
            if k not in [p["key"] for p in priorities]:
                priorities.append({"key": k, "skill": DISPLAY.get(k, k), "hint": LEARNING_HINTS.get(k, "")})
        out.append({
            "role": role,
            "coverage": round(coverage * 100),
            "have": [DISPLAY[k] for k in rs["core"] + rs["nice"] if k in have],
            "missing_core": [DISPLAY[k] for k in missing_core],
            "missing_nice": [DISPLAY[k] for k in missing_nice],
            "market_jobs_analyzed": n_jobs,
            "in_demand_missing": in_demand,
            "priorities": priorities[:6],
        })
    return out
