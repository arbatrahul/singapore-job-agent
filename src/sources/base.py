from __future__ import annotations

import abc
import logging

from ..models import Job

log = logging.getLogger(__name__)


class Source(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def fetch(self, keywords: list[str]) -> list[Job]:
        """Fetch jobs for the given keyword queries. Must not raise — log and return []."""
        ...

    def safe_fetch(self, keywords: list[str]) -> list[Job]:
        try:
            jobs = self.fetch(keywords)
            log.info("source %s: %d jobs", self.name, len(jobs))
            return jobs
        except Exception as e:  # noqa: BLE001
            log.warning("source %s failed: %s", self.name, e)
            return []
