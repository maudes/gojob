# Changelog

All notable changes to Go Job are recorded here, newest first.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-15

First tracked release. The backend moved from Node.js to Python; the screens and every feature are unchanged.

### Changed
- **Backend rewritten in Python (FastAPI).** All AI calls, the five-auditor review, quote checks, Word editing, job-page reading, the headhunter scan and the interview coach now live in `backend/`. The Next.js app only draws screens and forwards `/api/*` calls to it.
- All prompts are byte-for-byte the same as in v0.1.0, so results should behave the same. They are now gathered in `backend/gojob/prompts.py` (the interview coach's prompts moved there from the coach module).
- `npm run dev` now starts both the web interface and the backend. Needs [uv](https://docs.astral.sh/uv/) installed.
- Screen code no longer depends on `docx`, `jszip`, `mammoth`, `unpdf` or the Anthropic SDK; those moved to Python equivalents (`python-docx`, `mammoth`, `pypdf`, `anthropic`).

### Added
- **Traceable results.** Every AI result is stamped with `meta`: app version, a `promptHash` fingerprint of all prompts, and the writer and auditor models. The footer shows the running version.
- **Data versioning.** `data/db.json` carries a `schemaVersion`. Older files are upgraded on first read and a copy is kept as `data/db.v0.bak.json`. A file written by a newer app is refused instead of being damaged, and a corrupt file is set aside instead of overwritten.
- **Test suite.** `npm test` runs 67 pytest checks covering the audit and repair loop, quote proof, approval gates, Word editing, link safety, data upgrades and every API route in sample mode. No test calls the Claude API.
- `CHANGELOG.md`, a git history and release tags.

### Fixed
- `.gitignore` now also excludes `data/files/`, which holds the uploaded resumes.
- A saved file whose JSON is damaged no longer gets silently replaced by an empty one on the next save.

### Known gaps
- Results created before v1.0.0 have no `meta` stamp.
- Frontend-only helpers (`diffOps`, `tier`, `trackerTSV` in `lib/text.ts`) no longer have the start-up self-test, and have no automated test yet.
- There is no evaluation set yet for measuring answer quality; the runtime audit checks faithfulness to the sources only.

## [0.1.0] - 2026-11-14

Baseline: the Next.js-only version (profile health check, Find jobs, Target JD analysis, tracker, interview coach), recorded as the first commit. No changelog was kept for it.
