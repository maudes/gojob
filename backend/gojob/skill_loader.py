"""Loads skills/<name>.md (every prompt) or one `## part:` of it; pastes {{include:...}}, fills {{variable}}.
Read from disk on every use. Format: skills/README.md."""
from __future__ import annotations

import re
from pathlib import Path

from .config import SKILLS_DIR

_REF = re.compile(r"^([a-z0-9_-]+)(#[a-z0-9_-]+)?$")
_INCLUDE = re.compile(r"\{\{include:([a-z0-9_#-]+)\}\}")
_VARIABLE = re.compile(r"\{\{(\w+)\}\}")
_PART = re.compile(r"^## part: ([a-z0-9_-]+)[ \t]*$", re.M)


def split_header(text: str) -> tuple[dict[str, str], str]:
    """Separate the `---` header (simple `key: value` lines) from the prompt text."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            meta = {}
            for line in text[4:end].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            return meta, text[end + 5 :]
    return {}, text


def _file(name: str) -> Path:
    return SKILLS_DIR / f"{name}.md"


def _load(name: str) -> tuple[dict[str, str], str, dict[str, str]]:
    """(header, main prompt, {part name: text}) of one skill file."""
    if not _REF.match(name) or "#" in name:
        raise ValueError(f"Not a skill name: {name!r}")
    path = _file(name)
    if not path.exists():
        raise ValueError(f"No skill called {name!r}")
    meta, body = split_header(path.read_text("utf8"))
    pieces = _PART.split(body)  # [main, part1, text1, part2, text2, ...]
    parts: dict[str, str] = {}
    for pname, text in zip(pieces[1::2], pieces[2::2]):
        if pname in parts:
            raise ValueError(f"Skill {name!r} has two parts called {pname!r}")
        parts[pname] = text.strip()
    return meta, pieces[0].strip(), parts


def raw(ref: str) -> str:
    """The text of a skill (or of one part, as "name#part"), includes not yet pasted."""
    match = _REF.match(ref)
    if not match:
        raise ValueError(f"Not a skill name: {ref!r}")
    name, part = match.group(1), (match.group(2) or "")[1:]
    _, main, parts = _load(name)
    if not part:
        return main
    if part not in parts:
        raise ValueError(f"Skill {name!r} has no part {part!r}")
    return parts[part]


def info(name: str) -> dict[str, str]:
    """The header of a skill file: name, description, variables, used-by."""
    return _load(name)[0]


def parts(name: str) -> list[str]:
    return list(_load(name)[2])


def names() -> list[str]:
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md") if p.name != "README.md")


def _expand(ref: str, depth: int = 0) -> str:
    if depth > 5:
        raise ValueError(f"Skills include each other too deeply at {ref!r}")
    return _INCLUDE.sub(lambda m: _expand(m.group(1), depth + 1), raw(ref))


def skill(ref: str, **variables: object) -> str:
    """The finished prompt text for `ref` ("name" or "name#part"): includes pasted, variables filled in."""
    text = _expand(ref)
    missing = {m for m in _VARIABLE.findall(text) if m not in variables}
    if missing:
        raise ValueError(f"Skill {ref!r} needs: {', '.join(sorted(missing))}")
    # One pass, so a value that itself contains {{x}} is never filled in a second time.
    return _VARIABLE.sub(lambda m: str(variables[m.group(1)]), text)
