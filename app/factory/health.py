"""Healthcheck для Docker: процесс жив, если давно обновлял файл сердцебиения."""

import os
import sys
import time
from pathlib import Path

HEARTBEAT = Path(os.environ.get("HEARTBEAT_FILE", "/tmp/heartbeat"))
MAX_AGE = int(os.environ.get("HEALTH_MAX_AGE", "900"))  # дольше самой долгой обработки карточки


def beat() -> None:
    HEARTBEAT.touch()


def main() -> int:
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
    except FileNotFoundError:
        print("нет сердцебиения")
        return 1
    if age > MAX_AGE:
        print(f"сердцебиение {age:.0f} с назад")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
