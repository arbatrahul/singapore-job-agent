from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser

from ..models import Job
from .base import Source

log = logging.getLogger(__name__)


class RSSSource(Source):
    """Generic RSS source. Accepts a list of (label, url) tuples.

    Good for:
      - eFinancialCareers RSS feeds (https://www.efinancialcareers.sg/rss/)
      - LinkedIn saved-search RSS via user-generated service (RSS.app, Feedly)
      - Any other feed the user wants to plug in.
    """

    def __init__(self, feeds: Iterable[tuple[str, str]], name: str = "rss"):
        self.feeds = list(feeds)
        self.name = name

    def _to_job(self, label: str, entry) -> Job | None:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            return None

        summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        # Try to extract company from title: many feeds use "Title at Company" or "Title - Company"
        company = "Unknown"
        for sep in [" at ", " - ", " | ", " @ "]:
            if sep in title:
                maybe_title, maybe_company = title.rsplit(sep, 1)
                if len(maybe_company) < 80:
                    title, company = maybe_title.strip(), maybe_company.strip()
                    break

        posted_at = None
        for attr in ("published_parsed", "updated_parsed"):
            val = getattr(entry, attr, None)
            if val:
                try:
                    posted_at = datetime(*val[:6], tzinfo=timezone.utc)
                    break
                except (TypeError, ValueError):
                    pass

        external_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:16]

        return Job(
            source=f"{self.name}:{label}",
            external_id=external_id,
            title=title,
            company=company,
            url=link,
            location="Singapore",
            description=summary[:4000],
            posted_at=posted_at,
        )

    def fetch(self, keywords: list[str]) -> list[Job]:
        jobs: dict[str, Job] = {}
        for label, url in self.feeds:
            try:
                parsed = feedparser.parse(url)
            except Exception as e:  # noqa: BLE001
                log.warning("rss feed %s (%s) failed: %s", label, url, e)
                continue
            for entry in parsed.entries:
                job = self._to_job(label, entry)
                if job:
                    jobs[job.external_id] = job
        return list(jobs.values())
