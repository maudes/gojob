# GoJob architecture

Three diagrams: how the pieces fit, what happens when you paste a job description, and how one job moves between "apply", "tune" and "stop". The images are exported from the sources in [`diagrams/`](diagrams/) (the system diagram is drawn by hand as SVG).

## 1. System

![System architecture: Next.js screens, FastAPI backend, four AI roles, the audit gate, and local data files](img/architecture.svg)

- The screens never call Claude. They call `/api/*`, which Next.js forwards to the Python backend (`next.config.mjs`).
- The four AI roles are prompts and call patterns, not separate services. The prompts are plain files in `backend/gojob/skills/`, read on every call, so an edit applies without a restart. The writer, the review panel and the interview coach produce structured answers; the search agent also uses web search.
- Every AI answer goes through the audit gate in `backend/gojob/pipeline.py` before it is saved. Resume changes first pass a layout lock that drops any change on the name, section title, employer, job title, date, place or school lines. Search answers (job scan, company watch, people) are audited but not rewritten, because their facts come from the web, not from your resume.
- All state lives in `data/db.json`; resumes live in `data/files/`, whether uploaded or fetched from a Google Doc link as Word. Neither leaves your machine.

## 2. What happens when you paste a JD

![Sequence: user, backend, writer, review panel, auditors and db.json during a JD analysis](img/jd-analysis-sequence.svg)

- `par`: the writer's match analysis and the three reviewers' scores run at the same time.
- `opt`: the repair pass only happens if an auditor scores 95 or lower, a checklist box is unticked, or a quote is not found word for word in its source. It runs once.
- The gate at the end decides the apply tier: average 80 or more with no reviewer below 70.

Source: [`diagrams/jd-analysis-sequence.mmd`](diagrams/jd-analysis-sequence.mmd)

## 3. Apply, tune, or stop

![State diagram: a JD is assessed, then ready to apply, risky, or tuning; tuning loops back to assessed and ends at ceiling reached](img/fit-and-tuning-states.svg)

- Tuning may only reword what the resume already shows. It cannot add numbers, tools or titles; missing details become `[X%]` placeholders marked `needs_confirmation`.
- That is why tuning has a ceiling. It stops when the latest fine-tune has no change the resume supports, or when a resume change raised the average by less than 1 point (`CEILING_MIN_GAIN` in `pipeline.py`). The fine-tune button is then disabled and the backend refuses another one.
- A resume that really lacks the experience cannot be tuned into a pass. The way out is to add real experience and upload the revised resume, or to choose another job.

Source: [`diagrams/fit-and-tuning-states.mmd`](diagrams/fit-and-tuning-states.mmd)
