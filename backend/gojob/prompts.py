"""What the app puts around the prompts. The prompt text itself lives in skills/ (see skills.py).

This file only builds the data blocks (profile, JD, scan settings) and picks which skill file to use.
It is fingerprinted by meta.prompt_hash() together with every skill file.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from .skills import skill
from .text import redact

Lang = Literal["en", "zh"]

__all__ = ["Lang", "skill", "system", "profile_block", "target_jds_block", "jd_block"]


def system(role: str, lang: Lang) -> str:
    """The system prompt of a writer agent: shared ground rules, the language rule, then the task skill."""
    return f"{skill('shared-rules#ground-rules')}\n\n{skill('shared-rules#language-' + lang)}\n\n{role}"


# ---------- Context blocks ----------


def profile_block(p: dict, resume_text: str | None = None) -> str:
    resume = p["resumeText"] if resume_text is None else resume_text
    if not p["sponsorship"]:
        sponsorship = "No"
    elif p["workAuthorized"]:
        sponsorship = f"Yes, for every country except {', '.join(p['workAuthorized'])} (already authorised to work there)"
    else:
        sponsorship = "Yes"
    parts = [
        "<PROFILE>",
        f"Expected roles: {', '.join(p['roles']) or '(none)'}",
        f"Domains: {', '.join(p['domains']) or '(none)'}",
        f"Regions / countries (any of): {', '.join(p['regions']) or '(none)'}",
        f"Visa sponsorship required: {sponsorship}",
        f"Work type: {', '.join(p['workModes']) or '(none)'}",
        "Employment: full time only",
        "</PROFILE>",
        "<RESUME>",
        redact(resume),
        "</RESUME>",
        f"<LINKEDIN>\n{redact(p['linkedinText'])}\n</LINKEDIN>" if p["linkedinText"].strip() else "",
        f"<WEBSITE>\n{redact(p['websiteText'])[:8000]}\n</WEBSITE>" if p["websiteText"].strip() else "",
    ]
    return "\n".join(x for x in parts if x)


def target_jds_block(p: dict) -> str:
    return "\n".join(
        f'<TARGET_JD index="{i + 1}" title="{j["title"].replace(chr(34), chr(39))}">\n{j["text"]}\n</TARGET_JD>' for i, j in enumerate(p["targetJDs"])
    )


def jd_block(jd: str) -> str:
    return f"<JD>\n{jd}\n</JD>"

# ---------- Scoring reviewers and auditors ----------

# Reviewer id shown in the interface -> its file in skills/score-panel/.
PANEL_LENSES = {"ATS": "ats", "Recruiter": "recruiter", "Hiring manager": "hiring-manager"}
# The five fidelity auditors. The number is a product rule (all five must pass), so it is fixed here, not by counting files.
AUDIT_FOCUS = ("focus-1", "focus-2", "focus-3", "focus-4", "focus-5")


def panel_role(reviewer: str, target: Literal["profile", "jd"]) -> str:
    return skill("score-panel", lens=skill(f"score-panel#{PANEL_LENSES[reviewer]}"), what=skill(f"score-panel#what-{target}"))


def audit_role(focus: str) -> str:
    return skill("audit", focus=skill(f"audit#{focus}"))


# ---------- Job scout ----------


def scout_settings_block(s: dict, previous: str) -> str:
    parts = [
        "<SCAN_SETTINGS>",
        f"Regions to scan (one search round each): {'; '.join(s['regions']) or 'Global'}",
        f"Working languages accepted: {', '.join(s['languages']) or 'English'}",
        f"Notes from the candidate: {s['notes'].strip()}" if s["notes"].strip() else "",
        f"Today: {date.today().isoformat()}",
        "</SCAN_SETTINGS>",
        f"<PREVIOUS_SCANS>\n{previous}\n</PREVIOUS_SCANS>" if previous else "",
    ]
    return "\n".join(x for x in parts if x)



def scout_refresh_block(part: str, direction: list[dict], shown: list[str]) -> str:
    lines = [f"- {d['theme']}: {d['searchFor']}" for d in direction if d.get("theme")]
    return "\n".join(
        [
            "<REFRESH>",
            f"Part to refresh: {part}",
            "DIRECTION:",
            *(lines or ["- (derive it from the resume)"]),
            "ALREADY_SHOWN:",
            *([f"- {s}" for s in shown] or ["- (nothing)"]),
            "</REFRESH>",
        ]
    )

# ---------- Interview coach ----------


def coach_rules(lang: Lang) -> str:
    return f"{skill('interview-coach')}\n{skill('interview-coach#lang-' + lang)}"


def coach_feedback_task(lo: int, hi: int) -> str:
    return skill("coach-feedback", lo=lo, hi=hi)
