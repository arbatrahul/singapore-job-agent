from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)

# MyCareersFuture (WSG) public search API — POST with JSON body.
API = "https://api.mycareersfuture.gov.sg/v2/search"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub(" ", s or "").replace("&nbsp;", " ").strip()


class MyCareersFutureSource(Source):
    """Primary SG source — government job board, no auth, stable POST search API."""

    name = "mycareersfuture"

    def __init__(self, per_keyword_limit: int = 30, timeout: float = 20.0):
        self.per_keyword_limit = per_keyword_limit
        self.timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _query(self, keyword: str, page: int = 0, limit: int = 30) -> dict[str, Any]:
        body = {"search": keyword, "sortBy": ["new_posting_date"]}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(
                API,
                json=body,
                params={"page": page, "limit": limit},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            r.raise_for_status()
            return r.json()

    def _to_job(self, raw: dict[str, Any]) -> Job | None:
        uuid = raw.get("uuid")
        title = raw.get("title") or ""
        if not uuid or not title:
            return None

        metadata = raw.get("metadata") or {}
        posted_company = raw.get("postedCompany") or {}
        hiring_company = raw.get("hiringCompany") or {}
        company_name = (
            (hiring_company.get("name") if hiring_company else None)
            or posted_company.get("name")
            or "Unknown"
        )

        salary = raw.get("salary") or {}
        salary_min = salary.get("minimum")
        salary_max = salary.get("maximum")
        salary_type = ((salary.get("type") or {}).get("salaryType") or "").lower()
        if "month" in salary_type:
            period = "monthly"
        elif "annum" in salary_type or "annual" in salary_type:
            period = "annual"
        else:
            period = None

        posted_at_str = metadata.get("newPostingDate") or metadata.get("updatedAt")
        posted_at = None
        if posted_at_str:
            try:
                posted_at = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
            except ValueError:
                posted_at = None

        # positionLevels e.g. [{"position": "Senior Executive"}, {"position": "Manager"}]
        position_levels = raw.get("positionLevels") or []
        seniority = ", ".join(p.get("position", "") for p in position_levels) or None

        employment = raw.get("employmentTypes") or []
        emp_type = ", ".join(e.get("employmentType", "") for e in employment) or None

        url = metadata.get("jobDetailsUrl") or f"https://www.mycareersfuture.gov.sg/job/{uuid}"

        desc = _strip_html(raw.get("description") or "")

        return Job(
            source=self.name,
            external_id=uuid,
            title=title.strip(),
            company=company_name.strip(),
            url=url,
            location="Singapore",
            description=desc[:4000],
            seniority=seniority,
            employment_type=emp_type,
            salary_min_sgd=int(salary_min) if salary_min else None,
            salary_max_sgd=int(salary_max) if salary_max else None,
            salary_period=period,
            posted_at=posted_at,
            raw={"uuid": uuid, "jobPostId": metadata.get("jobPostId")},
        )

    def fetch(self, keywords: list[str]) -> list[Job]:
        jobs: dict[str, Job] = {}
        for kw in keywords:
            try:
                data = self._query(kw, page=0, limit=self.per_keyword_limit)
            except Exception as e:  # noqa: BLE001
                log.warning("mcf query failed for %r: %s", kw, e)
                continue
            for r in data.get("results") or []:
                job = self._to_job(r)
                if job:
                    jobs[job.external_id] = job
        return list(jobs.values())
