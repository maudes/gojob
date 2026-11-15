"""Paths, models and the app version. One place, so nothing else reads the environment."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FILES_DIR = DATA_DIR / "files"
DB_FILE = DATA_DIR / "db.json"
PROMPTS_DIR = ROOT / "prompts"

# Same file the Next.js app used, so an existing setup keeps working.
load_dotenv(ROOT / ".env.local")

MAIN_MODEL = os.environ.get("MAIN_MODEL") or "claude-opus-5-5"
REVIEWER_MODEL = os.environ.get("REVIEWER_MODEL") or "claude-haiku-5-5"

#: Bump when the shape of data/db.json changes. See store.MIGRATIONS.
SCHEMA_VERSION = 1


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def app_version() -> str:
    """The release version. package.json is the single source of truth."""
    try:
        return json.loads((ROOT / "package.json").read_text("utf8"))["version"]
    except (OSError, KeyError, ValueError):
        return "0.0.0"
