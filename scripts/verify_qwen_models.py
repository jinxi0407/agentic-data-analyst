"""Verify DashScope chat and embedding models without printing secrets."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.tools.qwen import embed_texts, generate_text


if __name__ == "__main__":
    if not settings.dashscope_api_key:
        raise SystemExit("DASHSCOPE_API_KEY is empty. Fill .env before verifying Qwen models.")
    if not settings.qwen_chat_model or not settings.qwen_embedding_model:
        raise SystemExit("QWEN_CHAT_MODEL or QWEN_EMBEDDING_MODEL is empty. Fill model names before verifying.")
    chat = generate_text(
        [
            {"role": "system", "content": "Return exactly OK."},
            {"role": "user", "content": "ping"},
        ],
        temperature=0.0,
    )
    vector = embed_texts(["schema retrieval ping"])[0]
    if not chat or not vector:
        raise SystemExit("Qwen verification failed.")
    print("Qwen chat and embedding verification succeeded.")
