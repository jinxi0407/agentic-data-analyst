"""Initialize the project MySQL schema from data/init.sql."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymysql
from pymysql.constants import CLIENT

from app.config import settings


def main() -> None:
    sql_text = (ROOT / "data" / "init.sql").read_text(encoding="utf-8")
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user="root",
        password=settings.mysql_root_password,
        charset="utf8mb4",
        autocommit=True,
        client_flag=CLIENT.MULTI_STATEMENTS,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql_text)
            while cursor.nextset():
                pass
    finally:
        conn.close()
    print("Initialized schema from data/init.sql.")


if __name__ == "__main__":
    main()
