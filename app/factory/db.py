import os

import psycopg


def connect(url: str | None = None) -> psycopg.Connection:
    """autocommit: каждая conn.transaction() — настоящая транзакция, а не savepoint."""
    return psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=True,
                           application_name=os.environ.get("WORKER_ID", "factory"))
