"""Turn an uploaded resume or a fetched job page into plain text."""
from __future__ import annotations

import html as html_lib
import io
import json
import re
from urllib.parse import parse_qs, urlparse

import mammoth
from pypdf import PdfReader


def tidy(s: str) -> str:
    s = s.replace("\r", "")
    s = re.sub(r"[ \t]+\n", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def file_to_text(name: str, data: bytes) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return tidy("\n".join((page.extract_text() or "") for page in reader.pages))
    if lower.endswith(".docx"):
        return tidy(mammoth.extract_raw_text(io.BytesIO(data)).value)
    if re.search(r"\.(txt|md|markdown)$", lower):
        return tidy(data.decode("utf8", errors="replace"))
    raise ValueError("Unsupported file type. Use PDF, DOCX, TXT or MD.")


def _strip(html: str) -> str:
    html = re.sub(r"<(script|style|noscript|svg|nav|footer|header)\b.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"</(p|div|li|h[1-6]|tr|section|ul|ol)>|<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "- ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html_lib.unescape(html).replace("\xa0", " ")
    html = re.sub(r"[ \t]{2,}", " ", html)
    return re.sub(r"\n[ \t]+", "\n", html)


def html_to_text(html: str) -> str:
    # Many job boards embed the posting as JSON-LD; prefer it when present.
    for m in re.finditer(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, flags=re.I | re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data, *(data.get("@graph") or [])] if isinstance(data, dict) else []
        job = next((x for x in items if isinstance(x, dict) and x.get("@type") == "JobPosting"), None)
        if job and job.get("description"):
            loc = job.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            where = ((loc.get("address") or {}).get("addressLocality")) or ""
            org = (job.get("hiringOrganization") or {}).get("name")
            header = "\n".join(x for x in [job.get("title"), org, where] if x)
            return tidy(f"{header}\n\n{_strip(str(job['description']))}")
    return tidy(_strip(html))


_PRIVATE_HOST = re.compile(r"^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|\[)")


def is_safe_url(raw: str) -> str | None:
    """Only public http(s) pages; never the local network. Returns the URL when it is safe."""
    try:
        url = urlparse(raw)
    except ValueError:
        return None
    if url.scheme not in ("http", "https") or not url.hostname:
        return None
    host = url.hostname
    # A colon in the host means an IPv6 literal (urlparse drops the brackets the old check looked for).
    if host == "localhost" or host.endswith(".local") or ":" in host or _PRIVATE_HOST.match(host):
        return None
    return raw


def google_resume_url(raw: str) -> str | None:
    """The download address for a resume kept in Google Docs (as Word, so the layout survives) or Drive.
    Works only when the file is shared as "Anyone with the link"; the app never signs in to Google."""
    if not is_safe_url(raw):
        return None
    url = urlparse(raw)
    m = re.search(r"/d/([\w-]{20,})", url.path)
    file_id = m.group(1) if m else (parse_qs(url.query).get("id") or [None])[0]
    if not file_id:
        return None
    if url.hostname == "docs.google.com" and url.path.startswith("/document/"):
        return f"https://docs.google.com/document/d/{file_id}/export?format=docx"
    if url.hostname == "drive.google.com":
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return None


def drive_download_url(raw: str) -> str | None:
    """Turn a Google Docs / Sheets / Drive share link into a direct download address.
    Works only when the file is shared as "Anyone with the link"."""
    if not is_safe_url(raw):
        return None
    url = urlparse(raw)
    m = re.search(r"/d/([\w-]{20,})", url.path)
    file_id = m.group(1) if m else (parse_qs(url.query).get("id") or [None])[0]
    if url.hostname == "docs.google.com" and file_id:
        if url.path.startswith("/document/"):
            return f"https://docs.google.com/document/d/{file_id}/export?format=txt"
        if url.path.startswith("/spreadsheets/"):
            g = re.search(r"gid=(\d+)", f"{url.fragment}&{url.query}")
            return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv{f'&gid={g.group(1)}' if g else ''}"
    if url.hostname == "drive.google.com" and file_id:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return raw
