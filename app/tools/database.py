"""MySQL access helpers with read-only execution for agent SQL."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pymysql
from pymysql.cursors import DictCursor

from app.config import settings


def _connect(user: Optional[str] = None, password: Optional[str] = None):
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=user or settings.mysql_user,
        password=settings.mysql_password if password is None else password,
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )


@contextmanager
def connection(user: Optional[str] = None, password: Optional[str] = None):
    conn = _connect(user=user, password=password)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return [_json_safe_row(row) for row in cursor.fetchall()]


def execute_write(sql: str, params: Optional[Tuple[Any, ...]] = None) -> int:
    with connection(user="root", password=settings.mysql_root_password) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return int(cursor.rowcount)


def execute_agent_select(sql: str) -> List[Dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [_json_safe_row(row) for row in rows]


def ping() -> Dict[str, Any]:
    rows = fetch_all("SELECT VERSION() AS version, DATABASE() AS database_name")
    return rows[0] if rows else {}


def _json_safe_row(row: Dict[str, Any]) -> Dict[str, Any]:
    converted: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            converted[key] = float(value)
        elif hasattr(value, "isoformat"):
            converted[key] = value.isoformat()
        else:
            converted[key] = value
    return converted
