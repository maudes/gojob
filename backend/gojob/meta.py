"""The stamp every AI result carries, so any output can be traced to the release, prompts and models that made it."""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

from . import skills as S
from .config import MAIN_MODEL, REVIEWER_MODEL, SKILLS_DIR, app_version


def _files() -> list[Path]:
    return [Path(__file__).with_name("prompts.py"), *sorted(p for p in SKILLS_DIR.glob("*.md") if p.name != "README.md")]


@lru_cache(maxsize=8)
def _digest(signature: tuple) -> str:
    digest = hashlib.sha256()
    for f in _files():
        digest.update(str(f.relative_to(SKILLS_DIR if f.is_relative_to(SKILLS_DIR) else f.parent)).encode())
        digest.update(f.read_bytes())
    return digest.hexdigest()[:10]


def prompt_hash() -> str:
    """A short fingerprint of every prompt (the skill files in skills/ and prompts.py).

    It changes by itself whenever a prompt is edited, so nobody has to remember to bump a number.
    Skills are read from disk on every use, so the fingerprint follows file changes without a restart.
    """
    return _digest(tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in _files()))


_INCLUDE = re.compile(r"\{\{include:([a-z0-9_#-]+)\}\}")


def _wanted(text: str, seen: set[str]) -> list[str]:
    """The skills and parts a text pastes in, and everything those paste in, each once."""
    found: list[str] = []
    for ref in _INCLUDE.findall(text):
        if ref not in seen:
            seen.add(ref)
            found.append(ref)
            found += _wanted(S.raw(ref), seen)
    return found


@lru_cache(maxsize=8)
def _skill_digests(signature: tuple) -> dict[str, str]:
    out = {}
    for name in S.names():
        own = (SKILLS_DIR / f"{name}.md").read_text("utf8")
        digest = hashlib.sha256(own.encode())
        for ref in sorted(_wanted(S.split_header(own)[1], set())):
            digest.update(ref.encode())
            digest.update(S.raw(ref).encode())
        out[name] = digest.hexdigest()[:6]
    return out


def skill_hashes() -> dict[str, str]:
    """One short fingerprint per skill: its own file plus every rule it pastes in with {{include:...}}.

    Two stamps can be compared to see which prompt changed. Editing a shared rule changes every skill that
    includes it; the shared file's own fingerprint shows where the edit was.
    """
    return dict(_skill_digests(tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in _files())))


def stamp() -> dict:
    return {
        "appVersion": app_version(),
        "promptHash": prompt_hash(),
        "skills": skill_hashes(),
        "models": {"main": MAIN_MODEL, "reviewer": REVIEWER_MODEL},
    }
