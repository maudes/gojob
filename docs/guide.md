# GoJob guide

Day-to-day notes, the code map, testing and the release routine. For the product overview see the [README](../README.md); for diagrams see [architecture.md](architecture.md).

## Good to know

- Keep your resume in Google Docs and paste its link in the profile, shared as "Anyone with the link", then press **Fetch from link**. The app downloads it as Word, so the file keeps your layout; fetch again after you edit the doc. It can read your doc but never edit it (it does not sign in to Google): download the revised resume and paste the changes back. Or upload a `.docx` yourself (Google Docs: File → Download → Microsoft Word). Revised resumes then keep your exact fonts and layout: only the words inside existing text runs change, so fonts, colours, margins, tab stops, borders and bullets stay as they are.
- **The layout is locked.** A tracked change can only reword the headline, the summary, bullets and skills lines. It never lands on the name, the contact line, section titles, or the employer, job title, date, place and school lines, and the prompt tells the model not to add lines or make lines longer so the resume stays on its current number of pages. Changing the layout takes an explicit request from you.
- PDF download needs LibreOffice (`brew install --cask libreoffice`). Without it, download the `.docx` and export to PDF from Google Docs or Word.
- Your data is stored in the `data/` folder here and is never uploaded anywhere else. What is sent to the Claude API is the text the AI works from: your profile settings, resume, LinkedIn and website text, story bank, the notes and practice answers you type, and the JD. Email addresses and phone numbers are removed first. The job scan and company research also run web searches through Claude.
- The tracker copies a row in your sheet's column order and opens your Google Sheet in a new tab; you paste it. No Google login is stored.
- Models can be changed in `.env.local` with `MAIN_MODEL` and `REVIEWER_MODEL`.
- **Without an API key** you can assess a job description with Claude Code subagents: `npm run gojob -- analyze-jd --runner subagent --run NAME --jd-file JD.txt` (paths are relative to `backend/`; `--case ../evals/cases/X.json` uses a synthetic case). The command writes a request file for every model call it needs and stops; subagents write the answers; you run the same command again until it says `done`. The `run-gojob` skill in `.claude/skills/` does this loop for you. The code still decides whether the result passes. Requests and answers live in `data/manual/NAME/` (git-ignored); delete the folder when you are done, because it holds your resume and the JD.
- Find jobs (step 2): a headhunter scan searches the web, region by region, for openings and companies that fit the saved profile. The app opens every job link itself and drops items without a real link. Save openings to a wish list to decide later, and keep a target company table to re-check for new openings and track outreach. The scan runs when you press the button, not in the background.
- Interview coach: load a story bank (file, pasted text, or a Google Doc / Sheet / Drive link shared as "Anyone with the link"), tick the jobs to practise for, and answer one question at a time in a 30-second or 2-minute version. Dictation works in Chrome, Edge and Safari.
- Nothing is deleted automatically. Use "Manage saved data" at the bottom of the page to clear old jobs, tracker rows or practice history.
- Job links are read from the job board's own API when it is Greenhouse, Ashby, Lever, SmartRecruiters or Workday. Other pages are read directly, and if that fails the link (only the link) is sent to Jina Reader, a third-party service. Set `JD_READER_FALLBACK=off` in `.env.local` to turn that off.

## Code map

```
browser ── Next.js (port 3210, screens only) ── /api/* ──▶ Python backend (FastAPI, port 8000)
                                                            ├─ gojob/api.py              the routes (/api/*)
                                                            ├─ gojob/request_checks.py   what every request must look like
                                                            ├─ gojob/tasks.py            what each button does: builds the context, runs the audit loop
                                                            ├─ gojob/audit.py            write → 5 auditors → quote proof → repair once
                                                            ├─ gojob/scoring.py          apply rule, tuning ceiling, score rounding
                                                            ├─ gojob/skills/             every prompt, one plain-text file per skill
                                                            ├─ gojob/skill_loader.py     loads a skill or one part of it, pastes includes, fills variables
                                                            ├─ gojob/context_blocks.py   the data blocks around a prompt, and which skill to use
                                                            ├─ gojob/model_client.py     the only place that calls the model: the Claude API, or the subagent runner
                                                            ├─ gojob/subagent_runner.py  lets Claude Code subagents answer model calls through files (command line only)
                                                            ├─ gojob/cli.py              command line: assess one JD without the browser
                                                            ├─ gojob/schemas.py          what every model answer must look like
                                                            ├─ gojob/text_tools.py       contact redaction, word-for-word check, layout lock
                                                            ├─ gojob/sample_data.py      sample output when there is no API key
                                                            ├─ gojob/version_stamp.py    version / prompt / model stamp on every result
                                                            └─ gojob/store.py            data/db.json, with a data version and upgrades
```

The screens (`app/`, `components/`) never call Claude. They only call `/api/...`, which Next.js passes on to the backend (`next.config.mjs`).

## Testing

`npm test` runs the screen-helper tests (`lib/*.test.ts`, Node's built-in runner, needs Node 22.18 or newer) and the backend tests (`backend/tests`, pytest). They never call the Claude API. `npm run typecheck` checks the screens.

`npm run eval` measures how accurate the AI is, using synthetic cases built to provoke specific mistakes. `npm run eval:audit` tests the five auditors by planting mistakes on purpose. Both are separate from the tests and cost API money on a real run. See [evals/README.md](../evals/README.md).

## Security checks and maintenance

| Check | What it does | When | Where |
|---|---|---|---|
| `npm audit` | Looks up every package in `package-lock.json` in the npm advisory database; fails on any known advisory | every push and pull request, and Mondays 03:00 UTC | `.github/workflows/security.yml` |
| `pip-audit` | Exports the versions pinned in `backend/uv.lock` and checks them against PyPI advisories | same | same |

**When a check turns red**
1. Open the failed run on the Actions tab and read which package and which advisory.
2. Update that package and its lockfile: `npm update PACKAGE` (or `npm audit fix`) for the web side; `uv lock --upgrade-package PACKAGE` inside `backend/` for the Python side.
3. Run `npm test` and `npm run typecheck`, then push. If no fixed version exists yet, note the advisory in the changelog and decide whether the affected code path is used before ignoring it.

**Keeping it running**
- The weekly run exists because advisories appear for versions that were clean when you committed them. GitHub pauses scheduled workflows in a public repository after 60 days without activity; if the Actions tab says so, re-enable the workflow there or push a commit.
- About once a month: `npm outdated`, `uv lock --upgrade` in `backend/`, then `npm test`, and `npm run eval -- --yes --compare` if a model-facing package such as `anthropic` moved.
- Never commit `.env.local` or anything under `data/`. Both are git-ignored; check `git status` before a commit if you add new files.

**Not covered yet** (all optional, and free for a public repository)
- GitHub **secret scanning** and **push protection** (Settings, Code security): blocks a pushed API key. Currently off.
- **Dependabot** alerts and version updates, which open the update pull requests for you. Currently off.
- **Code scanning** (CodeQL) for the Python and TypeScript source.
- **Tests in CI**: `npm test` and `npm run typecheck` make no API calls, so they are safe to run on every push.
- **Branch protection** on `main`, so a red check blocks a merge, and a `SECURITY.md` saying where to report a vulnerability.

## Versions and releases

- The release version is `version` in `package.json`, following [semantic versioning](https://semver.org/): patch for fixes, minor for new features, major for changes that break saved data.
- Every change is described in [CHANGELOG.md](../CHANGELOG.md) under the version that ships it.
- Every AI result saved in `data/db.json` carries a `meta` stamp: the app version, a fingerprint of all prompts (`promptHash`, which changes by itself whenever a skill file is edited), one fingerprint per skill (`skills`), the models used, and who answered (`runner`: `api` or `subagent`). Results from before v1.0.0 have no stamp.
- `data/db.json` has a `schemaVersion`. When a release changes its shape, `backend/gojob/store.py` upgrades older files on first read and keeps a copy as `data/db.v<old>.bak.json`.
- To release: update `CHANGELOG.md`, run `npm test`, then `npm version minor` (or `patch` / `major`), which edits `package.json` and creates the git tag. Publish the tag as a GitHub Release and paste the changelog section as its notes.

