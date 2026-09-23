"""Чтение и проверка данных из site/data/.

Формат повторяет будущую выгрузку из PostgreSQL:
  ratings/<площадка>/<категория>/<ГГГГ-Wнн>.json — из core.scores (+ core.categories,
      core.measurements); share = core.scores.share, change — разница с прошлой неделей;
  tariffs.json — строки billing.tariffs; period — interval в ISO 8601
      (SET intervalstyle = 'iso_8601'), NULL для разовых.
Чтобы подключить базу, достаточно заменить функции load_* — шаблоны не меняются.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Признаки персональных данных, которые не должны попасть в публичные рейтинги.
PD_PATTERNS = [
    re.compile(r"(?<![А-Яа-яЁё])ИП\s+[А-ЯЁ][а-яё]+"),           # «ИП Иванов»
    re.compile(r"индивидуальный\s+предприниматель", re.I),
    re.compile(r"(?<!\d)\d{10}(?:\d{2})?(?!\d)"),                 # ИНН
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),                       # e-mail
    re.compile(r"(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}"),  # телефон
]


class DataError(Exception):
    pass


def find_pd(text: str) -> str | None:
    for rx in PD_PATTERNS:
        m = rx.search(text)
        if m:
            return m.group(0)
    return None


@dataclass
class BrandRow:
    rank: int
    brand: str
    share: float
    change: float | None


@dataclass
class Rating:
    marketplace: str
    slug: str
    name: str
    week: str
    measured_at: dt.date
    method: dict
    brands: list[BrandRow]
    source: Path

    @property
    def week_start(self) -> dt.date:
        y, w = map(int, WEEK_RE.match(self.week).groups())
        return dt.date.fromisocalendar(y, w, 1)

    @property
    def week_end(self) -> dt.date:
        return self.week_start + dt.timedelta(days=6)

    @property
    def category_path(self) -> str:
        return f"/ratings/{self.marketplace}/{self.slug}/"

    @property
    def archive_path(self) -> str:
        return f"{self.category_path}{self.week}/"


@dataclass
class Category:
    marketplace: str
    slug: str
    name: str
    weeks: list[Rating] = field(default_factory=list)  # по возрастанию недели

    @property
    def latest(self) -> Rating:
        return self.weeks[-1]

    @property
    def path(self) -> str:
        return f"/ratings/{self.marketplace}/{self.slug}/"


@dataclass
class Tariff:
    code: str
    name: str
    price_rub: Decimal
    period: str | None
    sku_limit: int | None
    is_active: bool


def _require(cond: bool, where: Path | str, msg: str) -> None:
    if not cond:
        raise DataError(f"{where}: {msg}")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_rating(path: Path, marketplace: str, slug: str) -> Rating:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise DataError(f"{path}: невалидный JSON: {e}") from e
    for key in ("category", "week", "measured_at", "method", "brands"):
        _require(key in d, path, f"нет поля {key!r}")
    cat = d["category"]
    _require(cat.get("marketplace") == marketplace, path, "category.marketplace не совпадает с папкой")
    _require(cat.get("slug") == slug, path, "category.slug не совпадает с папкой")
    _require(isinstance(cat.get("name"), str) and cat["name"].strip(), path, "пустое category.name")

    week = d["week"]
    m = WEEK_RE.match(str(week))
    _require(bool(m), path, f"неделя {week!r} не в формате ГГГГ-Wнн")
    _require(path.stem == week, path, "имя файла не совпадает с week")
    try:
        start = dt.date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
        measured = dt.date.fromisoformat(d["measured_at"])
    except (ValueError, TypeError) as e:
        raise DataError(f"{path}: {e}") from e
    _require(start <= measured <= start + dt.timedelta(days=6), path,
             "measured_at вне указанной недели")

    meth = d["method"]
    for key in ("queries", "models", "runs", "formula_version"):
        _require(key in meth, path, f"нет поля method.{key}")
    _require(isinstance(meth["models"], list) and meth["models"], path, "пустой method.models")

    rows = d["brands"]
    _require(isinstance(rows, list) and rows, path, "пустой список brands")
    brands: list[BrandRow] = []
    seen: set[str] = set()
    for i, r in enumerate(rows, 1):
        _require(r.get("rank") == i, path, f"rank должен идти подряд с 1 (строка {i})")
        name = r.get("brand")
        _require(isinstance(name, str) and name.strip(), path, f"пустой бренд в строке {i}")
        _require(name not in seen, path, f"бренд {name!r} повторяется")
        seen.add(name)
        pd = find_pd(name)
        _require(pd is None, path, f"похоже на персональные данные: {pd!r}")
        _require(_num(r.get("share")) and 0 <= r["share"] <= 1, path, f"share вне [0, 1] у {name!r}")
        ch = r.get("change")
        _require(ch is None or (_num(ch) and -1 <= ch <= 1), path, f"change вне [-1, 1] у {name!r}")
        if brands:
            _require(r["share"] <= brands[-1].share, path, "бренды должны идти по убыванию share")
        brands.append(BrandRow(i, name.strip(), float(r["share"]), None if ch is None else float(ch)))

    return Rating(marketplace, slug, cat["name"].strip(), week, measured, meth, brands, path)


def load_categories(data_dir: Path) -> list[Category]:
    root = data_dir / "ratings"
    cats: list[Category] = []
    for mp_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        _require(bool(SLUG_RE.match(mp_dir.name)), mp_dir, "имя площадки — латиница в нижнем регистре")
        for cat_dir in sorted(p for p in mp_dir.iterdir() if p.is_dir()):
            _require(bool(SLUG_RE.match(cat_dir.name)), cat_dir, "slug категории — латиница, цифры, дефис")
            weeks = [load_rating(f, mp_dir.name, cat_dir.name) for f in sorted(cat_dir.glob("*.json"))]
            _require(bool(weeks), cat_dir, "нет ни одной недели")
            weeks.sort(key=lambda r: r.week)
            cats.append(Category(mp_dir.name, cat_dir.name, weeks[-1].name, weeks))
    _require(bool(cats), root, "нет ни одной категории")
    cats.sort(key=lambda c: (c.marketplace, c.name))
    return cats


def load_tariffs(path: Path) -> list[Tariff]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(rows, list), path, "ожидается массив строк billing.tariffs")
    out: list[Tariff] = []
    codes: set[str] = set()
    for r in rows:
        for key in ("code", "name", "price_rub", "period", "sku_limit", "is_active"):
            _require(key in r, path, f"нет поля {key!r}")
        _require(r["code"] not in codes, path, f"код тарифа {r['code']!r} повторяется")
        codes.add(r["code"])
        _require(_num(r["price_rub"]) and r["price_rub"] >= 0, path, f"цена {r['code']}")
        _require(r["period"] in (None, "P1M", "P3M", "P6M", "P1Y"), path,
                 f"period {r['period']!r}: ожидается NULL или P1M/P3M/P6M/P1Y")
        out.append(Tariff(r["code"], r["name"], Decimal(str(r["price_rub"])), r["period"],
                          r["sku_limit"], bool(r["is_active"])))
    return out
