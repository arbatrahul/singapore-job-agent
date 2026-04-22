from __future__ import annotations

import logging
import re
from typing import Iterable

from .config import profile
from .models import Job

log = logging.getLogger(__name__)

# Baseline anti-fit keyword patterns (case-insensitive substring match on title).
# These are generic disqualifiers. Domain-level anti-fit lives in profile.yaml:anti_fit
# and is merged at filter time via _anti_fit_terms().
_BASELINE_ANTI_FIT_TITLE_TERMS = [
    "intern", "internship", "apprentice", "graduate program", "fresh graduate",
    "junior", "associate engineer", "trainee",
    "sales engineer", "pre-sales", "solutions consultant",
]


def _anti_fit_terms() -> list[str]:
    """Merge baseline title anti-fit with profile.yaml:anti_fit domain terms."""
    terms = list(_BASELINE_ANTI_FIT_TITLE_TERMS)
    for entry in profile().get("anti_fit") or []:
        # Extract meaningful word tokens from "Junior / entry-level / associate positions" etc.
        tokens = [t.strip().lower() for t in re.split(r"[\s/,&]+", str(entry)) if len(t.strip()) >= 4]
        terms.extend(tokens)
    # Dedup while preserving order
    seen: set[str] = set()
    out = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def _title_has(title: str, terms: Iterable[str]) -> bool:
    low = title.lower()
    return any(t in low for t in terms)


def dedup(jobs: Iterable[Job]) -> list[Job]:
    """Collapse by (company, title) — prefer the entry with richest description."""
    best: dict[str, Job] = {}
    for j in jobs:
        key = j.dedup_key
        existing = best.get(key)
        if existing is None or len(j.description) > len(existing.description):
            best[key] = j
    return list(best.values())


def filter_salary(jobs: Iterable[Job], floor_sgd_monthly: int) -> list[Job]:
    """Keep jobs whose monthly salary floor is unknown OR >= threshold.

    We don't drop salary-unknown roles outright — MyCareersFuture omits salary for many
    senior roles. We flag them downstream for the ranker to judge.
    """
    kept = []
    for j in jobs:
        min_m = j.salary_min_sgd_monthly
        if min_m is None:
            kept.append(j)
            continue
        if min_m >= floor_sgd_monthly:
            kept.append(j)
    return kept


def filter_title(jobs: Iterable[Job]) -> list[Job]:
    """Drop obvious anti-fit titles. Keep the rest for the LLM ranker."""
    terms = _anti_fit_terms()
    kept = []
    for j in jobs:
        if _title_has(j.title, terms):
            log.debug("drop anti-fit title: %s @ %s", j.title, j.company)
            continue
        kept.append(j)
    return kept


def prefilter(jobs: Iterable[Job], floor_sgd_monthly: int) -> list[Job]:
    """Run dedup → anti-fit → salary floor. Returns candidate set for the ranker."""
    jobs = list(jobs)
    log.info("prefilter input: %d", len(jobs))
    jobs = dedup(jobs)
    log.info("after dedup: %d", len(jobs))
    jobs = filter_title(jobs)
    log.info("after title filter: %d", len(jobs))
    jobs = filter_salary(jobs, floor_sgd_monthly)
    log.info("after salary filter: %d", len(jobs))
    return jobs
