import os
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://oms_user:oms_password@localhost:5432/oms",
)


def wait_for_database(retries: int = 20, delay_seconds: float = 1.5) -> None:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return
        except Exception as exc:  # pragma: no cover - startup resilience
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError("Database is not reachable") from last_error


@contextmanager
def get_connection():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def apply_schema(conn) -> None:
    init_sql = (ROOT_DIR / "database" / "init.sql").read_text(encoding="utf-8")
    for statement in init_sql.split(";"):
        if statement.strip():
            conn.execute(statement)
