from __future__ import annotations

import logging
from datetime import datetime

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import ROOT, dry_run, env
from .models import RankedJob

log = logging.getLogger(__name__)

TEMPLATES = ROOT / "src" / "templates"
RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_FROM = "SG Jobs Digest <onboarding@resend.dev>"


def render_digest(
    ranked: list[RankedJob],
    total_candidates: int,
    source_count: int,
    salary_floor: int,
) -> str:
    env_ = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(enabled_extensions=("html", "j2", "htm")),
    )
    tmpl = env_.get_template("digest.html.j2")
    return tmpl.render(
        ranked=ranked,
        total_candidates=total_candidates,
        source_count=source_count,
        salary_floor=salary_floor,
        date=datetime.now().strftime("%a, %d %b %Y"),
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _post_resend(api_key: str, payload: dict) -> dict:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Resend {r.status_code}: {r.text[:300]}")
        return r.json()


def send(subject: str, html: str) -> None:
    if dry_run():
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        path = out / f"digest-{datetime.now().strftime('%Y%m%d')}.html"
        path.write_text(html, encoding="utf-8")
        log.info("DRY_RUN: digest written to %s", path)
        return

    api_key = env("RESEND_API_KEY", required=True)
    sender = env("DIGEST_FROM", DEFAULT_FROM) or DEFAULT_FROM
    to = env("DIGEST_TO", required=True)

    payload = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    resp = _post_resend(api_key, payload)
    log.info("digest sent (resend id=%s)", resp.get("id", "?"))
