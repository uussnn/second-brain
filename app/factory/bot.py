"""Telegram-бот (цех 3, воронка) — пока заглушка.

Проверяет, что у него есть всё нужное для работы: токен принят Telegram,
доступ к схеме pd есть. Затем ждёт, поддерживая сердцебиение.
Настоящий бот заменит run(); он же будет разбирать буфер mini_audit_store.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
import urllib.error
import urllib.request

import psycopg

from . import health
from .db import connect

log = logging.getLogger("factory.bot")
running = True


def stop(*_):
    global running
    running = False


def telegram_me(token: str) -> str:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=15) as r:
        data = json.load(r)
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram отказал"))
    return data["result"]["username"]


def self_check(token: str) -> None:
    with connect() as conn:
        n = conn.execute("SELECT count(*) FROM pd.telegram_links").fetchone()[0]
    log.info("доступ к pd есть, согласий: %d", n)
    try:
        log.info("Telegram принял токен: @%s", telegram_me(token))
    except urllib.error.HTTPError as e:
        log.error("Telegram отклонил токен: HTTP %s", e.code)  # сам токен в лог не пишем
    except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
        log.error("Telegram недоступен: %s", e)


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("не задан TELEGRAM_BOT_TOKEN")
    checked = False
    while running:
        if not checked:
            try:
                self_check(token)
                checked = True
                log.info("заглушка бота: логика воронки ещё не реализована")
            except psycopg.OperationalError as e:
                log.error("нет связи с базой: %s", e)  # сердцебиения нет — бот нездоров
        if checked:
            health.beat()
        time.sleep(10)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()
