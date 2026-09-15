"""Request-scoped, redacted diagnostics; never record hidden reasoning or secrets."""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from app.config import settings

request_id = ContextVar("querymate_request_id", default="")
LOG_DIR = Path(__file__).resolve().parents[2] / "logs/clarification"
DECISION_FIELDS = {"decision", "critical_missing_slots", "ambiguity_type", "alternatives",
                   "clarification_question", "known_constraints", "missing_slots", "options", "resolved_slots"}


def redact(value):
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items()
                if not re.search(r"reasoning|thought|api_key|password|token|secret", str(k), re.I)}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value[:50]]
    if not isinstance(value, str):
        return value
    for key, secret in vars(settings).items():
        if re.search(r"key|password|token|secret", key, re.I) and isinstance(secret, str) and secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?:sk-[\w-]{16,}|gh[pousr]_[\w]{20,}|Bearer\s+\S+)", "[REDACTED]", value)
    return value[:6000]


def event(stage, **details):
    rid = request_id.get()
    if not rid:
        return
    row = {"request_id": rid, "time": datetime.now(timezone.utc).isoformat(),
           "stage": stage, **redact(details)}
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(LOG_DIR / f"{rid}.jsonl", os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        # Observability must not change query behavior on a full/unavailable disk.
        pass


def model_output(raw, **details):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        value = None
    event("gate_model_output", structured={k: v for k, v in value.items() if k in DECISION_FIELDS}
          if isinstance(value, dict) else None, json_object=isinstance(value, dict),
          characters=len(raw) if isinstance(raw, str) else None, **details)


def validation_error(exc, location, **details):
    errors = ([{"loc": e["loc"], "type": e["type"], "msg": e["msg"]}
               for e in exc.errors(include_input=False, include_context=False, include_url=False)]
              if hasattr(exc, "errors") else [{"loc": [], "type": type(exc).__name__, "msg": str(exc)}])
    event("validation_failed", location=location, errors=errors, **details)
