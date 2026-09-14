import json
import os

import pytest

from scripts import local_services as services


def test_pid_reuse_is_not_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "RUN", tmp_path)
    (tmp_path / "fastapi.pid").write_text("12345")
    (tmp_path / "fastapi.json").write_text(json.dumps({"identity": "old process"}))
    monkeypatch.setattr(services, "identity", lambda pid: "unrelated process")
    monkeypatch.setattr(os, "kill", lambda *a: pytest.fail("Unrelated PID must not be killed"))
    with pytest.raises(RuntimeError, match="ownership"):
        services.stop("fastapi")


def test_ownership_requires_project_and_exact_command():
    current = f"{os.getuid()} Mon Sep 14 10:00:00 2026 {services.PYTHON} " + " ".join(services.SERVICES["fastapi"][1])
    from unittest.mock import patch
    record = {"identity": current, "root": str(services.ROOT), "service": "fastapi"}
    with patch.object(services, "identity", return_value=current):
        assert services.owns("fastapi", 123, record)
        assert not services.owns("fastapi", 123, record | {"root": "/another/project"})


def test_missing_pid_does_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "RUN", tmp_path)
    monkeypatch.setattr(os, "kill", lambda *a: pytest.fail("No recorded PID"))
    services.stop("streamlit")
