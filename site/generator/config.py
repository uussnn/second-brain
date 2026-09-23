"""Настройки сайта. Всё, что зависит от владельца, приходит из окружения,
в коде и в git не хранится (см. site/settings.env.example)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SITE_ROOT = Path(__file__).resolve().parent.parent  # site/


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    domain: str | None
    name: str
    telegram_bot: str | None
    owner_name: str | None
    owner_inn: str | None

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}" if self.domain else "http://localhost:8000"

    @property
    def bot_url(self) -> str | None:
        return f"https://t.me/{self.telegram_bot}" if self.telegram_bot else None

    def url(self, path: str) -> str:
        return self.base_url + path


def _get(env, key: str) -> str | None:
    value = (env.get(key) or "").strip()
    return value or None


def load_settings(env=None, strict: bool = False) -> Settings:
    """strict=True — боевая сборка: пустые настройки владельца = ошибка."""
    env = os.environ if env is None else env
    s = Settings(
        domain=_get(env, "SITE_DOMAIN"),
        name=_get(env, "SITE_NAME") or "GEO-аудит",
        telegram_bot=(_get(env, "TELEGRAM_BOT") or "").lstrip("@") or None,
        owner_name=_get(env, "OWNER_NAME"),
        owner_inn=_get(env, "OWNER_INN"),
    )
    if s.domain and not re.fullmatch(r"[a-z0-9.-]+(:\d+)?", s.domain):
        raise ConfigError(f"SITE_DOMAIN: некорректный домен {s.domain!r}")
    if s.telegram_bot and not re.fullmatch(r"[A-Za-z0-9_]{5,32}", s.telegram_bot):
        raise ConfigError(f"TELEGRAM_BOT: некорректное имя бота {s.telegram_bot!r}")
    if s.owner_inn and not re.fullmatch(r"\d{12}", s.owner_inn):
        raise ConfigError("OWNER_INN: ИНН физлица — 12 цифр")
    if strict:
        missing = [k for k, v in {
            "SITE_DOMAIN": s.domain, "TELEGRAM_BOT": s.telegram_bot,
            "OWNER_NAME": s.owner_name, "OWNER_INN": s.owner_inn,
        }.items() if not v]
        if missing:
            raise ConfigError("не заданы настройки: " + ", ".join(missing))
    return s
