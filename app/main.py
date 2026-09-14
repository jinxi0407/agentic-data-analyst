"""FastAPI entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.agent.production import run_question
from app.config import settings
from app.tools.database import ping


app = FastAPI(title="Agentic Data Analyst", version="1.0.0")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)


@app.get("/health")
def health():
    db = ping()
    return {"status": "ok", "database": db.get("database_name"), "mysql_version": db.get("version")}


@app.post("/api/query")
def query(request: QueryRequest):
    state = run_question(request.question)
    return {
        "question": request.question,
        "engine": "Production NL2SQL Engine",
        "sql": state.get("sql", ""),
        "retry_count": state.get("retry_count", 0),
        "result": state.get("result", []),
        "latency_ms": state.get("latency_ms", 0),
        "trace": state.get("trace", []),
        "status": state.get("status", "unknown"),
    }
