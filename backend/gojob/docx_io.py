"""Edit a .docx in place so the revised resume keeps the fonts and layout of the file the user uploaded.

Only the text inside existing runs is touched, so this works on the raw XML rather than rebuilding the file.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.shared import Pt

_PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)
# Text runs and tabs, in document order.
_PIECE = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:tab/>|<w:br(?:\s[^>]*)?/>")


def _unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class _Piece:
    start: int
    end: int
    text: str
    editable: bool


def _pieces(para: str) -> list[_Piece]:
    out = []
    for m in _PIECE.finditer(para):
        editable = m.group(0).startswith("<w:t") and not m.group(0).startswith("<w:tab")
        out.append(_Piece(m.start(), m.end(), _unescape(m.group(1) or "") if editable else " ", editable))
    return out


def _document_xml(data: bytes) -> tuple[zipfile.ZipFile, str]:
    zf = zipfile.ZipFile(io.BytesIO(data))
    try:
        return zf, zf.read("word/document.xml").decode("utf8")
    except KeyError as err:
        raise ValueError("This .docx file has no document body.") from err


def docx_to_text(data: bytes) -> str:
    """Plain text of a .docx, one line per paragraph, built from the same runs we later edit."""
    _, xml = _document_xml(data)
    lines = []
    for m in _PARA.finditer(xml):
        line = "".join(p.text for p in _pieces(m.group(0)))
        lines.append(re.sub(r"\s+", " ", line).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _find_loose(hay: str, needle: str) -> tuple[int, int] | None:
    """Find `needle` in `hay` ignoring differences in whitespace runs. Returns [start, end) in `hay`."""
    exact = hay.find(needle)
    if exact >= 0:
        return exact, exact + len(needle)
    mapping: list[int] = []
    collapsed = ""
    for i, ch in enumerate(hay):
        if ch.isspace():
            if collapsed.endswith(" ") or collapsed == "":
                continue
            collapsed += " "
        else:
            collapsed += ch
        mapping.append(i)
    want = re.sub(r"\s+", " ", needle).strip()
    at = collapsed.find(want) if want else -1
    if at < 0:
        return None
    return mapping[at], mapping[at + len(want) - 1] + 1


def _replace_in_paragraph(para: str, find: str, replace: str) -> str | None:
    ps = _pieces(para)
    full = "".join(p.text for p in ps)
    hit = _find_loose(full, find)
    if not hit:
        return None
    s, e = hit
    offset = 0
    placed = False
    edits: list[tuple[_Piece, str]] = []
    for p in ps:
        p_start, p_end = offset, offset + len(p.text)
        offset = p_end
        if not p.editable or p_end <= s or p_start >= e:
            continue
        before = p.text[: max(0, s - p_start)]
        after = p.text[max(0, min(len(p.text), e - p_start)) :]
        edits.append((p, before + ("" if placed else replace) + after))
        placed = True
    if not placed:
        return None
    out = para
    for piece, text in reversed(edits):
        out = f'{out[: piece.start]}<w:t xml:space="preserve">{_escape(text)}</w:t>{out[piece.end :]}'
    return out


def apply_changes_to_docx(data: bytes, changes: list[dict]) -> tuple[bytes, list[str]]:
    zf, xml = _document_xml(data)
    paras = _PARA.findall(xml)
    updated = list(paras)
    missed: list[str] = []
    for c in changes:
        done = False
        for i in range(len(updated)):
            nxt = _replace_in_paragraph(updated[i], c["find"], c["replace"])
            if nxt is not None:
                updated[i] = nxt
                done = True
                break
        if not done:
            missed.append(c["find"])
    it = iter(updated)
    # A callable replacement is inserted literally, so backslashes in the XML are safe.
    new_xml = _PARA.sub(lambda _m: next(it), xml)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in zf.infolist():
            payload = new_xml.encode("utf8") if item.filename == "word/document.xml" else zf.read(item.filename)
            dst.writestr(item, payload)
    return out.getvalue(), missed


def text_to_docx(text: str) -> bytes:
    """A clean, simple .docx for originals that were not Word files, and for cover letters."""
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    lines = text.replace("\r", "").split("\n")
    for i, raw in enumerate(lines):
        line = raw.strip()
        if i == 0 and len(line) < 60 and not re.search(r"[.!?]$", line):
            doc.add_heading(line, level=0)
        elif re.fullmatch(r"[A-Z][A-Z &/]{2,40}", line):
            p = doc.add_paragraph()
            p.add_run(line).bold = True
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
        elif m := re.match(r"^[•·▪●○◦*-]\s+(.*)$", line):
            doc.add_paragraph(m.group(1), style="List Bullet")
        else:
            p = doc.add_paragraph(line)
            p.paragraph_format.space_after = Pt(4 if line else 0)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


_SOFFICE = ["soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/bin/soffice", "/opt/homebrew/bin/soffice"]


def docx_to_pdf(data: bytes) -> bytes | None:
    """Convert with LibreOffice when it is installed, so the PDF matches the .docx exactly."""
    tmp = Path(tempfile.mkdtemp(prefix="jhc-"))
    try:
        src = tmp / "resume.docx"
        src.write_bytes(data)
        for binary in _SOFFICE:
            try:
                subprocess.run([binary, "--headless", "--convert-to", "pdf", "--outdir", str(tmp), str(src)], check=True, timeout=60, capture_output=True)
                return (tmp / "resume.pdf").read_bytes()
            except (OSError, subprocess.SubprocessError):
                continue
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
