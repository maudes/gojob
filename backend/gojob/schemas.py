"""Shapes of everything a model must return, plus the profile.

Python names are snake_case; on the wire (the browser, data/db.json and the model's JSON)
they are camelCase, exactly as the first version of the app used them. Stored records are
plain dicts in that camelCase form, so existing data keeps loading.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def dump(self) -> dict:
        return self.model_dump(by_alias=True, mode="json")


Label = Literal["confirmed", "inference", "needs_confirmation"]


class Evidence(Model):
    """A verbatim quote plus where it came from. Empty quote = no evidence exists."""

    source: Literal["resume", "jd", "profile", "none"]
    quote: str


class ResumeChange(Model):
    """One tracked change. `find` is copied word for word from one resume line; `replace` is the new text."""

    section: str
    find: str
    replace: str
    reason: str
    label: Label


# ---------- Profile (user input, never model output) ----------


class TargetJD(Model):
    id: str
    title: str
    text: str


class Profile(Model):
    resume_text: str = ""
    resume_file_name: str = ""
    resume_link: str = ""
    resume_format: Literal["docx", "other", ""] = ""
    linkedin_url: str = ""
    website_url: str = ""
    linkedin_text: str = ""
    website_text: str = ""
    roles: list[str] = Field(default_factory=list, max_length=2)
    domains: list[str] = Field(default_factory=list, max_length=3)
    # to_camel would give "targetJds"; the browser and data/db.json have always used "targetJDs".
    target_jds: list[TargetJD] = Field(default_factory=list, max_length=10, alias="targetJDs")
    regions: list[str] = Field(default_factory=list)
    sponsorship: bool = False
    #: Countries where the candidate can already work, so sponsorship is not needed there.
    work_authorized: list[str] = Field(default_factory=list, max_length=10)
    work_modes: list[Literal["remote", "onsite", "hybrid"]] = Field(default_factory=list)
    full_time_only: Literal[True] = True
    sheet_url: str = ""
    #: When the resume content last changed. Drives the six-month reminder.
    resume_updated_at: str | None = None
    saved_at: str | None = None


# ---------- Review layers ----------


class PanelPoint(Model):
    point: str
    proof: Evidence


class PanelScore(Model):
    """One of the three scoring reviewers (ATS, recruiter, hiring manager)."""

    score: float
    verdict: str
    strengths: list[PanelPoint]
    gaps: list[PanelPoint]


class AuditChecks(Model):
    resume_quotes_verbatim: bool
    jd_quotes_verbatim: bool
    no_invented_facts: bool
    labels_correct: bool
    aligned_with_profile: bool


class Audit(Model):
    """One of the five lightweight fidelity auditors."""

    score: float
    checks: AuditChecks
    issues: list[str]


# ---------- Profile health check ----------


class RoleConflict(Model):
    conflict: bool
    reason: str


class Positioning(Model):
    statement: str
    close_to_truth: str
    close_to_target: str


class KeywordRow(Model):
    keyword: str
    jd_count: float
    status: Literal["covered", "terminology_gap", "needs_confirmation"]
    proof: Evidence


class HealthCheck(Model):
    role_conflict: RoleConflict
    positioning: Positioning
    keywords: list[KeywordRow]
    changes: list[ResumeChange]


# ---------- Target JD analysis ----------

Verdict = Literal["green", "mint", "yellow", "orange", "red"]


class JDMeta(Model):
    company: str
    title: str
    location: str
    one_line: str


class Strategy(Model):
    verdict: Verdict
    instruction: str


class ScoreBasis(Model):
    score: float
    basis: str


class Requirement(Model):
    requirement: Evidence
    evidence: Evidence
    label: Label
    note: str


class MissingKeyword(Model):
    keyword: str
    where_to_add: str
    reason: str
    label: Label


class ProfileFitRow(Model):
    item: Literal["region", "sponsorship", "work_mode", "full_time", "role", "domain"]
    status: Literal["ok", "risk", "unknown"]
    note: str


class JDAnalysis(Model):
    meta: JDMeta
    company_context: str
    strategy: Strategy
    ats_match: ScoreBasis
    recruiter_probability: ScoreBasis
    projected_ats: ScoreBasis
    requirements: list[Requirement]
    missing_keywords: list[MissingKeyword]
    profile_fit: list[ProfileFitRow]


# ---------- Follow-up actions ----------


class BulletOrder(Model):
    section: str
    ordered_bullets: list[str]
    drop: list[str]
    reason: str


class Addition(Model):
    type: Literal["project", "skill"]
    suggestion: str
    basis: str
    label: Label


class FineTune(Model):
    headline_tags: list[str]
    changes: list[ResumeChange]
    bullet_order: list[BulletOrder]
    additions: list[Addition]


class CoreProblem(Model):
    text: str
    label: Label


class FactCheckRow(Model):
    claim: str
    label: Label
    proof: Evidence


class CoverLetter(Model):
    needs_story: bool
    story_request: str
    core_problem: CoreProblem
    letter: str
    fact_check: list[FactCheckRow]


class RiskRow(Model):
    requirement: Evidence
    evidence: Evidence
    likely_question: str
    risk: str
    preparation: str


class InterviewQuestion(Model):
    category: Literal["recruiter_screen", "hiring_manager", "technical_functional", "behavioral", "motivation", "domain"]
    interviewer: str
    question: str
    why: str
    must_prove: str
    key_elements: list[str]
    evidence: Evidence
    concern: str


class Interview(Model):
    risk_map: list[RiskRow]
    questions: list[InterviewQuestion]


class OutreachMessage(Model):
    angle: str
    text: str


class NetworkTarget(Model):
    type: Literal["hiring_manager_or_hr", "employee", "similar_background"]
    name: str
    title: str
    profile_url: str
    why: str
    messages: list[OutreachMessage]


class Networking(Model):
    targets: list[NetworkTarget]
    note: str


# ---------- Interview coach ----------

CoachCategory = Literal["self_intro", "behavioral", "general", "story", "jd", "product"]
CoachMode = Literal["30s", "2min"]
Weakness = Literal[
    "too_long", "too_short", "unclear_situation", "no_challenge", "no_decision", "no_impact", "weak_relevance", "grammar", "vague_wording"
]


class CoachQuestion(Model):
    question: str
    story_hint: str
    why: str


class ContentRow(Model):
    element: Literal["situation", "challenge", "decision", "impact", "relevance"]
    present: bool
    note: str


class EnglishFix(Model):
    original: str
    better: str
    why: str


class CoachFeedback(Model):
    score: float
    headline: str
    content: list[ContentRow]
    english: list[EnglishFix]
    delivery: str
    tighter: str
    weaknesses: list[Weakness]
    confirm: list[str]


class CoachReport(Model):
    strengths: list[str]
    weak_areas: list[str]
    prepare: list[str]
    delivery30: str
    delivery2min: str = Field(alias="delivery2min")


# ---------- Job scout ----------
# Web-search output is messier than structured output, so these fall back to safe defaults.


def _text(v):
    return v if isinstance(v, str) else ""


Text = Annotated[str, BeforeValidator(_text)]


def _proof(v):
    try:
        return Evidence.model_validate(v)
    except Exception:
        return Evidence(source="none", quote="")


Proof = Annotated[Evidence, BeforeValidator(_proof)]


def _label(v):
    return v if v in ("confirmed", "inference", "needs_confirmation") else "needs_confirmation"


LooseLabel = Annotated[Label, BeforeValidator(_label)]


def _one_of(allowed: tuple[str, ...], default: str):
    return BeforeValidator(lambda v: v if v in allowed else default)


def _list(v):
    return v if isinstance(v, list) else []


LooseList = BeforeValidator(_list)


def _no_proof() -> Evidence:
    return Evidence(source="none", quote="")


class ScoutJob(Model):
    tier: Annotated[Literal["A", "B", "C"], _one_of(("A", "B", "C"), "C")] = "C"
    company: str
    title: str
    location: Text = ""
    visa: Annotated[
        Literal["offered", "not_mentioned", "needs_confirmation"], _one_of(("offered", "not_mentioned", "needs_confirmation"), "needs_confirmation")
    ] = "needs_confirmation"
    visa_note: Text = ""
    posted: Text = ""
    url: str
    fit: Text = ""
    proof: Proof = Field(default_factory=_no_proof)
    label: LooseLabel = "needs_confirmation"


class ScoutCompany(Model):
    company: str
    url: Text = ""
    signal: Text = ""
    signal_url: Text = ""
    why: Text = ""
    role_type: Text = ""
    approach: Text = ""
    proof: Proof = Field(default_factory=_no_proof)
    label: LooseLabel = "needs_confirmation"


class ScoutRegion(Model):
    region: str
    heat: Annotated[Literal["warming", "steady", "cooling", "unknown"], _one_of(("warming", "steady", "cooling", "unknown"), "unknown")] = "unknown"
    summary: Text = ""
    label: LooseLabel = "needs_confirmation"
    source_url: Text = ""


class ScoutDirection(Model):
    theme: Text = ""
    search_for: Text = ""
    proof: Proof = Field(default_factory=_no_proof)


class ScoutReport(Model):
    headline: Text = ""
    direction: Annotated[list[ScoutDirection], LooseList] = Field(default_factory=list)
    regions: Annotated[list[ScoutRegion], LooseList] = Field(default_factory=list)
    jobs: Annotated[list[ScoutJob], LooseList] = Field(default_factory=list)
    companies: Annotated[list[ScoutCompany], LooseList] = Field(default_factory=list)
    weekly: Text = ""
    priorities: Annotated[list[str], LooseList] = Field(default_factory=list)
    unreachable: Annotated[list[str], LooseList] = Field(default_factory=list)


class Opening(Model):
    title: str
    location: Text = ""
    url: str
    fit: Text = ""
    proof: Proof = Field(default_factory=_no_proof)
    label: LooseLabel = "needs_confirmation"


class CompanyOpenings(Model):
    openings: Annotated[list[Opening], LooseList] = Field(default_factory=list)
    note: Text = ""


# ---------- Plain constants ----------

TRACKER_STATUSES = ("Apply", "HR", "Interview", "Reject")
WISH_DECISIONS = ("Deciding", "Will apply", "Applied", "Pass")
COMPANY_STATUSES = ("Watching", "Reached out", "In conversation", "Paused")
ACTION_KINDS = ("fineTune", "coverLetter", "interview", "networking", "onePager")
