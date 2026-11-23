"""Text helpers: contact redaction, word-for-word quote check, applying changes, layout lock."""
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


# ---------- Layout lock: which resume lines a tracked change may never touch ----------

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATE_RANGE = re.compile(rf"(?:{_MONTH}\s+)?(?:19|20)\d{{2}}\s*[–—-]\s*(?:(?:{_MONTH}\s+)?(?:19|20)\d{{2}}|Present|Current|Now)\b", re.I)


_SCHOOL = re.compile(r"\b(University|College|Institute|School|Academy|B\.?A\.?|B\.?S\.?|M\.?A\.?|M\.?S\.?|MBA|Ph\.?D|Bachelor|Master)\b")
_YEAR_FIRST = re.compile(r"^(?:19|20)\d{2}\b")


def is_layout_line(line: str, first: bool = False, second: bool = False) -> bool:
    """True for lines that are structure, not wording: the name, the contact line, section titles, and the
    employer, job title, date, location, school and degree lines. A tracked change never touches these."""
    s = line.strip()
    if not s:
        return False
    words = len(s.split())
    letters = re.sub(r"[^A-Za-z]", "", s)
    if first:
        return True
    if second and re.search(r"[·|•]", s) and "[email]" not in s:
        return False  # the headline under the name may be reworded, even when it is short
    if letters and letters.isupper() and words <= 5:
        return True  # SUMMARY, EXPERIENCE, SELECTED PROJECTS
    if "[email]" in s or "[phone]" in s or "linkedin" in s.lower():
        return True
    if words <= 14 and _DATE_RANGE.search(s):
        return True  # "Software Product Manager ... Nov 2025 – Present"
    if words <= 14 and (_SCHOOL.search(s) or _YEAR_FIRST.match(s)):
        return True  # school and degree lines; award lines that start with a year
    return words <= 8 and ":" not in s and not s.endswith(".")  # employer, short titles


def editable_lines(resume: str) -> list[str]:
    """The resume lines wording changes may target: sentences and bullets, headline, summary, skills."""
    lines = [ln.strip() for ln in resume.split("\n") if ln.strip()]
    return [ln for i, ln in enumerate(lines) if not is_layout_line(ln, i == 0, i == 1)]


def keep_editable(changes: list[dict], resume: str) -> tuple[list[dict], int]:
    """Drop tracked changes whose text sits on a layout line. Returns the kept changes and how many were dropped."""
    lines = [ln.strip() for ln in resume.split("\n") if ln.strip()]
    flags = [is_layout_line(ln, i == 0, i == 1) for i, ln in enumerate(lines)]
    norm = [normalise(ln) for ln in lines]
    kept = []
    for c in changes:
        want = normalise(c.get("find", ""))
        at = next((i for i, ln in enumerate(norm) if want and want in ln), None)
        if at is None or not flags[at]:
            kept.append(c)
    return kept, len(changes) - len(kept)


def today() -> str:
    return date.today().isoformat()
