"""Every test runs against a throw-away data folder and never reaches the Claude API."""
from __future__ import annotations

import pytest

from gojob import config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_FILE", tmp_path / "db.json")
    monkeypatch.setattr(config, "FILES_DIR", tmp_path / "files")
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


RESUME = (
    "Sample Candidate\n[email] · [phone] · Dublin\nProduct Manager | IoT\nSUMMARY\n"
    "Engineer turned product manager with experience in smart lighting and connected devices across Europe.\nEXPERIENCE\n"
    "Sample Lighting Co · Product Manager · 2021 - 2024\n"
    "Led Matter integration across three partner ecosystems for the smart lighting line\n"
    "Aligned firmware, cloud and app teams on a shared release calendar\n"
    "Owned the connectivity roadmap for the consumer product range\n"
    "Sample Devices Inc · Firmware Engineer · 2017 - 2021\nBuilt middleware for edge AI camera modules\n"
    "Shipped over-the-air update tooling used by the whole firmware organisation\n"
)


@pytest.fixture
def resume() -> str:
    return RESUME
