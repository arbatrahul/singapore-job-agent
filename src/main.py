from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from .config import env, profile
from .emailer import render_digest, send
from .filter import prefilter
from .models import Job
from .ranker import rank
from .sources.base import Source
from .sources.mycareersfuture import MyCareersFutureSource
from .sources.rss import RSSSource

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("sg-jobs-agent")

# Search keywords used against MyCareersFuture. Kept broad; filters narrow downstream.
SEARCH_KEYWORDS = [
    "generative ai",
    "agentic ai",
    "llm engineer",
    "ai engineer",
    "machine learning engineer",
    "ai engineering manager",
    "ai architect",
    "staff engineer",
    "principal engineer",
    "senior full stack engineer",
    "senior software engineer",
    "platform engineer",
]

TOP_N = 10


def _load_sources() -> list[Source]:
    sources: list[Source] = [MyCareersFutureSource()]

    linkedin_urls = env("LINKEDIN_RSS_URLS", "").strip()
    if linkedin_urls:
        feeds = [
            (f"linkedin-{i}", u.strip())
            for i, u in enumerate(linkedin_urls.split(","))
            if u.strip()
        ]
        if feeds:
            sources.append(RSSSource(feeds, name="linkedin"))

    extra_feeds_env = env("EXTRA_RSS_URLS", "").strip()
    if extra_feeds_env:
        feeds = []
        for i, pair in enumerate(extra_feeds_env.split(",")):
            pair = pair.strip()
            if not pair:
                continue
            if "|" in pair:
                label, url = pair.split("|", 1)
            else:
                label, url = f"feed-{i}", pair
            feeds.append((label.strip(), url.strip()))
        if feeds:
            sources.append(RSSSource(feeds, name="rss"))

    return sources


def run() -> int:
    started = datetime.now()
    log.info("digest run starting")

    p = profile()
    salary_floor = int(p.get("salary_floor_sgd_monthly", 8000))
    sources = _load_sources()
    log.info("loaded %d source(s): %s", len(sources), [s.name for s in sources])

    all_jobs: list[Job] = []
    for s in sources:
        all_jobs.extend(s.safe_fetch(SEARCH_KEYWORDS))
    log.info("fetched %d raw jobs from all sources", len(all_jobs))

    candidates = prefilter(all_jobs, floor_sgd_monthly=salary_floor)
    log.info("prefiltered to %d candidates", len(candidates))

    if not candidates:
        log.error(
            "prefilter returned 0 candidates — likely source outage or over-aggressive filter. "
            "Not sending an empty digest. Check source fetch logs above."
        )
        return 1

    ranked = rank(candidates)
    if not ranked:
        log.error(
            "ranker returned 0 results across %d candidates — every LLM batch failed. "
            "Check ANTHROPIC_API_KEY and account balance. Not sending an empty digest.",
            len(candidates),
        )
        return 1

    top = ranked[:TOP_N]
    log.info("ranked %d, sending top %d", len(ranked), len(top))

    html = render_digest(top, len(candidates), len(sources), salary_floor)
    subject = f"SG Jobs Digest — {started.strftime('%a %d %b')} ({len(top)} roles, top {top[0].score})"
    send(subject, html)
    log.info("digest run done in %.1fs", (datetime.now() - started).total_seconds())
    return 0


if __name__ == "__main__":
    sys.exit(run())
