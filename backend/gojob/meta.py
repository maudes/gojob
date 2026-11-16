"""The stamp every AI result carries, so any output can be traced to the release, prompts and models that made it."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from .config import MAIN_MODEL, PROMPTS_DIR, REVIEWER_MODEL, app_version


@lru_cache(maxsize=1)
def prompt_hash() -> str:
    """A short fingerprint of every prompt (prompts.py and prompt_templates/*.md).

    It changes by itself whenever a prompt is edited, so nobody has to remember to bump a number.
    """
    digest = hashlib.sha256()
    files = [Path(__file__).with_name("prompts.py"), *sorted(PROMPTS_DIR.glob("*.md"))]
    for f in files:
        digest.update(f.name.encode())
        digest.update(f.read_bytes())
    return digest.hexdigest()[:10]


def stamp() -> dict:
    return {
        "appVersion": app_version(),
        "promptHash": prompt_hash(),
        "models": {"main": MAIN_MODEL, "reviewer": REVIEWER_MODEL},
    }
