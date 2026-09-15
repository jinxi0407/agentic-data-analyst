"""Ordinary pytest must never reach a paid model or an actual database."""

import pytest
import requests

from app.tools import database, qwen
from app.agent import diagnostics


@pytest.fixture(autouse=True)
def block_unmocked_external_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path / "diagnostics")
    def blocked(*args, **kwargs):
        pytest.fail("Unmocked external call: use a test double; run live checks separately")
    monkeypatch.setattr(qwen, "_require_dashscope", blocked)
    monkeypatch.setattr(database, "_connect", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
