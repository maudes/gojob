"""The audit loop: write, five auditors check, quotes proven word for word, repair once.
Used by tasks.py, coach.py and scout.py."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from . import context_blocks as P
from . import model_client, sample_data
from .config import REVIEWER_MODEL
from .schemas import Audit
from .scoring import clamp_score
from .text_tools import is_verbatim

AUDITOR_COUNT = len(P.AUDIT_FOCUS)
#: Every auditor must score strictly above this.
AUDIT_PASS_ABOVE = 95

EMPTY_QUOTE_CHECK = {"total": 0, "verified": 0, "failed": []}


# ---------- Deterministic proof: every quote must exist in its source ----------


def check_quotes(output: Any, sources: dict[str, str]) -> dict:
    found: list[tuple[str, str]] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, list):
            for item in node:
                if isinstance(item, str) and key in ("orderedBullets", "drop"):
                    found.append(("resume", item))
                else:
                    walk(item, key)
            return
        if not isinstance(node, dict):
            return
        if isinstance(node.get("quote"), str) and node.get("source") in ("resume", "jd"):
            found.append((node["source"], node["quote"]))
        if isinstance(node.get("find"), str) and isinstance(node.get("replace"), str):
            found.append(("resume", node["find"]))
        for k, v in node.items():
            walk(v, k)

    walk(output)
    real = [(s, q) for s, q in found if q.strip()]
    failed = [{"source": s, "quote": q} for s, q in real if not is_verbatim(q, sources[s])]
    return {"total": len(real), "verified": len(real) - len(failed), "failed": failed}


# ---------- Five lightweight auditors ----------


def _dumps(obj: Any, **kw: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, **kw)


def run_audits(context: str, output: Any, lang: P.Lang, note: str = "") -> list[dict]:
    audit_note = f"<AUDIT_NOTE>\n{note}\n</AUDIT_NOTE>\n" if note else ""
    user = f"{context}\n{audit_note}<OUTPUT>\n{_dumps(output, indent=1)}\n</OUTPUT>"
    language = "Write issues in Taiwan Traditional Chinese." if lang == "zh" else "Write issues in English."

    def one(focus: str) -> dict:
        audit = model_client.run_json(
            schema=Audit, model=REVIEWER_MODEL, system=f"{P.audit_role(focus)}\n\n{language}", user=user, effort="low"
        )
        return {**audit.dump(), "score": clamp_score(audit.score)}

    with ThreadPoolExecutor(max_workers=AUDITOR_COUNT) as pool:
        return list(pool.map(one, P.AUDIT_FOCUS))


def is_approved(audits: list[dict], quote_check: dict) -> bool:
    """Approved only when all five auditors score above 95, tick every box, and every quote is verbatim."""
    return (
        len(audits) == AUDITOR_COUNT
        and all(a["score"] > AUDIT_PASS_ABOVE and all(a["checks"].values()) for a in audits)
        and not quote_check["failed"]
    )


def demo_audit() -> dict:
    return {"audits": sample_data.AUDITS, "quoteCheck": dict(EMPTY_QUOTE_CHECK), "approved": True, "demo": True}


def with_audit(
    *,
    produce: Callable[[str], Any],
    context: str,
    lang: P.Lang,
    check: Callable[[Any], dict] | None = None,
    note: str = "",
    repair: bool = True,
) -> dict:
    """Returns {output, audits, quoteCheck, approved, demo}."""
    check = check or (lambda _o: dict(EMPTY_QUOTE_CHECK))
    output = produce("")
    audits = run_audits(context, output, lang, note)
    quote_check = check(output)
    if repair and not is_approved(audits, quote_check):
        problems = [
            *[issue for a in audits for issue in a["issues"]],
            *[
                f'This text is attributed to the {f["source"]} but is not found there word for word: "{f["quote"]}"'
                for f in quote_check["failed"]
            ],
        ]
        if problems:
            unique = list(dict.fromkeys(problems))
            output = produce(
                f"\n<PREVIOUS_OUTPUT>\n{_dumps(output, separators=(',', ':'))}\n</PREVIOUS_OUTPUT>\n<REVIEW_ISSUES>\n"
                + "\n".join(f"- {p}" for p in unique)
                + "\n</REVIEW_ISSUES>\nProduce the output again. Keep everything the reviewers did not flag. Fix or remove each flagged item so that it is fully supported by the sources."
            )
            audits = run_audits(context, output, lang, note)
            quote_check = check(output)
    return {"output": output, "audits": audits, "quoteCheck": quote_check, "approved": is_approved(audits, quote_check), "demo": False}
