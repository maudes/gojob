"""The shape of every JSON request body. FastAPI checks a request against these before a route runs,
so a wrong type is answered with a clear 400 instead of failing somewhere inside the route.

Rules that keep the browser code working unchanged:
- Unknown fields are ignored.
- Every field is optional and may be null; a route decides what it needs for the `kind` it was sent.
- Values a route already cleans up itself (a tracker status outside the list, an over-long note)
  stay plain strings here, so they are ignored or trimmed there rather than rejected.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from .schemas import Model

Lang = Literal["en", "zh"]


class Req(Model):
    """Base for request bodies. `body()` gives the route a plain dict of the fields that were sent."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore", strict=True)

    def body(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class RunBody(Req):
    kind: str | None = None
    lang: Lang | None = None
    id: str | None = None
    jd_url: str | None = None
    jd_text: str | None = None
    action: str | None = None
    input: str | None = None
    target: str | None = None


class ResumeLinkBody(Req):
    link: str | None = None


class JDFetchBody(Req):
    url: str | None = None


class Change(Req):
    find: str
    replace: str


class ResumeApplyBody(Req):
    scope: Literal["profile", "jd"]
    id: str | None = None
    accepted: list[Change] | None = None
    rejected: list[str] | None = None


class TrackerBody(Req):
    id: str | None = None
    company: str | None = None
    position: str | None = None
    location: str | None = None
    job_link: str | None = None
    one_line: str | None = None
    matching_score: str | None = None
    apply_date: str | None = None
    network_target: str | None = None
    status: str | None = None
    notes: str | None = None


class FeedbackBody(Req):
    feature: str | None = None
    message: str | None = None


class ScoutSettingsBody(Req):
    regions: list[str] | None = None
    languages: list[str] | None = None
    notes: str | None = None


class ScoutJobBody(Req):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    url: str | None = None
    tier: str | None = None
    visa: str | None = None
    posted: str | None = None
    fit: str | None = None
    notes: str | None = None


class ScoutCompanyBody(Req):
    company: str | None = None
    careers_url: str | None = None
    why: str | None = None
    role_type: str | None = None
    contact: str | None = None
    notes: str | None = None


class ScoutBody(Req):
    kind: str | None = None
    lang: Lang | None = None
    id: str | None = None
    part: Literal["jobs", "companies"] | None = None
    settings: ScoutSettingsBody | None = None
    job: ScoutJobBody | None = None
    company: ScoutCompanyBody | None = None


class ScoutEditBody(ScoutJobBody, ScoutCompanyBody):
    """Inline edit of a wish list job or a target company: `list` says which, the rest are the changed fields."""

    list: Literal["jobs", "companies"] | None = None
    id: str | None = None
    decision: str | None = None
    status: str | None = None


class CoachBody(Req):
    kind: str | None = None
    lang: Lang | None = None
    category: str | None = None
    jd_ids: list[str] | None = None
    prompt: dict[str, Any] | None = None
    mode: Literal["30s", "2min"] | None = None
    answer: str | None = None
    seconds: float | None = None
