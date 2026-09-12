"""Restrict the application MySQL user to read-only access after seeding."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymysql

from app.config import settings


if __name__ == "__main__":
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user="root",
        password=settings.mysql_root_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"REVOKE ALL PRIVILEGES, GRANT OPTION FROM `{settings.mysql_user}`@`%`")
            cursor.execute(f"GRANT SELECT ON `{settings.mysql_database}`.* TO `{settings.mysql_user}`@`%`")
            cursor.execute("FLUSH PRIVILEGES")
        print("Application MySQL user is now read-only.")
    finally:
        conn.close()
