"""Resume files on disk (uploaded original, master copy, per-JD tailored copy). Never sent to a model."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Literal

from . import config
from .docx_io import apply_changes_to_docx, text_to_docx
from .text_tools import apply_to_text


def _file(scope: str, ext: Literal["docx", "txt"]) -> Path:
    return config.FILES_DIR / f"{re.sub(r'[^a-z0-9-]', '', scope, flags=re.I)}.{ext}"


def _read(p: Path) -> bytes | None:
    try:
        return p.read_bytes()
    except OSError:
        return None


def _rm(p: Path) -> None:
    p.unlink(missing_ok=True)


def save_source(scope: str, kind: Literal["docx", "other"], data: bytes | str) -> None:
    config.FILES_DIR.mkdir(parents=True, exist_ok=True)
    _rm(_file(scope, "docx"))
    _rm(_file(scope, "txt"))
    target = _file(scope, "docx" if kind == "docx" else "txt")
    target.write_bytes(data if isinstance(data, bytes) else data.encode("utf8"))


def copy_source(src: str, dst: str) -> None:
    config.FILES_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("docx", "txt"):
        _rm(_file(dst, ext))
        if _file(src, ext).exists():
            shutil.copyfile(_file(src, ext), _file(dst, ext))


def has_source(scope: str) -> bool:
    return _file(scope, "docx").exists() or _file(scope, "txt").exists()


def apply_to_source(scope: str, changes: list[dict]) -> list[str]:
    """Apply accepted changes to the stored file for a scope. Returns finds that could not be placed."""
    docx = _read(_file(scope, "docx"))
    if docx is not None:
        data, missed = apply_changes_to_docx(docx, changes)
        _file(scope, "docx").write_bytes(data)
        return missed
    raw = _read(_file(scope, "txt"))
    if raw is None:
        return []
    text, missed = apply_to_text(raw.decode("utf8"), changes)
    _file(scope, "txt").write_text(text, "utf8")
    return missed


def export_docx(scope: str, fallback_text: str) -> bytes:
    """The resume as a .docx: the edited original when there is one, otherwise a clean rebuild."""
    docx = _read(_file(scope, "docx"))
    if docx is not None:
        return docx
    raw = _read(_file(scope, "txt"))
    return text_to_docx(raw.decode("utf8") if raw is not None else fallback_text)


def remove_source(scope: str) -> None:
    _rm(_file(scope, "docx"))
    _rm(_file(scope, "txt"))
