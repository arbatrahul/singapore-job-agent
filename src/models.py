from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Job(BaseModel):
    """Normalized job record across all sources."""

    source: str
    external_id: str
    title: str
    company: str
    url: str
    location: str = "Singapore"
    description: str = ""
    seniority: Optional[str] = None
    employment_type: Optional[str] = None
    salary_min_sgd: Optional[int] = None
    salary_max_sgd: Optional[int] = None
    salary_period: Optional[str] = None  # "monthly" | "annual"
    posted_at: Optional[datetime] = None
    raw: dict = Field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return f"{self.company.strip().lower()}::{self.title.strip().lower()}"

    @property
    def salary_min_sgd_monthly(self) -> Optional[int]:
        return self._to_monthly(self.salary_min_sgd)

    @property
    def salary_max_sgd_monthly(self) -> Optional[int]:
        return self._to_monthly(self.salary_max_sgd)

    def _to_monthly(self, val: Optional[int]) -> Optional[int]:
        if val is None:
            return None
        if self.salary_period == "annual":
            return val // 12
        return val


class RankedJob(BaseModel):
    job: Job
    score: int  # 0-100
    why_fits: str
    flags: list[str] = Field(default_factory=list)  # e.g. ["salary_unknown"]
