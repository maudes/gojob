# Evaluating Go Job's AI

The app already audits every answer while you use it (five auditors plus a word-for-word quote check). That protects one answer.
**This folder answers a different question: is the system accurate overall, and did a change make it better or worse?**

Run it before a release, and after any change to a prompt, a model or the pipeline.

## Three kinds of checking

| Layer | What it judges | Cost | Trust |
|---|---|---|---|
| **Code graders** (`graders.py`) | Faithfulness: invented numbers, fabricated quotes, stronger verbs than the resume supports, keywords added without evidence, obeying text hidden in a JD | free | exact and repeatable |
| **LLM judge** (`judge.py`) | Usefulness: would this actually help the candidate (`rubrics/usefulness.md`) | API money | an opinion; must be calibrated |
| **You** (`labels/human.json`) | The ground truth the other two are measured against | your time | the reference |

## Run it

All commands run from the project folder.

```bash
npm run eval -- --list
```

```bash
npm run eval -- --demo
```
`--demo` needs no API key. It only proves the wiring works (the app's sample answers are expected to fail the checks).

```bash
npm run eval -- --yes
```
A real run of every case. It prints an estimate and refuses to start without `--yes`. Results are saved to `runs/` with the version, prompt fingerprint, models and git commit in the file name.

```bash
npm run eval -- --yes --judge --cases keyword-trap,no-metrics
```
Only some cases, and also score usefulness.

```bash
npm run eval -- --compare evals/runs/OLD.json evals/runs/NEW.json
```
Shows each check side by side and marks a regression.

A run exits with 0 when every **critical** check passed, 1 when one failed, 2 when it did not run. A single critical failure means do not release.

## The cases (`cases/*.json`)

Synthetic resumes and job descriptions, no real person's data. Each is a trap built to provoke one specific failure:

| Case | Trap |
|---|---|
| `no-metrics` | resume has no numbers, JD asks for impact: must use `[X%]`, not invent |
| `keyword-trap` | JD needs Kubernetes, SQL, A/B testing; resume shows none: never add, must flag |
| `participation-not-ownership` | resume says "supported"; JD wants a leader: must not say "led" |
| `visa-negative` / `visa-already-authorised` | work authorisation read correctly in both directions |
| `prompt-injection` | the JD tells the AI what to write |
| `cover-letter-no-story` / `-with-story` | no invented motivation; letter stays inside the sources |
| `messy-resume` | PDF-style broken spacing: quotes must still match |
| `chinese-notes` | notes in Chinese, resume text stays English |

A case states what it expects (`expect`), not the exact text, because the AI's wording changes every run.
To add a case, copy one, change the resume/JD, and list the checks it needs. `backend/tests/test_evals.py` verifies that a new case is well formed and that its trap is real.

## Making the judge trustworthy

1. `npm run eval -- --yes --judge` to make a run with judge scores.
2. From `backend/`: `uv run python ../evals/calibrate.py --template RUN.json` adds blank rows to `labels/human.json`.
3. Read each output in the run file, fill in `score` (1 to 5, same rubric).
4. `uv run python ../evals/calibrate.py` compares you with the judge. With at least 20 labels and the judge within 1 point of you at least 85% of the time, use its scores as a **trend**. Otherwise do not trust them; fix the rubric or set `EVAL_JUDGE_MODEL` to a stronger model.

## What this does not cover (yet)

- Only `jdAnalysis`, `fineTune` and `coverLetter`. Interview prep, networking, the one-pager, the scan and the coach are not evaluated.
- Ten cases is a start. Add a case every time a real answer goes wrong; that is the best source of new ones.
- Token cost is not measured, only time.
- The graders were tested against hand-written good and bad outputs (`backend/tests/test_evals.py`). They have not yet been run against real model answers, so expect to adjust them after the first live run.
