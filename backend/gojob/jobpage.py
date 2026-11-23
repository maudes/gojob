"""Read a job posting from its link: the board's own API, then the page, then Jina Reader.
JD_READER_FALLBACK=off skips Jina."""
from __future__ import annotations

import os
import re
from typing import Callable
from urllib.parse import urlparse

import httpx

from .extract import html_to_text, is_safe_url

HEADERS = {"user-agent": "Mozilla/5.0 (compatible; job-page-reader)"}
MIN_CHARS = 600


def _get_json(url: str) -> dict | None:
    try:
        res = httpx.get(url, headers={**HEADERS, "accept": "application/json"}, timeout=10, follow_redirects=True)
        return res.json() if res.status_code < 400 else None
    except (httpx.HTTPError, ValueError):
        return None


def _with_title(title, company, location, body: str) -> str:
    head = "\n".join(x for x in (title, company, location) if isinstance(x, str) and x)
    return "\n\n".join(x for x in (head, body) if x)


def _greenhouse(url: str) -> str | None:
    m = re.match(r"https://(?:job-boards|boards)\.greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not m:
        return None
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{m[1]}/jobs/{m[2]}?questions=false")
    if not data:
        return None
    # Greenhouse returns its HTML entity-encoded, so decode once before stripping tags.
    html = str(data.get("content") or data.get("description") or "").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
    return _with_title(data.get("title"), data.get("company_name"), (data.get("location") or {}).get("name"), html_to_text(html))


def _ashby(url: str) -> str | None:
    m = re.match(r"https://jobs\.ashbyhq\.com/([^/]+)/([a-f0-9-]{36})", url)
    if not m:
        return None
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{m[1]}")
    job = next((j for j in (data or {}).get("jobs", []) if m[2] in str(j.get("jobUrl", ""))), None)
    if not job:
        return None
    body = html_to_text(str(job.get("descriptionHtml") or "")) or str(job.get("descriptionPlain") or "")
    return _with_title(job.get("title"), m[1], job.get("location"), body)


def _workday(url: str) -> str | None:
    m = re.match(r"https://([^.]+\.\w+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/([^?#]+)", url)
    if not m:
        return None
    host, board, path = m.groups()
    tenant = host.split(".")[0]
    data = _get_json(f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{board}/job/{path}")
    info = (data or {}).get("jobPostingInfo")
    if not info:
        return None
    org = ((data or {}).get("hiringOrganization") or {}).get("name") or tenant
    return _with_title(info.get("title"), org, info.get("location"), html_to_text(str(info.get("jobDescription") or "")))


def _lever(url: str) -> str | None:
    m = re.match(r"https://jobs\.(?:eu\.)?lever\.co/([^/]+)/([a-f0-9-]{36})", url)
    if not m:
        return None
    api = "api.eu.lever.co" if "jobs.eu.lever.co" in url else "api.lever.co"
    data = _get_json(f"https://{api}/v0/postings/{m[1]}/{m[2]}")
    if not data:
        return None
    parts = [str(data.get("descriptionPlain") or "")]
    for section in data.get("lists") or []:
        parts.append(f"{section.get('text', '')}\n{html_to_text(str(section.get('content') or ''))}")
    if data.get("additional"):
        parts.append(html_to_text(str(data["additional"])))
    return _with_title(data.get("text"), m[1], (data.get("categories") or {}).get("location"), "\n\n".join(p for p in parts if p))


def _smartrecruiters(url: str) -> str | None:
    m = re.match(r"https://jobs\.smartrecruiters\.com/([^/]+)/([^/?#]+)", url)
    if not m:
        return None
    lead = re.match(r"(\d+)", m[2])
    data = _get_json(f"https://api.smartrecruiters.com/v1/companies/{m[1]}/postings/{lead.group(1) if lead else m[2]}")
    sections = ((data or {}).get("jobAd") or {}).get("sections")
    if not sections:
        return None
    keys = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")
    body = "\n\n".join(t for t in (html_to_text(str((sections.get(k) or {}).get("text") or "")) for k in keys) if t)
    return _with_title(data.get("name"), (data.get("company") or {}).get("name") or m[1], (data.get("location") or {}).get("city"), body)


def _direct(url: str) -> str | None:
    try:
        res = httpx.get(url, headers={**HEADERS, "accept": "text/html"}, timeout=12, follow_redirects=True)
    except httpx.HTTPError:
        return None
    # A closed posting often redirects to the company home page; that is not the job.
    if res.status_code >= 400 or urlparse(str(res.url)).hostname != urlparse(url).hostname:
        return None
    return html_to_text(res.text)


_TAIL_CUTS = ["### 類似職缺", "### Similar Jobs", "## 聯絡方式", "這些工作也很適合你"]


def _jina(url: str) -> str | None:
    if os.environ.get("JD_READER_FALLBACK", "").lower() == "off":
        return None
    try:
        key = os.environ.get("JINA_API_KEY")
        res = httpx.get(f"https://r.jina.ai/{url}", headers={"authorization": f"Bearer {key}"} if key else {}, timeout=25, follow_redirects=True)
        if res.status_code >= 400:
            return None
        text = res.text
    except httpx.HTTPError:
        return None
    # Jina reports the address it ended on. A different site means the posting redirected away.
    landed = re.search(r"Final URL:\s*(\S+)", text)
    if landed and urlparse(landed.group(1)).hostname != urlparse(url).hostname:
        return None
    for cut in _TAIL_CUTS:
        if cut in text:
            text = text[: text.index(cut)]
    # A short page that still says "Loading" was not rendered.
    if "Loading" in text and len(text) < 1500:
        return None
    return text.strip() or None


_SIGNALS = [
    "responsibilit", "requirement", "qualification", "experience", "skills", "about the role", "what you", "we are looking", "you will", "apply", "team",
    "工作內容", "條件", "職責", "資格", "經驗", "技能", "aufgaben", "profil", "erfahrung", "expérience", "compétences", "poste",
]
_CLOSED = ["職缺已關閉", "no longer available", "no longer accepting", "position has been filled", "job has expired", "posting has closed", "page not found"]


def looks_like_job(text: str, trusted: bool) -> bool:
    """A fetched page counts only if it reads like an open job posting. Board APIs are trusted with fewer signals."""
    lower = text.lower()
    if any(c.lower() in lower[:600] for c in _CLOSED):
        return False
    return sum(1 for s in _SIGNALS if s in lower) >= (2 if trusted else 4)


_BOARDS: list[tuple[str, Callable[[str], str | None]]] = [
    ("Greenhouse", _greenhouse),
    ("Ashby", _ashby),
    ("Workday", _workday),
    ("Lever", _lever),
    ("SmartRecruiters", _smartrecruiters),
]


def read_job_page(raw: str) -> dict | None:
    url = is_safe_url(raw)
    if not url:
        return None

    def good(text: str | None, trusted: bool = False) -> bool:
        return text is not None and len(text.strip()) >= MIN_CHARS and looks_like_job(text, trusted)

    for via, read in _BOARDS:
        text = read(url)
        if good(text, True):
            return {"text": text[:30000], "via": via}
    page = _direct(url)
    if good(page):
        return {"text": page[:30000], "via": "page"}
    rendered = _jina(url)
    if good(rendered):
        return {"text": rendered[:30000], "via": "Jina Reader"}
    return None
