"""Схема, начальные данные и права ролей."""

import psycopg
import pytest


def test_seed(owner):
    assert owner.execute("SELECT code FROM core.marketplaces").fetchall() == [("wb",)]
    shops = owner.execute("SELECT id, code FROM line.workshops ORDER BY id").fetchall()
    assert [c for _, c in shops] == ["leads", "mini_audit", "funnel", "sales", "monitoring", "retention"]
    ages = dict(owner.execute("SELECT code, max_age::text FROM line.buffers").fetchall())
    assert ages == {"leads_store": "14 days", "mini_audit_store": "7 days", "onboarding": "1 day"}


def test_worker_has_no_pd_access(database):
    with psycopg.connect(database["worker"], autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM pd.telegram_links")


def test_bot_has_pd_access(database):
    with psycopg.connect(database["bot"], autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM pd.telegram_links").fetchone()[0] == 0


@pytest.mark.parametrize("role", ["bot", "worker"])
def test_roles_work_with_line(database, role):
    with psycopg.connect(database[role], autocommit=True) as conn:
        conn.execute("SELECT * FROM line.buffer_stats").fetchall()
        conn.execute("SELECT * FROM billing.tariffs").fetchall()
        conn.execute("SELECT * FROM growth.rules").fetchall()


@pytest.mark.parametrize("role", ["bot", "worker"])
def test_fixed_rules_are_read_only(database, role):
    with psycopg.connect(database[role], autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE growth.rules SET value = '0.9' WHERE code = 'dev_share'")


def test_roles_sql_is_idempotent(database):
    from conftest import ROOT
    with psycopg.connect(database["owner"], autocommit=True) as conn:
        conn.execute((ROOT / "db/roles.sql").read_text(encoding="utf-8"))
