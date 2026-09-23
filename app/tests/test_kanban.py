"""Канбан: взять, закрыть, передать дальше, повторить, изолировать, просрочить."""

import datetime as dt

import pytest

from factory import kanban
from factory.kanban import Card, Defect, Result
from factory.worker import Worker


def put(conn, buffer="leads_store", payload=None, **kw):
    return kanban.enqueue(conn, Card(buffer, payload or {"shop": 1}, **kw))


def status(conn, item_id):
    return conn.execute("SELECT status FROM line.work_items WHERE id = %s", (item_id,)).fetchone()[0]


def test_buffers_of(worker_conn):
    assert kanban.buffers_of(worker_conn, "mini_audit") == ["leads_store"]
    assert kanban.buffers_of(worker_conn, "leads") == []


def test_claim_complete_with_children(worker_conn):
    a = put(worker_conn)
    item = kanban.claim(worker_conn, ["leads_store"], "w1")
    assert item.id == a and item.attempts == 1 and status(worker_conn, a) == "in_progress"
    assert kanban.claim(worker_conn, ["leads_store"], "w2") is None
    kanban.complete(worker_conn, item, Result([Card("mini_audit_store", {"report": 7})]))
    assert status(worker_conn, a) == "done"
    child = worker_conn.execute(
        "SELECT buffer_code, payload, parent_id FROM line.work_items WHERE id <> %s", (a,)).fetchone()
    assert child == ("mini_audit_store", {"report": 7}, a)


def test_priority_and_schedule(worker_conn):
    low = put(worker_conn, priority=0)
    high = put(worker_conn, priority=5)
    later = put(worker_conn, priority=9,
                scheduled_for=dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1))
    assert kanban.claim(worker_conn, ["leads_store"], "w").id == high
    assert kanban.claim(worker_conn, ["leads_store"], "w").id == low
    assert kanban.claim(worker_conn, ["leads_store"], "w") is None  # хейдзунка: ещё не время
    assert status(worker_conn, later) == "queued"


def test_full_downstream_buffer_returns_item(owner, worker_conn):
    owner.execute("UPDATE line.buffers SET card_limit = 1 WHERE code = 'mini_audit_store'")
    try:
        put(worker_conn, "mini_audit_store")
        a = put(worker_conn)
        item = kanban.claim(worker_conn, ["leads_store"], "w")
        with pytest.raises(kanban.BufferFull):
            kanban.complete(worker_conn, item, Result([Card("mini_audit_store", {})]))
        row = worker_conn.execute(
            "SELECT status, attempts, scheduled_for > now() FROM line.work_items WHERE id = %s", (a,)).fetchone()
        assert row == ("queued", 0, True)  # ждёт, попытка не потрачена
        n = worker_conn.execute(
            "SELECT count(*) FROM line.work_items WHERE buffer_code = 'mini_audit_store'").fetchone()[0]
        assert n == 1  # дочерняя карточка не создана
    finally:
        owner.execute("UPDATE line.buffers SET card_limit = 100 WHERE code = 'mini_audit_store'")


def test_retry_then_quarantine(owner, worker_conn):
    a = put(worker_conn)
    for attempt in range(1, kanban.MAX_ATTEMPTS + 1):
        owner.execute("UPDATE line.work_items SET scheduled_for = now() WHERE id = %s", (a,))
        item = kanban.claim(worker_conn, ["leads_store"], "w")
        outcome = kanban.fail(worker_conn, item, RuntimeError("API 502"))
        assert outcome == ("retry" if attempt < kanban.MAX_ATTEMPTS else "quarantined")
    assert status(worker_conn, a) == "quarantined"
    d = worker_conn.execute("SELECT check_code, decision, details->>'message' FROM line.defects").fetchone()
    assert d == ("handler_failed", "escalate", "API 502")


def test_defect_goes_straight_to_quarantine(worker_conn):
    a = put(worker_conn)
    item = kanban.claim(worker_conn, ["leads_store"], "w")
    assert kanban.fail(worker_conn, item, Defect("mention_not_in_raw", {"brand": "X"})) == "quarantined"
    d = worker_conn.execute("SELECT check_code, details->>'brand' FROM line.defects").fetchone()
    assert d == ("mention_not_in_raw", "X") and status(worker_conn, a) == "quarantined"


def test_expire_old_cards(owner, worker_conn):
    old = put(worker_conn)
    fresh = put(worker_conn)
    owner.execute("UPDATE line.work_items SET enqueued_at = now() - interval '15 days' WHERE id = %s", (old,))
    assert kanban.expire(worker_conn, ["leads_store"]) == 1
    assert status(worker_conn, old) == "expired" and status(worker_conn, fresh) == "queued"
    assert worker_conn.execute("SELECT check_code, decision FROM line.defects").fetchone() == ("expired", "discard")


def test_recover_stale(owner, worker_conn):
    a = put(worker_conn)
    kanban.claim(worker_conn, ["leads_store"], "dead-worker")
    owner.execute("UPDATE line.work_items SET started_at = now() - interval '1 hour' WHERE id = %s", (a,))
    assert kanban.recover_stale(worker_conn, ["leads_store"]) == 1
    assert status(worker_conn, a) == "queued"


def test_card_limit_trigger(owner, worker_conn):
    owner.execute("UPDATE line.buffers SET card_limit = 2 WHERE code = 'onboarding'")
    try:
        put(worker_conn, "onboarding")
        put(worker_conn, "onboarding")
        with pytest.raises(kanban.BufferFull):
            put(worker_conn, "onboarding")
    finally:
        owner.execute("UPDATE line.buffers SET card_limit = 20 WHERE code = 'onboarding'")


def test_worker_step_stub_quarantines(worker_conn):
    a = put(worker_conn)
    w = Worker("mini_audit")
    assert w.step(worker_conn, ["leads_store"]) is True
    assert status(worker_conn, a) == "quarantined"
    assert worker_conn.execute("SELECT check_code FROM line.defects").fetchone() == ("not_implemented",)
    assert w.step(worker_conn, ["leads_store"]) is False


def test_worker_step_passes_downstream(monkeypatch, worker_conn):
    from factory import handlers
    monkeypatch.setitem(handlers.HANDLERS, "leads_store",
                        lambda item: Result([Card("mini_audit_store", {"from": item.id})]))
    a = put(worker_conn)
    assert Worker("mini_audit").step(worker_conn, ["leads_store"]) is True
    assert status(worker_conn, a) == "done"
    assert worker_conn.execute(
        "SELECT payload->>'from' FROM line.work_items WHERE buffer_code = 'mini_audit_store'"
    ).fetchone() == (str(a),)
