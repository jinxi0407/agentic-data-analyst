"""Import isolation checks: no model, database, or Docker calls."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("root_already_present", [False, True])
def test_fresh_streamlit_process_imports_project_package(root_already_present):
    code = r'''
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import requests
from streamlit.testing.v1 import AppTest

root = Path(sys.argv[1])
sys.path[:] = [p for p in sys.path if p and Path(p).resolve() != root]
sys.path.insert(0, str(root / "ui"))
if sys.argv[2] == "True":
    sys.path.append(str(root))
assert "app" not in sys.modules
with patch.object(requests.sessions.Session, "request", side_effect=AssertionError("Unexpected network")), \
     patch.object(requests, "get", return_value=SimpleNamespace(ok=True)):
    view = AppTest.from_file(str(root / "ui/app.py")).run(timeout=30)
assert not view.exception, str(view.exception)
from app.agent import diagnostics
import app
from app.main import app as api
assert Path(app.__file__).resolve() == root / "app/__init__.py"
assert Path(diagnostics.__file__).resolve() == root / "app/agent/diagnostics.py"
assert api is not None
print("UI and API imports passed")
'''
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", code, str(ROOT), str(root_already_present)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UI and API imports passed" in result.stdout


@pytest.mark.parametrize("existing_path", ["", "/existing/import/path"])
def test_start_script_derives_root_and_exports_pythonpath(tmp_path, existing_path):
    project = tmp_path / "project with spaces"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "start_local.sh").write_bytes((ROOT / "scripts/start_local.sh").read_bytes())
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$PYTHONPATH" "$@"\n')
    python.chmod(0o755)
    (project / ".env").touch()
    env = os.environ.copy()
    env["PYTHONPATH"] = existing_path
    result = subprocess.run(["bash", str(scripts / "start_local.sh")], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=10, check=True)
    assert result.stdout.splitlines() == [str(project), f"{project}:{existing_path}",
                                          "scripts/local_services.py", "start"]
