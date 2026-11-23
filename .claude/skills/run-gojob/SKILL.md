---
name: run-gojob
description: Assess one job description with Claude Code subagents instead of the Claude API (no API key). Use when asked to run GoJob "by subagent" or "without the API".
---

You are the orchestrator. The code (`backend/gojob/`) decides what to ask and whether the result passes; you only dispatch.

1. Run, from the repo root (keep the arguments identical every round):
   `cd backend && uv run python -m gojob.cli analyze-jd --runner subagent --run NAME <--case ../evals/cases/X.json | --jd-file FILE> [--save]` (paths are relative to `backend/`, which is why the case path starts with `../`)
2. Read the JSON it prints.
   - `"status": "pending"`: for every item in `requests`, start one subagent, **all in the same message** so they run in parallel. `model` = the item's `agentModel`. Prompt, nothing else: `Read <promptFile> and follow it. Write your answer to <answerFile>.`
   - Wait for all of them, then go back to step 1.
   - `"status": "done"`: report `approved`, `gate`, `auditScores`, `panelAuditScores`, `quoteCheck`, and `resultFile`. Stop.
   - `"status": "error"`: report the error. Stop.
3. Rules
   - Never write or edit an answer file yourself, and never give a subagent more than the line above: each step must be judged on its own.
   - Never decide whether the result passes. `approved` comes from the code (five auditors above 95, every quote word for word).
   - A request that comes back with `error` is asked again by the code, at most 3 times. Do not fix it by hand.
   - Results made this way carry `meta.runner: "subagent"`. They are not API results; do not mix them into an API eval run.
4. Private data: `--case` uses a synthetic eval case. Without it the saved profile is used, and its resume and JD are written under `data/manual/NAME/` (git-ignored). Delete that folder when you are done.
