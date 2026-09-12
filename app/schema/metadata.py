"""Schema metadata retrieval and formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import settings
from app.tools.database import fetch_all
from app.tools.qwen import embed_texts


@dataclass(frozen=True)
class SchemaMatch:
    kind: str
    table: str
    column: Optional[str]
    datatype: Optional[str]
    description: str
    relationship: Optional[str]
    similarity: float


def cosine_similarity(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _loads_vector(raw: Optional[str]) -> Optional[List[float]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return [float(x) for x in parsed]
    return None


def list_schema_documents() -> List[Dict[str, Any]]:
    tables = fetch_all(
        """
        SELECT id, table_name, custom_comment, table_comment, relationship, embedding_json
        FROM core_table
        WHERE checked = 1
        ORDER BY id
        """
    )
    fields = fetch_all(
        """
        SELECT t.table_name, f.field_name, f.field_type, f.custom_comment,
               f.field_comment, f.relationship, f.embedding_json
        FROM core_field f
        JOIN core_table t ON t.id = f.table_id
        WHERE t.checked = 1 AND f.checked = 1
        ORDER BY t.id, f.field_index
        """
    )

    docs: List[Dict[str, Any]] = []
    for row in tables:
        docs.append(
            {
                "kind": "table",
                "table": row["table_name"],
                "column": None,
                "datatype": None,
                "description": row["custom_comment"] or row["table_comment"],
                "relationship": row["relationship"],
                "embedding": _loads_vector(row["embedding_json"]),
            }
        )
    for row in fields:
        docs.append(
            {
                "kind": "column",
                "table": row["table_name"],
                "column": row["field_name"],
                "datatype": row["field_type"],
                "description": row["custom_comment"] or row["field_comment"],
                "relationship": row["relationship"],
                "embedding": _loads_vector(row["embedding_json"]),
            }
        )
    return docs


def retrieve_relevant_schema(question: str) -> Dict[str, Any]:
    query_vector = embed_texts([question])[0]
    docs = list_schema_documents()

    scored: List[SchemaMatch] = []
    for doc in docs:
        vector = doc.get("embedding")
        if not vector:
            continue
        score = cosine_similarity(query_vector, vector)
        if score >= settings.schema_similarity_threshold:
            scored.append(
                SchemaMatch(
                    kind=doc["kind"],
                    table=doc["table"],
                    column=doc["column"],
                    datatype=doc["datatype"],
                    description=doc["description"],
                    relationship=doc["relationship"],
                    similarity=score,
                )
            )

    scored.sort(key=lambda item: item.similarity, reverse=True)
    top_matches = scored[: settings.schema_top_k]
    table_names = sorted({m.table for m in top_matches})
    table_names = _expand_required_relationship_tables(table_names)
    columns = [m for m in top_matches if m.kind == "column"]

    return {
        "matches": top_matches,
        "matched_tables": table_names,
        "matched_columns": [
            {
                "table": m.table,
                "column": m.column,
                "datatype": m.datatype,
                "description": m.description,
                "similarity": round(m.similarity, 4),
            }
            for m in columns
        ],
        "db_schema": build_schema_text(table_names),
    }


def _expand_required_relationship_tables(table_names: List[str]) -> List[str]:
    selected = set(table_names)
    if "orders" in selected:
        selected.add("users")
    if "order_items" in selected:
        selected.update({"orders", "products"})
    if "refunds" in selected:
        selected.update({"orders", "order_items", "products"})
    if "products" in selected and ("sales" in selected or "refunds" in selected):
        selected.add("order_items")
    return sorted(selected)


def build_schema_text(table_names: List[str]) -> str:
    if not table_names:
        return ""

    placeholders = ", ".join(["%s"] * len(table_names))
    tables = fetch_all(
        f"""
        SELECT id, table_name, table_comment, custom_comment, relationship
        FROM core_table
        WHERE checked = 1 AND table_name IN ({placeholders})
        ORDER BY FIELD(table_name, {placeholders})
        """,
        tuple(table_names + table_names),
    )

    parts = []
    for table in tables:
        fields = fetch_all(
            """
            SELECT field_name, field_type, custom_comment, relationship
            FROM core_field
            WHERE checked = 1 AND table_id = %s
            ORDER BY field_index
            """,
            (table["id"],),
        )
        lines = [
            f"TABLE {table['table_name']}: {table['custom_comment']}",
            f"RELATIONSHIP: {table['relationship']}",
            "COLUMNS:",
        ]
        for field in fields:
            rel = f" Relationship: {field['relationship']}." if field["relationship"] else ""
            lines.append(
                f"- {field['field_name']} {field['field_type']}: "
                f"{field['custom_comment']}.{rel}"
            )
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def refresh_schema_embeddings() -> int:
    table_rows = fetch_all(
        "SELECT id, custom_comment, table_comment, relationship FROM core_table WHERE checked = 1"
    )
    field_rows = fetch_all(
        "SELECT id, custom_comment, field_comment, relationship FROM core_field WHERE checked = 1"
    )

    documents = []
    for row in table_rows:
        documents.append(("core_table", row["id"], _document_text(row, "table_comment")))
    for row in field_rows:
        documents.append(("core_field", row["id"], _document_text(row, "field_comment")))

    vectors = embed_texts([text for _, _, text in documents])
    from app.tools.database import execute_write

    for (table_name, row_id, _), vector in zip(documents, vectors):
        execute_write(
            f"UPDATE {table_name} SET embedding_json = %s WHERE id = %s",
            (json.dumps(vector), row_id),
        )
    return len(documents)


def _document_text(row: Dict[str, Any], fallback_key: str) -> str:
    description = row.get("custom_comment") or row.get(fallback_key) or ""
    relationship = row.get("relationship") or ""
    return f"{description}\n关系: {relationship}"
