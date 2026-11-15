# Changelog

All notable changes to Go Job are recorded here, newest first.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **`evals/`: an evaluation set for the AI.** Ten synthetic cases built as traps (missing metrics, keywords without evidence, participation inflated to leadership, work-authorisation wording, prompt injection in a job description, cover letter with no real motivation, messy PDF text, Chinese output), eleven code graders, an optional LLM judge for usefulness, a calibration tool that compares the judge with your own scores, and run-to-run comparison that flags regressions. `npm run eval -- --help`.
- Every run is saved with the app version, prompt fingerprint, models and git commit, so any two releases can be compared.
- 29 tests that check the graders themselves against hand-written good and bad answers.
- **Request checking.** Every JSON request is checked against a typed shape (`backend/gojob/requests.py`) before a route runs. A wrong type is answered with a 400 that names the field, and the shapes appear in the API docs at `/api/docs`. 16 tests.
- **Tests for the screen helpers.** `npm run test:web` runs 11 checks on tracked-change marks, JD tiers, the tracker row and applying accepted changes, using Node's built-in test runner (needs Node 22.18 or newer; running the app still works on Node 20). `npm test` now runs both the screen and backend tests.

### Known gaps
- Covers three tasks (JD analysis, resume tuning, cover letter). Not yet run against real model output.

## [1.0.0] - 2026-11-15

First tracked release. The backend moved from Node.js to Python; the screens and every feature are unchanged.

### Changed
- **Backend rewritten in Python (FastAPI).** All AI calls, the five-auditor review, quote checks, Word editing, job-page reading, the headhunter scan and the interview coach now live in `backend/`. The Next.js app only draws screens and forwards `/api/*` calls to it.
- The prompts were carried over word for word from the Node.js version, so the move itself does not change results. Two prompt changes made shortly before the move are part of this release: work-authorisation signals in the JD verdict, recruiter review and job scan, and the three-part cover letter (view and reason, ability, one sentence on work authorisation). They are now gathered in `backend/gojob/prompts.py` (the interview coach's prompts moved there from the coach module).
- Profile: "Countries where you can already work", so sponsorship is not treated as an issue for jobs there.
- Tracked changes are computed with the `diff` package instead of hand-written code. Marks are finer (a changed comma no longer marks the whole word), and a spacing-only edit no longer shows both spacings.
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
- Frontend-only helpers (`diffOps`, `tier`, `trackerTSV` in `lib/text.ts`) no longer have the start-up self-test. (Tests added after this release, see Unreleased.)
- There is no evaluation set yet for measuring answer quality; the runtime audit checks faithfulness to the sources only.

## [0.1.0] - 2026-11-14

Baseline: the Next.js-only version (profile health check, Find jobs, Target JD analysis, tracker, interview coach), recorded as the first commit. No changelog was kept for it.
