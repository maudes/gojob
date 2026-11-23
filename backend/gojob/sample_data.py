"""Invented sample output for when there is no API key, so the whole flow can be clicked through."""
from __future__ import annotations

from .text_tools import editable_lines

NONE = {"source": "none", "quote": ""}


def _jd(quote: str) -> dict:
    return {"source": "jd", "quote": quote}


def _all_checks(ok: bool = True) -> dict:
    return {"resumeQuotesVerbatim": ok, "jdQuotesVerbatim": True, "noInventedFacts": True, "labelsCorrect": True, "alignedWithProfile": True}


AUDITS = [{"score": s, "checks": _all_checks(), "issues": []} for s in (97, 96, 98, 96, 99)]


def panel(scores: list[float]) -> list[dict]:
    return [
        {"reviewer": r, "score": scores[i], "verdict": "Sample verdict. Add an API key to get a real one.", "strengths": [], "gaps": []}
        for i, r in enumerate(["ATS", "Recruiter", "Hiring manager"])
    ]


def _sample_changes(resume: str) -> list[dict]:
    """Two sample tracked changes on real sentence or bullet lines of the resume, never on the
    name, contact, section title, employer, job title, date or school lines."""
    lines = [ln for ln in editable_lines(resume) if len(ln.split()) >= 10 and len(ln) < 220 and "[" not in ln]
    out: list[dict] = []
    if len(lines) > 0:
        words = lines[0].split(" ")
        out.append(
            {
                "section": "Sample",
                "find": lines[0],
                "replace": f"{' '.join(words[:3])} (sample rewording) {' '.join(words[3:])}",
                "reason": "Sample change. A real run explains which JD requirement this serves.",
                "label": "inference",
            }
        )
    if len(lines) > 1:
        out.append(
            {
                "section": "Sample",
                "find": lines[1],
                "replace": f"{lines[1].rstrip('.;')}, resulting in [X%] improvement",
                "reason": "Sample change. Outcome missing; replace [X%] with your real number or reject.",
                "label": "needs_confirmation",
            }
        )
    return out


def health(resume: str) -> dict:
    return {
        "roleConflict": {"conflict": False, "reason": "Sample result. A real run checks whether your roles share a job family."},
        "positioning": {
            "statement": "Sample: the resume positions you by technology rather than by product outcome.",
            "closeToTruth": "Sample: close to the experience shown.",
            "closeToTarget": "Sample: target JDs ask for terms the resume does not yet use.",
        },
        "keywords": [
            {"keyword": "Roadmap", "jdCount": 3, "status": "covered", "proof": NONE},
            {"keyword": "Stakeholder management", "jdCount": 3, "status": "terminology_gap", "proof": NONE},
            {"keyword": "A/B testing", "jdCount": 2, "status": "needs_confirmation", "proof": NONE},
        ],
        "changes": _sample_changes(resume),
    }


JD_ANALYSIS = {
    "meta": {
        "company": "Sample Home Co",
        "title": "Senior Product Manager, Connected Devices",
        "location": "Dublin, Ireland (Hybrid)",
        "oneLine": "Own the roadmap for a smart home device line and its partner integrations.",
    },
    "companyContext": "Sample result. A real run summarises the company and product from the JD you supplied.",
    "strategy": {"verdict": "yellow", "instruction": "Sample: fine-tune the summary and two bullets, then re-assess."},
    "atsMatch": {"score": 68, "basis": "Sample basis."},
    "recruiterProbability": {"score": 62, "basis": "Sample basis. Rough diagnostic only."},
    "projectedAts": {"score": 81, "basis": "Sample basis."},
    "requirements": [
        {
            "requirement": _jd("(sample) 5+ years of product management experience with connected hardware"),
            "evidence": NONE,
            "label": "inference",
            "note": "Sample row. A real run quotes your resume here.",
        },
        {
            "requirement": _jd("(sample) Experience running experiments to inform prioritisation"),
            "evidence": NONE,
            "label": "needs_confirmation",
            "note": "Sample row.",
        },
    ],
    "missingKeywords": [
        {"keyword": "Go-to-market", "whereToAdd": "Summary", "reason": "Sample reason.", "label": "inference"},
        {"keyword": "Experimentation", "whereToAdd": "Do not add yet", "reason": "Sample: no resume evidence.", "label": "needs_confirmation"},
    ],
    "profileFit": [
        {"item": "region", "status": "ok", "note": "Sample."},
        {"item": "sponsorship", "status": "unknown", "note": "Sample: the JD does not mention sponsorship."},
        {"item": "work_mode", "status": "ok", "note": "Sample."},
        {"item": "full_time", "status": "ok", "note": "Sample."},
    ],
}


def fine_tune(resume: str) -> dict:
    return {
        "headlineTags": ["Connected Devices", "Partner Integrations", "Roadmap"],
        "changes": _sample_changes(resume),
        "bulletOrder": [],
        "additions": [
            {
                "type": "project",
                "suggestion": "Sample: have you run a pricing or packaging experiment you could describe?",
                "basis": "Sample basis.",
                "label": "needs_confirmation",
            }
        ],
    }


def cover_letter(story: str) -> dict:
    if len(story.strip()) < 40:
        return {
            "needsStory": True,
            "storyRequest": "Say in your own words why this company and why this role. The letter opens with it.",
            "coreProblem": {"text": "Sample core problem.", "label": "inference"},
            "letter": "",
            "factCheck": [],
        }
    return {
        "needsStory": False,
        "storyRequest": "",
        "coreProblem": {"text": "Sample core problem.", "label": "inference"},
        "letter": f"Dear Hiring Team,\n\n{story.strip()}\n\n(Sample letter. A real run writes 250 to 400 words from your story and resume, then lists every claim for you to check.)\n\nKind regards,",
        "factCheck": [{"claim": "Opening story", "label": "confirmed", "proof": {"source": "profile", "quote": "Provided by you"}}],
    }


_INTERVIEW_QUESTIONS = [
    ("Product lead", "Walk me through a product decision where a firmware constraint forced you to change the roadmap. What did you give up?"),
    ("Product lead", "How did factory realities such as yield, test time or lead times change a requirement you wrote?"),
    ("Product lead", "Look at our flow from unboxing to the first automation. What would you change first, and how would you prove it worked?"),
    ("Product lead", "From the outside, where does our product process most need adjusting?"),
    ("Product lead", "A partner changes its certification requirement three weeks before launch. Talk me through your first 48 hours."),
    ("Product lead", "How do you choose between a feature a partner demands and one our data says users need?"),
    ("Product lead", "Which part of our roadmap would you stop investing in, and why?"),
    ("Engineering lead", "How do you write requirements for firmware differently from cloud or app?"),
    ("Designer", "Tell me about a time feasibility and the ideal experience conflicted. Who decided?"),
    ("Peer PM", "Which metric would you add to the device team's dashboard, and which would you remove?"),
    ("QA", "A field issue shows on 2% of devices only. How do you handle it?"),
    ("Product lead", "Why this move now, and what would make you leave after a year?"),
]

INTERVIEW = {
    "riskMap": [
        {
            "requirement": _jd("(sample) Experience running experiments to inform prioritisation"),
            "evidence": NONE,
            "likelyQuestion": "Tell me about a decision you changed because of data.",
            "risk": "High, because it is a listed requirement and the resume shows no experiment.",
            "preparation": "Prepare one real decision with the data you used.",
        }
    ],
    "questions": [
        {
            "category": "hiring_manager",
            "interviewer": who,
            "question": q,
            "why": "Sample reason.",
            "mustProve": "Sample competency.",
            "keyElements": ["The constraint", "Options you weighed", "The call you made", "Result"],
            "evidence": NONE,
            "concern": "Sample concern.",
        }
        for who, q in _INTERVIEW_QUESTIONS
    ],
}

NETWORKING = {
    "targets": [
        {
            "type": "hiring_manager_or_hr",
            "name": "Sample Person",
            "title": "Head of Product, Connected Devices · Sample Home Co",
            "profileUrl": "https://www.linkedin.com/search/results/people/?keywords=Head%20of%20Product%20Connected%20Devices",
            "why": "Sample: one level above the role and likely the hiring manager.",
            "messages": [
                {
                    "angle": "Content follower",
                    "text": "Hi [Name], your post on [topic of their recent post] made me rethink how partner certification shapes a device roadmap. You have led connected devices through several ecosystem shifts. I would value your view on where device teams lose the most time today. Would you be open to a 20-minute call in the next two weeks?",
                },
                {
                    "angle": "Quick question",
                    "text": "Hi [Name], I am reaching out cold because your path from [previous role] to leading connected devices stood out. One question I think you can answer in a minute: which partner ecosystem shapes your roadmap the most right now?",
                },
            ],
        }
    ],
    "note": "Sample list. A real run searches the web for people at the company and returns their names, titles and LinkedIn links.",
}

ONE_PAGER_HTML = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:system-ui;margin:40px;color:#374151}h1{color:#DC2626}</style></head>'
    "<body><h1>Sample one-pager</h1><p>This is placeholder output. Add an API key to generate the researched company one-pager with cited sources.</p></body></html>"
)
