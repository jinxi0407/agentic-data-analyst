"""DashScope/Qwen client wrappers.

All API keys and model names come from environment variables through app.config.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from contextlib import contextmanager
from contextvars import ContextVar

from app.config import settings


class QwenConfigError(RuntimeError):
    pass


_usage = ContextVar("qwen_usage", default=None)


@contextmanager
def capture_usage():
    records = []
    token = _usage.set(records)
    try:
        yield records
    finally:
        _usage.reset(token)


def _require_dashscope():
    if not settings.dashscope_api_key:
        raise QwenConfigError("DASHSCOPE_API_KEY is empty. Fill .env before live Qwen calls.")
    if not settings.qwen_chat_model:
        raise QwenConfigError("QWEN_CHAT_MODEL is empty. Fill .env before chat generation.")
    try:
        import dashscope
    except ImportError as exc:
        raise QwenConfigError("dashscope package is not installed.") from exc
    dashscope.api_key = settings.dashscope_api_key
    if settings.dashscope_base_url:
        dashscope.base_http_api_url = settings.dashscope_base_url
    return dashscope


def generate_text(messages: List[Dict[str, str]], temperature: float = 0.1,
                  response_format: dict | None = None, *,
                  request_timeout: tuple[float, float] | None = None) -> str:
    dashscope = _require_dashscope()
    records = _usage.get()
    record = {"input_tokens": None, "output_tokens": None, "status": "transport_error"}
    if records is not None:
        records.append(record)
    kwargs = {"response_format": response_format} if response_format is not None else {}
    if request_timeout is not None:
        kwargs["request_timeout"] = request_timeout
    response = dashscope.Generation.call(
        model=settings.qwen_chat_model,
        messages=messages,
        temperature=temperature,
        result_format="message",
        **kwargs,
    )
    usage = response.get("usage") or {}
    record.update(input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
                  status="ok" if getattr(response, "status_code", 200) == 200 else "api_error")
    if getattr(response, "status_code", 200) != 200:
        raise RuntimeError(f"Qwen chat call failed: {getattr(response, 'message', response)}")

    output = response.get("output") if isinstance(response, dict) else response.output
    choices = output.get("choices") if isinstance(output, dict) else getattr(output, "choices", None)
    if choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else choices[0].message
        content = message.get("content") if isinstance(message, dict) else message.content
        return str(content).strip()
    text = output.get("text") if isinstance(output, dict) else getattr(output, "text", "")
    return str(text).strip()


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not settings.dashscope_api_key:
        raise QwenConfigError("DASHSCOPE_API_KEY is empty. Fill .env before embedding calls.")
    if not settings.qwen_embedding_model:
        raise QwenConfigError("QWEN_EMBEDDING_MODEL is empty. Fill .env before schema embeddings.")
    try:
        import dashscope
    except ImportError as exc:
        raise QwenConfigError("dashscope package is not installed.") from exc
    dashscope.api_key = settings.dashscope_api_key
    if settings.dashscope_base_url:
        dashscope.base_http_api_url = settings.dashscope_base_url

    vectors: List[List[float]] = []
    batch_size = 10
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        kwargs = {"model": settings.qwen_embedding_model, "input": batch}
        if settings.qwen_embedding_dimension:
            kwargs["dimension"] = settings.qwen_embedding_dimension
        response = dashscope.TextEmbedding.call(**kwargs)
        if getattr(response, "status_code", 200) != 200:
            raise RuntimeError(f"Qwen embedding call failed: {getattr(response, 'message', response)}")

        output = response.get("output") if isinstance(response, dict) else response.output
        embeddings = output.get("embeddings") if isinstance(output, dict) else output.embeddings
        batch_vectors: List[Optional[List[float]]] = [None] * len(batch)
        for item in embeddings:
            idx = item.get("text_index", item.get("index", 0)) if isinstance(item, dict) else item.text_index
            emb = item.get("embedding") if isinstance(item, dict) else item.embedding
            batch_vectors[int(idx)] = [float(x) for x in emb]
        vectors.extend([v or [] for v in batch_vectors])
    return vectors
