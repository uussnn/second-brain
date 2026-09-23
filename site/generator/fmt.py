"""Форматирование чисел и дат по-русски. Одни и те же функции используют
шаблоны и тесты, поэтому текст в HTML проверяется побайтно."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

NBSP = " "
MINUS = "−"

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]


def _dec(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def pct(share: float) -> str:
    """0.31 -> '31,0 %'"""
    return f"{_dec(share * 100)}{NBSP}%"


def pp(change: float | None) -> str:
    """0.02 -> '+2,0 п.п.', None -> 'новый'"""
    if change is None:
        return "новый"
    value = round(change * 100, 1)
    if value > 0:
        sign = "+"
    elif value < 0:
        sign = MINUS
    else:
        sign = ""
    return f"{sign}{_dec(abs(value))}{NBSP}п.п."


def trend(change: float | None) -> str:
    if change is None:
        return "new"
    value = round(change * 100, 1)
    return "up" if value > 0 else "down" if value < 0 else "flat"


def date_ru(d: dt.date) -> str:
    return f"{d.day}{NBSP}{MONTHS_GEN[d.month - 1]} {d.year}"


def range_ru(a: dt.date, b: dt.date) -> str:
    if a.month == b.month:
        return f"{a.day}–{b.day}{NBSP}{MONTHS_GEN[b.month - 1]} {b.year}"
    if a.year == b.year:
        return f"{a.day}{NBSP}{MONTHS_GEN[a.month - 1]} – {date_ru(b)}"
    return f"{date_ru(a)} – {date_ru(b)}"


def rub(amount: Decimal) -> str:
    if amount == 0:
        return "бесплатно"
    whole = int(amount)
    text = f"{whole:,}".replace(",", NBSP)
    if amount != whole:
        text += "," + f"{amount:.2f}".split(".")[1]
    return f"{text}{NBSP}₽"


PERIODS = {None: "разово", "P1M": "в месяц", "P3M": "за 3 месяца",
           "P6M": "за 6 месяцев", "P1Y": "в год"}


def period(p: str | None) -> str:
    return PERIODS[p]


def plural(n: int, one: str, few: str, many: str) -> str:
    """plural(3, 'прогон', 'прогона', 'прогонов') -> '3 прогона'"""
    n10, n100 = n % 10, n % 100
    word = one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many
    return f"{n}{NBSP}{word}"


def num(x: float) -> str:
    """1.0 -> '1', 0.7 -> '0,7'"""
    return f"{x:g}".replace(".", ",")
