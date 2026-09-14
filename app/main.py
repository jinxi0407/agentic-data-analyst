"""FastAPI entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator
from typing import Literal

from app.agent.production import run_interactive
from app.agent.clarification import ClarificationContext
from app.config import settings
from app.tools.database import ping
from app.agent import scoped_clarification as scoped


app = FastAPI(title="Agentic Data Analyst", version="1.1.0")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=6000)
    clarification_answer: str | None = Field(default=None, min_length=1, max_length=2000)
    clarification_context: ClarificationContext | None = None

    @model_validator(mode="after")
    def complete_followup(self):
        if not self.question.strip():
            raise ValueError("Question cannot be blank")
        if (self.clarification_answer is None) != (self.clarification_context is None):
            raise ValueError("Follow-up requires both answer and context")
        if self.clarification_answer is not None and not self.clarification_answer.strip():
            raise ValueError("Answer cannot be blank")
        if self.clarification_context and self.question != self.clarification_context.original_question:
            raise ValueError("Follow-up question must match original question")
        return self


@app.get("/health")
def health():
    db = ping()
    return {"status": "ok", "database": db.get("database_name"), "mysql_version": db.get("version")}


@app.post("/api/query")
def query(request: QueryRequest):
    return run_interactive(request.question, request.clarification_answer,
                           request.clarification_context)


class ScopedQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    mode: Literal["direct", "clarify"] = "direct"
    clarification_answer: str | None = Field(default=None, min_length=1, max_length=2000)
    clarification_context: scoped.Context | None = None

    @model_validator(mode="after")
    def valid_followup(self):
        if not self.question.strip():
            raise ValueError("Question cannot be blank")
        if (self.clarification_answer is None) != (self.clarification_context is None):
            raise ValueError("Follow-up requires both answer and context")
        if self.clarification_context:
            if self.mode != "clarify" or self.question != self.clarification_context.original_question:
                raise ValueError("Follow-up must match original question and mode")
            if not self.clarification_answer.strip():
                raise ValueError("Answer cannot be blank")
        return self


@app.post("/api/scoped-query")
def scoped_query(request: ScopedQueryRequest):
    if request.mode == "clarify":
        return scoped.run_interactive(request.question, request.clarification_answer,
                                      request.clarification_context)
    try:
        return scoped.direct(request.question)
    except Exception:
        return {"status": "system_error", "error": "查询服务未完成，请稍后重试。", "result": [], "sql": ""}
