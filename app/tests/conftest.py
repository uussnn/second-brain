"""Интеграционные тесты на настоящем PostgreSQL 16.

TEST_DATABASE_URL — суперпользователь тестового сервера, например:
  docker run -d --name pgtest -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
  TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres make test-factory
Каждый прогон создаёт отдельную базу и удаляет её после тестов.
"""

import os
import secrets
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

APP = Path(__file__).resolve().parent.parent
ROOT = APP.parent
sys.path.insert(0, str(APP))

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.skip("не задан TEST_DATABASE_URL", allow_module_level=True)


@pytest.fixture(scope="session")
def database():
    name = "factory_test_" + secrets.token_hex(4)
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base = conninfo_to_dict(ADMIN_URL)
    owner = make_conninfo(**{**base, "dbname": name})
    pw = {"bot": secrets.token_hex(12), "worker": secrets.token_hex(12)}
    with psycopg.connect(owner, autocommit=True) as conn:
        conn.execute((ROOT / "schema_v0_1.sql").read_text(encoding="utf-8"))
        conn.execute((ROOT / "db/02-seed.sql").read_text(encoding="utf-8"))
        conn.execute((ROOT / "db/roles.sql").read_text(encoding="utf-8"))
        conn.execute(f"ALTER ROLE bot_role PASSWORD '{pw['bot']}'")
        conn.execute(f"ALTER ROLE worker_role PASSWORD '{pw['worker']}'")
    urls = {
        "owner": owner,
        "bot": make_conninfo(**{**base, "dbname": name, "user": "bot_role", "password": pw["bot"]}),
        "worker": make_conninfo(**{**base, "dbname": name, "user": "worker_role", "password": pw["worker"]}),
    }
    yield urls
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture
def owner(database):
    with psycopg.connect(database["owner"], autocommit=True) as conn:
        conn.execute("TRUNCATE line.defects, line.work_items RESTART IDENTITY CASCADE")
        yield conn


@pytest.fixture
def worker_conn(database, owner):
    with psycopg.connect(database["worker"], autocommit=True) as conn:
        yield conn
