"""Project-owned API/UI lifecycle. MySQL data is never initialized here."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / ".run"
LOGS = ROOT / "logs"
PYTHON = ROOT / ".venv/bin/python"
SERVICES = {"fastapi": (8002, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"], "/health"),
            "streamlit": (8502, ["-m", "streamlit", "run", str(ROOT / "ui/app.py"), "--server.port", "8502",
                                 "--server.address", "127.0.0.1", "--server.headless", "true"], "/_stcore/health")}


def identity(pid):
    state = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
    if state.returncode or "Z" in state.stdout:
        return ""
    result = subprocess.run(["ps", "-p", str(pid), "-o", "uid=", "-o", "lstart=", "-o", "command="],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def owns(name, pid, record):
    current = identity(pid)
    if not current or current != record.get("identity") or record.get("root") != str(ROOT):
        return False
    if record.get("service") != name or int(current.split()[0]) != os.getuid():
        return False
    expected = " ".join([str(PYTHON), *SERVICES[name][1]])
    return expected in current


def stop(name):
    path = RUN / f"{name}.pid"
    if not path.exists():
        return
    try:
        pid = int(path.read_text())
        record = json.loads((RUN / f"{name}.json").read_text())
    except (ValueError, OSError):
        raise RuntimeError(f"Invalid {name} PID record; refusing to stop an unverified process")
    if identity(pid):
        if not owns(name, pid, record):
            raise RuntimeError(f"{name} PID ownership changed; no process was stopped")
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not identity(pid):
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
                break
            time.sleep(.1)
        else:
            raise RuntimeError(f"{name} did not exit; refusing to kill forcibly")
    path.unlink(missing_ok=True)
    (RUN / f"{name}.json").unlink(missing_ok=True)


def free_port(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise RuntimeError(f"Port {port} is occupied by an untracked process. Stop it manually; no unknown PID was killed.")


def healthy(url, process):
    for _ in range(360):
        if process.poll() is not None:
            raise RuntimeError("Service exited during startup; inspect project logs")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(.5)
    raise RuntimeError("Service health check timed out; inspect project logs")


def start():
    stamp = runtime_fingerprint()
    reusable = {name: can_reuse(name, stamp) for name in SERVICES}
    for name, (port, _, _) in SERVICES.items():
        if not reusable[name]:
            stop(name)
            free_port(port)
    # Resolve only the mysql service belonging to this compose file.
    subprocess.run(["docker", "compose", "up", "-d", "mysql"], cwd=ROOT, check=True)
    container = subprocess.check_output(["docker", "compose", "ps", "-q", "mysql"], cwd=ROOT, text=True).strip()
    if not container:
        raise RuntimeError("Current project's MySQL container is missing")
    for _ in range(90):
        health = subprocess.check_output(["docker", "inspect", "--format", "{{.State.Health.Status}}", container], text=True).strip()
        if health == "healthy":
            break
        time.sleep(1)
    else:
        raise RuntimeError("Current project's MySQL did not become healthy")
    started = []
    try:
        for name, (port, args, endpoint) in SERVICES.items():
            if reusable[name]:
                print(f"{name}: reusing healthy project process", flush=True)
                continue
            env = os.environ.copy()
            env.update(API_HOST="127.0.0.1", API_PORT="8002", UI_PORT="8502", PYTHONUNBUFFERED="1")
            with (LOGS / f"{name}.log").open("ab") as log:
                process = subprocess.Popen([str(PYTHON), *args], cwd=ROOT, env=env,
                                           stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
            time.sleep(.1)
            record = {"root": str(ROOT), "service": name, "identity": identity(process.pid),
                      "runtime_fingerprint": stamp}
            (RUN / f"{name}.json").write_text(json.dumps(record))
            (RUN / f"{name}.pid").write_text(str(process.pid))
            started.append(name)
            healthy(f"http://127.0.0.1:{port}{endpoint}", process)
            print(f"{name}: healthy, PID {process.pid}", flush=True)
    except Exception:
        for name in reversed(started):
            try:
                stop(name)
            except RuntimeError as cleanup_error:
                print(f"Cleanup: {cleanup_error}", file=sys.stderr)
        raise
    print(f"UI: http://127.0.0.1:8502\nAPI Docs: http://127.0.0.1:8002/docs\nLogs: {LOGS}")
    if sys.platform == "darwin" and os.getenv("OPEN_BROWSER", "1") == "1":
        subprocess.run(["open", "http://127.0.0.1:8502"], check=False)


def runtime_fingerprint():
    digest = hashlib.sha256()
    files = sorted((ROOT / "app").rglob("*.py")) + [
        ROOT / "ui/app.py", ROOT / "eval/strong_baseline.py",
        ROOT / "eval/strong_baseline_v2.py", ROOT / ".env"]
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def can_reuse(name, stamp):
    try:
        pid = int((RUN / f"{name}.pid").read_text())
        record = json.loads((RUN / f"{name}.json").read_text())
        if not owns(name, pid, record) or record.get("runtime_fingerprint") != stamp:
            return False
        port, _, endpoint = SERVICES[name]
        with urlopen(f"http://127.0.0.1:{port}{endpoint}", timeout=2) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def main():
    os.chdir(ROOT)
    RUN.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    with (RUN / "services.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another project start/stop command is running")
        try:
            if len(sys.argv) == 2 and sys.argv[1] == "start":
                start()
            elif len(sys.argv) == 2 and sys.argv[1] == "stop":
                for name in reversed(SERVICES):
                    stop(name)
                print("Recorded project API/UI processes stopped. MySQL left running.")
            else:
                raise RuntimeError("Usage: local_services.py start|stop")
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
