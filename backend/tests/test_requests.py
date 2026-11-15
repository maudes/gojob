"""Request bodies are checked before a route runs: a wrong type is a clear 400, never a crash."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gojob.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("method", "path", "body", "field"),
    [
        ("post", "/api/run", {"kind": "analyze", "jdText": 12345}, "jdText"),
        ("post", "/api/run", {"kind": "health", "lang": "fr"}, "lang"),
        ("post", "/api/jd-fetch", {"url": ["https://example.com"]}, "url"),
        ("post", "/api/resume-apply", {"scope": "everything"}, "scope"),
        ("post", "/api/resume-apply", {"scope": "profile", "accepted": [{"find": "a"}]}, "accepted.0.replace"),
        ("post", "/api/resume-apply", {"scope": "profile", "rejected": "all"}, "rejected"),
        ("post", "/api/tracker", {"company": {"name": "Acme"}}, "company"),
        ("patch", "/api/tracker", {"id": 7}, "id"),
        ("post", "/api/feedback", {"message": 5}, "message"),
        ("post", "/api/scout", {"kind": "run", "settings": {"regions": "Ireland"}}, "settings.regions"),
        ("patch", "/api/scout", {"list": "everything", "id": "x"}, "list"),
        ("post", "/api/coach", {"kind": "feedback", "mode": "5min"}, "mode"),
        ("post", "/api/coach", {"kind": "next", "jdIds": "abc"}, "jdIds"),
    ],
)
def test_wrong_types_are_refused_and_the_field_is_named(client, method, path, body, field):
    res = getattr(client, method)(path, json=body)
    assert res.status_code == 400
    assert field in res.json()["error"]


def test_a_body_that_is_not_an_object_is_refused(client):
    assert client.post("/api/run", json=["analyze"]).status_code == 400
    assert client.post("/api/tracker", content=b"not json", headers={"content-type": "application/json"}).status_code == 400


def test_unknown_fields_and_nulls_are_tolerated(client):
    row = client.post("/api/tracker", json={"company": "Acme", "notes": None, "somethingNew": 1}).json()["row"]
    assert row["company"] == "Acme" and row["notes"] == "" and "somethingNew" not in row


def test_nothing_is_written_when_a_request_is_refused(client):
    client.post("/api/tracker", json={"company": 1})
    assert client.get("/api/state").json()["tracker"] == []
