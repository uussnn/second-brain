"""Воркер цеха: python -m factory.worker --workshop mini_audit

Тянет карточки из буферов своего цеха, обрабатывает, передаёт дальше.
Раз в минуту убирает протухшие карточки и возвращает брошенные упавшими воркерами.
SIGTERM: дорабатывает текущую карточку и выходит.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import signal
import socket
import time

import psycopg

from . import health, kanban
from .db import connect
from .handlers import handler_for

log = logging.getLogger("factory.worker")


class Worker:
    def __init__(self, workshop: str, poll: float = 5.0, housekeeping_every: float = 60.0):
        self.workshop = workshop
        self.poll = poll
        self.housekeeping_every = housekeeping_every
        self.id = os.environ.get("WORKER_ID") or f"{workshop}@{socket.gethostname()}:{os.getpid()}"
        self.stopping = False
        self._last_housekeeping = 0.0

    def stop(self, *_):
        log.info("получен сигнал остановки, дорабатываю текущую карточку")
        self.stopping = True

    def housekeeping(self, conn, buffers) -> None:
        if time.monotonic() - self._last_housekeeping < self.housekeeping_every:
            return
        self._last_housekeeping = time.monotonic()
        expired = kanban.expire(conn, buffers)
        stale = kanban.recover_stale(conn, buffers)
        if expired or stale:
            log.info("просрочено: %d, возвращено брошенных: %d", expired, stale)

    def step(self, conn, buffers) -> bool:
        """Одна карточка. True — карточка была, False — буферы пусты."""
        self.housekeeping(conn, buffers)
        item = kanban.claim(conn, buffers, self.id)
        if item is None:
            return False
        try:
            result = handler_for(item.buffer_code)(item)
            kanban.complete(conn, item, result)
            log.info("карточка %d (%s) готова, дальше: %d", item.id, item.buffer_code,
                     len(result.children))
        except kanban.BufferFull as e:
            log.info("карточка %d ждёт: буфер %s полон", item.id, e)
        except psycopg.OperationalError:
            raise  # связь с базой — забота внешнего цикла; карточку вернёт recover_stale
        except Exception as e:  # noqa: BLE001 — останавливается деталь, а не линия
            outcome = kanban.fail(conn, item, e)
            log.warning("карточка %d (%s): %s — %s", item.id, item.buffer_code, e, outcome)
        return True

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        while not self.stopping:
            try:
                with connect() as conn:
                    buffers = kanban.buffers_of(conn, self.workshop)
                    if not buffers:
                        log.info("у цеха %s нет входных буферов: жду задач по расписанию", self.workshop)
                    else:
                        log.info("цех %s, буферы: %s", self.workshop, ", ".join(buffers))
                    while not self.stopping:
                        health.beat()
                        if not buffers or not self.step(conn, buffers):
                            time.sleep(self.poll * random.uniform(0.8, 1.2))
            except psycopg.OperationalError as e:
                # Сердцебиение не обновляем: без базы воркер нездоров
                log.error("нет связи с базой: %s; повтор через 10 с", e)
                time.sleep(10)
        log.info("остановлен")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workshop", default=os.environ.get("WORKSHOP"), required=not os.environ.get("WORKSHOP"))
    ap.add_argument("--poll", type=float, default=float(os.environ.get("POLL_INTERVAL", "5")))
    args = ap.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Worker(args.workshop, poll=args.poll).run()


if __name__ == "__main__":
    main()
