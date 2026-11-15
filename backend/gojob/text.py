"""Text helpers: contact redaction, verbatim checks, applying accepted changes."""
from __future__ import annotations

import re
from datetime import date

_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"(?<![\w/.-])\+?[0-9][0-9\s().-]{7,}[0-9](?![\w/-])")
_YEAR_RANGE = re.compile(r"^[0-9]{4}\s*[-–.]\s*[0-9]{4}$")


def redact(text: str) -> str:
    """Replace contact details with placeholders. Applied before any text reaches a model or the screen."""

    def phone(m: re.Match[str]) -> str:
        digits = re.sub(r"[^0-9]", "", m.group(0))
        # Leave years and year ranges such as "2019 - 2023" alone.
        if len(digits) < 9 or _YEAR_RANGE.match(m.group(0).strip()):
            return m.group(0)
        return "[phone]"

    return _PHONE.sub(phone, _EMAIL.sub("[email]", text))


def normalise(s: str) -> str:
    s = s.lower()
    s = re.sub("[‘’]", "'", s)
    s = re.sub("[“”]", '"', s)
    s = re.sub("[‐‑‒–—]", "-", s)
    s = re.sub(r"^[\s•·▪●○◦*\-]+", "", s, flags=re.M)
    return re.sub(r"\s+", " ", s).strip()


def is_verbatim(quote: str, source: str) -> bool:
    """True when `quote` appears word for word in `source`, ignoring whitespace and bullet glyphs."""
    q = normalise(quote)
    if not q:
        return True
    return q in normalise(source)


def apply_to_text(text: str, changes: list[dict]) -> tuple[str, list[str]]:
    """Apply accepted changes to plain text. Returns the new text and the finds that could not be placed."""
    missed: list[str] = []
    out = text
    for c in changes:
        find = c.get("find", "")
        if find and find in out:
            out = out.replace(find, c["replace"], 1)
        else:
            missed.append(find)
    return out, missed


def today() -> str:
    return date.today().isoformat()
