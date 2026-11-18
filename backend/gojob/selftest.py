"""Free, deterministic checks run on every start. No model calls.

The footer of the app shows how many pass. The fuller pytest suite in backend/tests runs the same
checks and more; `uv run pytest` is the one to use while developing.
"""
from __future__ import annotations

from functools import lru_cache

from .docx_io import apply_changes_to_docx, docx_to_text, text_to_docx
from .meta import stamp
from .pipeline import check_quotes, gate, is_approved
from .scout import keep_linked
from .store import migrate
from .text import apply_to_text, is_verbatim, keep_editable, redact


def _audit(score: float, ok: bool = True) -> dict:
    return {
        "score": score,
        "checks": {"resumeQuotesVerbatim": ok, "jdQuotesVerbatim": True, "noInventedFacts": True, "labelsCorrect": True, "alignedWithProfile": True},
        "issues": [],
    }


_CLEAN = {"total": 1, "verified": 1, "failed": []}


def _run() -> list[dict]:
    out: list[dict] = []

    def t(name: str, passed: bool) -> None:
        out.append({"name": name, "pass": bool(passed)})

    red = redact("Jane Doe · jane.doe@mail.com · +353 87 123 4567 · 2019 - 2023")
    t("Contact details are removed", "@" not in red and "123 4567" not in red and "2019 - 2023" in red)
    t("Quote check accepts word-for-word text", is_verbatim("•  Led   Matter integration", "- Led Matter integration across teams"))
    t("Quote check rejects altered text", not is_verbatim("Led Matter integrations", "Led Matter integration across teams"))
    qc = check_quotes({"a": {"source": "resume", "quote": "not there"}, "c": [{"find": "Owned roadmap", "replace": "x"}]}, {"resume": "Owned roadmap", "jd": ""})
    t("Unverified quotes are counted", qc["total"] == 2 and len(qc["failed"]) == 1)
    t("Health gate: average 80, minimum 70", gate([80, 80, 80], 80, 70)["green"] and not gate([95, 95, 69], 80, 70)["green"] and not gate([79, 80, 80], 80, 70)["green"])
    five = lambda scores, ok_index=None: [_audit(s, i != ok_index) for i, s in enumerate(scores)]  # noqa: E731
    t(
        "Approval needs five auditors above 95",
        is_approved(five([96] * 5), _CLEAN) and not is_approved(five([96, 96, 96, 96, 95]), _CLEAN) and not is_approved(five([99] * 4), _CLEAN),
    )
    t(
        "Approval needs every box and every quote",
        not is_approved(five([99] * 5, ok_index=2), _CLEAN)
        and not is_approved(five([99] * 5), {"total": 1, "verified": 0, "failed": [{"source": "resume", "quote": "x"}]}),
    )
    text, _ = apply_to_text("A\nOwned roadmap\nB", [{"find": "Owned roadmap", "replace": "Owned the roadmap"}])
    t("Accepted changes apply to text", text == "A\nOwned the roadmap\nB")
    try:
        docx = text_to_docx("Jane Doe\nEXPERIENCE\n- Owned the connectivity roadmap\n- Built middleware")
        edited, missed = apply_changes_to_docx(docx, [{"find": "Owned the connectivity roadmap", "replace": "Owned the connectivity roadmap for [X] products"}])
        back = docx_to_text(edited)
        t("Word file is edited in place", not missed and "for [X] products" in back and "Built middleware" in back)
    except Exception:  # noqa: BLE001
        t("Word file is edited in place", False)
    kept, dropped = keep_linked([{"url": "https://jobs.example.com/1"}, {"url": ""}, {"url": "see careers page"}, {"url": "http://localhost/x"}])
    t("Scan drops jobs without a real link", len(kept) == 1 and dropped == 3)
    layout = "Jane Doe\nSUMMARY\nAcme Corp Berlin, Germany\nProduct Manager Jan 2021 – Present\nOwned the connectivity roadmap across three hardware product lines for EU launches."
    kept, dropped = keep_editable([{"find": "Acme Corp Berlin, Germany", "replace": "x"}, {"find": "Product Manager Jan 2021", "replace": "x"}, {"find": "Owned the connectivity roadmap", "replace": "y"}], layout)
    t("Changes never touch name, section, employer, title or date lines", dropped == 2 and [c["replace"] for c in kept] == ["y"])
    s = stamp()
    t("Results are stamped with version, prompts and models", bool(s["appVersion"]) and len(s["promptHash"]) == 10 and s["models"]["main"] and s["models"]["reviewer"])
    migrated = migrate({"profile": {}})
    t("Older data files are upgraded to the current data version", isinstance(migrated.get("schemaVersion"), int) and migrated["schemaVersion"] >= 1)
    return out


@lru_cache(maxsize=1)
def self_test() -> list[dict]:
    return _run()
