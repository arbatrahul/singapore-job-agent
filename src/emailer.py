from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT, dry_run, env
from .models import RankedJob

log = logging.getLogger(__name__)

TEMPLATES = ROOT / "src" / "templates"


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


def send(subject: str, html: str) -> None:
    if dry_run():
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        path = out / f"digest-{datetime.now().strftime('%Y%m%d')}.html"
        path.write_text(html, encoding="utf-8")
        log.info("DRY_RUN: digest written to %s", path)
        return

    host = env("SMTP_HOST", required=True)
    port = int(env("SMTP_PORT", "587"))
    user = env("SMTP_USER", required=True)
    password = env("SMTP_PASSWORD", required=True)
    sender = env("DIGEST_FROM", user)
    to = env("DIGEST_TO", required=True)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(sender, [to], msg.as_string())
    log.info("digest sent successfully")
