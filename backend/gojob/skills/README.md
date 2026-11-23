# Skills

Every prompt GoJob sends to a model is a plain text file here, one file per skill. Edit a file, save, and the next request uses it. No restart and no code change.

```
skills/<name>.md      one skill: a small header (name, description, variables), then the prompt
## part: <part>       inside the file, starts a named piece the code picks at run time
```

The text before the first `## part:` line is the skill's main prompt. Parts are for things the code chooses between (the English or 繁中 language rule, one of the five auditors' starting points, one question category). Refer to them as `name` or `name#part`.

Two markers work inside the text:

- `{{include:shared-rules#visa-signals}}` pastes another skill or part at that spot. Rules used by several prompts live in one place.
- `{{variable}}` is filled in by the code. The header's `variables:` line lists them; a missing one is an error, never a silent blank.

The header (`name`, `description`) follows the layout Claude Code uses for skills, so the files read and diff like any document.

## The skills

| File | What it makes the model do | Parts | Used in |
|---|---|---|---|
| `shared-rules` | Rules several skills share | `ground-rules`, `change-rules`, `visa-signals`, `search-honesty`, `language-en`, `language-zh` | every writer agent; included by others |
| `health-check` | Role conflict, positioning, keywords, resume changes | | step 1 |
| `panel-scorer` | One scoring reviewer | `ats`, `recruiter`, `hiring-manager`, `what-profile`, `what-jd` | steps 1 and 3 |
| `jd-match` | Matching assessment of one JD | | step 3 |
| `fine-tune` | Tailor the resume to one JD as tracked changes | | step 3 |
| `cover-letter` | Cover letter with a work authorisation sentence | | step 3 |
| `interview-prep` | Risk map and 12 to 14 deep interview questions | | step 3, feeds step 5 |
| `networking` | Real people at a company plus two LinkedIn messages each | | step 3, step 2 |
| `one-pager` | System rule for the company one-pager | `english`, `template` (the report prompt) | step 3 |
| `auditor` | One fidelity auditor | `focus-1` to `focus-5`: each auditor's starting point | every AI output |
| `scout` | Headhunter scan: search direction, regions, filters, refresh | | step 2 |
| `company-watch` | Check one target company for openings | | step 2 |
| `interview-coach` | Base rules shared by the three coach tasks | `lang-en`, `lang-zh`, `audit-note` | step 5 |
| `coach-question` | One practice question | six `category-*` briefs, `audit-note` | step 5 |
| `coach-feedback` | Feedback on one answer (takes the word target `lo`, `hi`) | | step 5 |
| `coach-report` | Weekly practice review | `audit-note` | step 5 |

## Editing safely

- **Answer shapes are not prompts.** The JSON a skill asks for (`scout`, `networking`, `company-watch`) and the fields the model fills elsewhere are defined in `backend/gojob/schemas.py`. If you rename a field in a skill, rename it there too; the code rejects an answer it cannot read.
- **The five auditors are a product rule** (all five must score above 95). Reword a `focus-N` part freely, but adding or removing one means changing `AUDIT_FOCUS` in `backend/gojob/context_blocks.py`.
- **Keep the check names** in `auditor.md` (`resumeQuotesVerbatim`, `jdQuotesVerbatim`, `noInventedFacts`, `labelsCorrect`, `alignedWithProfile`); the answer schema uses them.
- **Do not start a normal heading with `part:`.** Only `## part: name` starts a part, so ordinary `##` headings inside a prompt (the one-pager template has many) are safe.
- **What stays in code**: the data blocks that wrap a prompt (`<PROFILE>`, `<RESUME>`, `<JD>`, the scan settings), because they are built from your saved data.

After an edit: `npm test` (checks that every skill loads and every reference resolves), then `npm run eval -- --yes` and compare with the last run; after changing `auditor.md` also run `npm run eval:audit -- --yes`. Every saved result carries a fingerprint of all skill files (`promptHash`) and one per skill (`skills`, which includes the shared rules it pastes in), so you can tell which wording produced it and `--compare` can name the skill that changed.
