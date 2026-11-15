"""Check whether the LLM judge can be trusted, by comparing it with your own scores.

    npm run eval -- --yes --judge                          make a run that includes judge scores
    uv run python ../evals/calibrate.py --template RUN.json   add blank rows for that run to labels/human.json
    (open labels/human.json, read each output, fill in "score" 1-5)
    uv run python ../evals/calibrate.py                    compare your scores with the judge's

Run these from the backend/ folder. Score outputs with the same rubric the judge uses (rubrics/usefulness.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

LABELS = Path(__file__).with_name("labels") / "human.json"
RUNS = Path(__file__).with_name("runs")
MIN_LABELS = 20
MIN_WITHIN_ONE = 0.85


def load_labels() -> list[dict]:
    return json.loads(LABELS.read_text("utf8")) if LABELS.exists() else []


def template(run_name: str) -> None:
    run = json.loads((RUNS / run_name).read_text("utf8")) if (RUNS / run_name).exists() else json.loads(Path(run_name).read_text("utf8"))
    name = Path(run_name).name
    labels = load_labels()
    have = {(x["run"], x["case"], x["task"]) for x in labels}
    added = 0
    for cid, c in run["cases"].items():
        for task, r in c["results"].items():
            if "output" in r and (name, cid, task) not in have:
                labels.append({"run": name, "case": cid, "task": task, "score": None, "note": ""})
                added += 1
    LABELS.write_text(json.dumps(labels, indent=1, ensure_ascii=False) + "\n", "utf8")
    print(f"added {added} blank rows to {LABELS.relative_to(ROOT)}. Read each output in runs/{name}, then fill in score 1-5.")


def calibrate() -> int:
    labels = [x for x in load_labels() if isinstance(x.get("score"), int)]
    if not labels:
        print("No scored labels yet. See the instructions at the top of this file.")
        return 2
    pairs, missing = [], 0
    runs: dict[str, dict] = {}
    for x in labels:
        run = runs.setdefault(x["run"], json.loads((RUNS / x["run"]).read_text("utf8")))
        j = run["cases"].get(x["case"], {}).get("judge", {}).get(x["task"])
        if j is None:
            missing += 1
            continue
        pairs.append((x, j["score"]))
    if not pairs:
        print(f"{missing} labels have no judge score in their run. Re-run with --judge.")
        return 2
    n = len(pairs)
    diffs = [j - x["score"] for x, j in pairs]
    exact = sum(d == 0 for d in diffs) / n
    within1 = sum(abs(d) <= 1 for d in diffs) / n
    mae = sum(abs(d) for d in diffs) / n
    bias = sum(diffs) / n
    print(f"labels compared: {n}" + (f" ({missing} skipped, no judge score)" if missing else ""))
    print(f"exact agreement:   {exact:.0%}\nwithin 1 point:    {within1:.0%}\nmean abs error:    {mae:.2f}\njudge bias:        {bias:+.2f} (positive = judge is more generous than you)")
    big = [(x, j) for x, j in pairs if abs(j - x["score"]) >= 2]
    for x, j in big:
        print(f" - disagree by {abs(j - x['score'])}: {x['case']}/{x['task']} you {x['score']}, judge {j}")
    if n < MIN_LABELS:
        print(f"\nNOT ENOUGH LABELS: need at least {MIN_LABELS}, have {n}. Treat the judge as unverified.")
        return 1
    if within1 < MIN_WITHIN_ONE:
        print(f"\nDO NOT TRUST: the judge is within 1 point of you only {within1:.0%} of the time (need {MIN_WITHIN_ONE:.0%}). Improve rubrics/usefulness.md or change EVAL_JUDGE_MODEL.")
        return 1
    print("\nUSABLE as a trend indicator. Keep re-checking after rubric or model changes.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", metavar="RUN.json")
    a = ap.parse_args()
    if a.template:
        template(a.template)
        raise SystemExit(0)
    raise SystemExit(calibrate())
