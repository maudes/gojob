"""Paths, models and app version. The only place that reads the environment."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
FILES_DIR = DATA_DIR / "files"
DB_FILE = DATA_DIR / "db.json"
MANUAL_DIR = DATA_DIR / "manual"  # request and answer files of a subagent run (private, not committed)
SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Same file the Next.js app used, so an existing setup keeps working.
load_dotenv(ROOT / ".env.local")

MAIN_MODEL = os.environ.get("MAIN_MODEL") or "claude-opus-5-5"
REVIEWER_MODEL = os.environ.get("REVIEWER_MODEL") or "claude-haiku-5-5"

#: Bump when the shape of data/db.json changes. See store.MIGRATIONS.
SCHEMA_VERSION = 1


def runner() -> str:
    """Who answers a model call: "api" (default, the Claude API) or "subagent" (Claude Code subagents, through files).
    Set GOJOB_RUNNER=subagent for the command line tool only; see subagent_runner.py."""
    return "subagent" if os.environ.get("GOJOB_RUNNER") == "subagent" else "api"


def has_credentials() -> bool:
    return runner() == "subagent" or bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def app_version() -> str:
    """The release version. package.json is the single source of truth."""
    try:
        return json.loads((ROOT / "package.json").read_text("utf8"))["version"]
    except (OSError, KeyError, ValueError):
        return "0.0.0"
