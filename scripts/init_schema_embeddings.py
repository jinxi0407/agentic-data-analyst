"""Refresh schema metadata embeddings using DashScope."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schema.metadata import refresh_schema_embeddings


if __name__ == "__main__":
    count = refresh_schema_embeddings()
    print(f"Schema embeddings refreshed: {count}")
