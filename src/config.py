from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def profile() -> dict[str, Any]:
    with open(ROOT / "profile.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and not val:
        raise RuntimeError(f"Required env var {key} is not set")
    return val or ""


def dry_run() -> bool:
    return env("DRY_RUN", "0") == "1"
