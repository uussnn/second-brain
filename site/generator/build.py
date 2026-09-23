"""Сборка статического сайта: site/data + site/templates -> site/dist.

Любая ошибка в данных или шаблонах прерывает сборку с ненулевым кодом:
сайт выкатывается автоматически, и лучше не выкатить, чем выкатить брак.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import fmt
from .config import SITE_ROOT, ConfigError, Settings, load_settings
from .data import Category, DataError, Formula, Rating, load_categories, load_formulas, load_tariffs

AI_CRAWLERS = ["YandexBot", "Googlebot", "Bingbot", "PerplexityBot", "OAI-SearchBot",
               "ChatGPT-User", "GPTBot", "ClaudeBot", "Claude-SearchBot"]


class BuildError(Exception):
    pass


@dataclass
class Page:
    path: str                      # URL-путь, всегда со слешем на конце
    template: str
    title: str
    description: str
    lastmod: dt.date
    ctx: dict = field(default_factory=dict)
    jsonld: list[dict] = field(default_factory=list)
    in_sitemap: bool = True
    noindex: bool = False


# ---------------------------------------------------------------- тексты

def rating_summary(r: Rating) -> str:
    """Короткий вывод «ответ сначала»: 2–3 предложения из данных."""
    b = r.brands
    s = f"Чаще всего ИИ-ассистенты рекомендуют {b[0].brand}: {fmt.pct(b[0].share)} ответов"
    if len(b) >= 3:
        s += f", следом идут {b[1].brand} ({fmt.pct(b[1].share)}) и {b[2].brand} ({fmt.pct(b[2].share)})"
    elif len(b) == 2:
        s += f", следом — {b[1].brand} ({fmt.pct(b[1].share)})"
    parts = [s + "."]

    known = [x for x in b if x.change is not None]
    if not known:
        parts.append("Это первый замер категории, изменений за неделю пока нет.")
        return " ".join(parts)
    up = max(known, key=lambda x: x.change)
    down = min(known, key=lambda x: x.change)
    moves = []
    if fmt.trend(up.change) == "up":
        moves.append(f"сильнее всех выросла доля {up.brand} ({fmt.pp(up.change)})")
    if fmt.trend(down.change) == "down":
        moves.append(f"{'а ' if moves else 'сильнее всех '}снизилась — у {down.brand} ({fmt.pp(down.change)})")
    if moves:
        parts.append("За неделю " + ", ".join(moves) + ".")
    else:
        parts.append("За неделю доли брендов не изменились.")
    new = [x.brand for x in b if x.change is None]
    if new:
        parts.append("Впервые в рейтинге: " + ", ".join(new) + ".")
    return " ".join(parts)


def weights_text(f: Formula) -> str:
    parts = [f"{i}-я позиция — {fmt.num(w)}" for i, w in enumerate(f.position_weights, 1)]
    n = len(f.position_weights)
    tail = (f"{n + 1}-я и ниже — {fmt.num(f.tail_weight)}" if f.tail_weight
            else f"ниже {n}-й позиции упоминания не учитываются")
    return ", ".join(parts + [tail])


def method_faq(cats: list[Category], formulas: dict[str, Formula]) -> list[tuple[str, str]]:
    latest = [c.latest for c in cats]
    models = sorted({m for r in latest for m in r.method["models"]})
    runs = sorted({r.method["runs"] for r in latest})
    queries = sorted({r.method["queries"] for r in latest})
    versions = sorted({str(r.method["formula_version"]) for r in latest})
    j = ", ".join
    return [
        ("Что показывает рейтинг?",
         "Как часто ИИ-ассистенты с веб-поиском называют бренд, когда покупатель просит совета "
         "по товарам категории. Главная метрика — доля в ответах ИИ с учётом позиции упоминания."),
        ("Какие запросы задаются ИИ?",
         f"Единый набор категории (сейчас в наборе {j(map(str, queries))}) из запросов четырёх типов: общие "
         "(«какую палатку купить»), с ограничениями (бюджет, размер, условия), сравнительные "
         "и проблемные (запрос от задачи или неудачного опыта покупателя). Набор одинаков для всех "
         "брендов и замораживается: новая формулировка — новая версия набора. Брендовые запросы "
         "используются только в аудитах и в публичный рейтинг не входят."),
        ("Какие модели опрашиваются?",
         f"Только модели с веб-поиском, потому что покупатели получают от них ответы со ссылками. "
         f"В последнем замере: {j(models)}. Список расширяется, модели без поиска не используются."),
        ("Зачем задавать каждый запрос несколько раз?",
         f"Ответы ИИ нестабильны: один и тот же вопрос даёт разные списки брендов. Поэтому каждый "
         f"запрос задаётся несколько раз (сейчас — {j(map(str, runs))}), и в расчёт идут все ответы."),
        ("Как считается доля в ответах ИИ?",
         "Из каждого ответа извлекаются упомянутые бренды и их позиции, каждое упоминание сверяется "
         "с исходным текстом ответа. В каждом ответе бренд получает вес по позиции своего первого "
         "упоминания, если бренда в ответе нет — 0. Доля бренда — сумма этих весов по всем ответам, "
         "делённая на число ответов. "
         + " ".join(f"Веса в формуле {v}: {weights_text(formulas[v])}." for v in versions)
         + " Изменение за неделю — разница долей в процентных пунктах."),
        ("Что такое версии и можно ли сравнивать недели?",
         f"Наборы запросов, формула и извлечение упоминаний имеют версии. Новая версия не "
         f"переписывает старые замеры, а каждая страница рейтинга указывает версию формулы "
         f"(сейчас {j(versions)}). Сравнивать можно недели с одинаковой версией."),
        ("Меняются ли старые рейтинги?",
         "Нет. У каждой недели постоянный адрес вида /ratings/площадка/категория/ГГГГ-Wнн/, "
         "страница архива после публикации не меняется."),
    ]


# ---------------------------------------------------------------- JSON-LD

def base_graph(s: Settings) -> list[dict]:
    org = {"@type": "Organization", "@id": s.url("/#org"), "name": s.name,
           "url": s.url("/"), "logo": s.url("/static/icon.svg")}
    if s.bot_url:
        org["sameAs"] = [s.bot_url]
    site = {"@type": "WebSite", "@id": s.url("/#website"), "url": s.url("/"),
            "name": s.name, "inLanguage": "ru", "publisher": {"@id": s.url("/#org")}}
    return [org, site]


def breadcrumbs(s: Settings, items: list[tuple[str, str]]) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": s.url(path)}
        for i, (name, path) in enumerate(items, 1)]}


def rating_jsonld(s: Settings, r: Rating, page_path: str, summary: str) -> list[dict]:
    title = f"Кого рекомендует ИИ: {r.name}, {r.week}"
    dataset = {
        "@type": "Dataset",
        "name": title,
        "description": summary,
        "url": s.url(page_path),
        "sameAs": s.url(r.archive_path),
        "inLanguage": "ru",
        "isAccessibleForFree": True,
        "creator": {"@id": s.url("/#org")},
        "dateModified": r.measured_at.isoformat(),
        "temporalCoverage": f"{r.week_start.isoformat()}/{r.week_end.isoformat()}",
        "measurementTechnique": (f"{fmt.plural(r.method['queries'], 'запрос', 'запроса', 'запросов')} × "
                                 f"{fmt.plural(r.method['runs'], 'прогон', 'прогона', 'прогонов')} × "
                                 f"модели с веб-поиском ({', '.join(r.method['models'])}); "
                                 f"формула {r.method['formula_version']}"),
        "variableMeasured": [
            {"@type": "PropertyValue", "name": "Доля в ответах ИИ", "minValue": 0, "maxValue": 1,
             "description": "Доля ответов ИИ-ассистентов, где упомянут бренд, с весом по позиции"},
            {"@type": "PropertyValue", "name": "Изменение за неделю", "unitText": "процентные пункты"},
        ],
        "keywords": [r.name, "рекомендации ИИ", "GEO", "Wildberries" if r.marketplace == "wb" else r.marketplace],
    }
    items = {
        "@type": "ItemList",
        "name": title,
        "numberOfItems": len(r.brands),
        "itemListOrder": "https://schema.org/ItemListOrderDescending",
        "itemListElement": [
            {"@type": "ListItem", "position": b.rank, "name": b.brand,
             "description": f"Доля в ответах ИИ: {fmt.pct(b.share)}"} for b in r.brands],
    }
    return [dataset, items]


# ---------------------------------------------------------------- сборка

def make_env(s: Settings) -> Environment:
    env = Environment(loader=FileSystemLoader(SITE_ROOT / "templates"), autoescape=True,
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.policies["json.dumps_kwargs"] = {"ensure_ascii": False, "sort_keys": False}
    env.globals.update(site=s, fmt=fmt)
    env.filters.update(pct=fmt.pct, pp=fmt.pp, trend=fmt.trend, date_ru=fmt.date_ru,
                       rub=fmt.rub, period=fmt.period)
    return env


def copy_static(out: Path) -> str:
    """Копирует static/, дописывает классы ширины полос. Возвращает хэш CSS для сброса кэша."""
    dst = out / "static"
    shutil.copytree(SITE_ROOT / "static", dst)
    css = dst / "style.css"
    bars = "".join(f".w{i}{{--w:{i}%}}" for i in range(101))
    css.write_text(css.read_text(encoding="utf-8") + "\n/* ширина полос, генерируется */\n" + bars + "\n",
                   encoding="utf-8")
    return hashlib.sha256(css.read_bytes()).hexdigest()[:10]


def collect_pages(s: Settings, cats: list[Category], tariffs,
                  formulas: dict[str, Formula]) -> list[Page]:
    latest_date = max(c.latest.measured_at for c in cats)
    pages: list[Page] = []
    example = cats[0].latest

    pages.append(Page(
        "/", "index.html", f"{s.name} — кого рекомендует ИИ на маркетплейсах",
        "Измеряем, как часто ИИ-ассистенты с поиском рекомендуют бренды селлеров Wildberries. "
        "Еженедельные открытые рейтинги по категориям.",
        latest_date, {"cats": cats, "example": example, "example_summary": rating_summary(example)}))

    pages.append(Page(
        "/ratings/", "ratings.html", "Рейтинги: кого рекомендует ИИ по категориям",
        "Еженедельные рейтинги брендов по доле в ответах ИИ-ассистентов, по категориям маркетплейсов.",
        latest_date, {"cats": cats},
        jsonld=[breadcrumbs(s, [("Главная", "/"), ("Рейтинги", "/ratings/")]),
                {"@type": "ItemList", "name": "Рейтинги по категориям", "itemListElement": [
                    {"@type": "ListItem", "position": i, "name": c.name, "url": s.url(c.path)}
                    for i, c in enumerate(cats, 1)]}]))

    for c in cats:
        for r in c.weeks:
            is_current = r is c.latest
            for path, current in ([(c.path, True)] if is_current else []) + [(r.archive_path, False)]:
                summary = rating_summary(r)
                crumbs = [("Главная", "/"), ("Рейтинги", "/ratings/"), (c.name, c.path)]
                if not current:
                    crumbs.append((r.week, r.archive_path))
                pages.append(Page(
                    path, "rating.html",
                    f"Кого рекомендует ИИ: {r.name} — неделя {r.week}",
                    summary, r.measured_at,
                    {"cat": c, "r": r, "summary": summary, "is_current": current,
                     "is_latest": is_current},
                    jsonld=[breadcrumbs(s, crumbs)] + rating_jsonld(s, r, path, summary)))

    faq = method_faq(cats, formulas)
    pages.append(Page(
        "/method/", "method.html", "Методология: как измеряется доля в ответах ИИ",
        "Типы запросов, модели с веб-поиском, три прогона, формула доли в ответах ИИ и версии.",
        latest_date, {"faq": faq, "cats": cats,
                      "formulas": [formulas[v] for v in sorted(formulas)]},
        jsonld=[{"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]))

    active = [t for t in tariffs if t.is_active]
    if not active:
        raise BuildError("в tariffs.json нет активных тарифов")
    pages.append(Page(
        "/pricing/", "pricing.html", "Тарифы",
        "Бесплатный мини-аудит, полный аудит и ежемесячный мониторинг доли в ответах ИИ.",
        latest_date, {"tariffs": active}))

    for path, title in (("/offer/", "Публичная оферта"),
                        ("/privacy/", "Политика обработки персональных данных")):
        pages.append(Page(path, "draft.html", title, f"{title} — черновик.", latest_date,
                          {"doc_title": title}, in_sitemap=False, noindex=True))

    pages.append(Page("/contacts/", "contacts.html", "Контакты",
                      f"Контакты сервиса {s.name}.", latest_date))
    return pages


def render_page(env: Environment, s: Settings, p: Page, css_ver: str) -> str:
    graph = base_graph(s) + p.jsonld
    jsonld = {"@context": "https://schema.org", "@graph": graph}
    return env.get_template(p.template).render(
        page=p, canonical=s.url(p.path), jsonld=jsonld, css_ver=css_ver, **p.ctx)


def write(out: Path, url_path: str, text: str) -> None:
    target = out / url_path.lstrip("/")
    if url_path.endswith("/"):
        target = target / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def robots_txt(s: Settings) -> str:
    lines = []
    for bot in AI_CRAWLERS:
        lines += [f"User-agent: {bot}", "Allow: /", ""]
    lines += ["User-agent: *", "Allow: /", "", f"Sitemap: {s.url('/sitemap.xml')}", ""]
    return "\n".join(lines)


def sitemap_xml(s: Settings, pages: list[Page]) -> str:
    rows = [f"  <url><loc>{xml_escape(s.url(p.path))}</loc><lastmod>{p.lastmod.isoformat()}</lastmod></url>"
            for p in pages if p.in_sitemap]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")


def llms_txt(s: Settings, cats: list[Category]) -> str:
    out = [f"# {s.name}", "",
           "> Сервис измеряет, как часто ИИ-ассистенты с веб-поиском рекомендуют бренды селлеров "
           "маркетплейсов. Главная метрика — доля в ответах ИИ с учётом позиции упоминания. "
           "Рейтинги обновляются еженедельно; архив каждой недели доступен по постоянному адресу.", "",
           "## Рейтинги", ""]
    for c in cats:
        r = c.latest
        out.append(f"- [{c.name}]({s.url(c.path)}): неделя {r.week}, лидер — {r.brands[0].brand} "
                   f"({fmt.pct(r.brands[0].share)})")
    out += ["", "## Архив недель", ""]
    for c in cats:
        for r in reversed(c.weeks):
            out.append(f"- [{c.name}, {r.week}]({s.url(r.archive_path)})")
    out += ["", "## О методе", "",
            f"- [Методология]({s.url('/method/')}): типы запросов, модели, прогоны, формула доли, версии",
            f"- [Тарифы]({s.url('/pricing/')})", ""]
    return "\n".join(out).replace(fmt.NBSP, " ")


# ---------------------------------------------------------------- архив

def read_lock(lock: Path) -> list[str]:
    if not lock.exists():
        return []
    return [ln.strip() for ln in lock.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def check_and_update_lock(lock: Path, archive_paths: list[str], update: bool) -> None:
    known = read_lock(lock)
    missing = sorted(set(known) - set(archive_paths))
    if missing:
        raise BuildError("пропали архивные адреса (адрес недели вечный):\n  " + "\n  ".join(missing))
    if update:
        merged = sorted(set(known) | set(archive_paths))
        if merged != known:
            lock.write_text("# Архивные адреса рейтингов. Только дописывается, см. README.\n"
                            + "\n".join(merged) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- точка входа

def build(out: Path, settings: Settings, data_dir: Path | None = None,
          lock: Path | None = None, update_lock: bool = True) -> list[Page]:
    data_dir = data_dir or SITE_ROOT / "data"
    lock = lock or SITE_ROOT / "archive_urls.lock"
    cats = load_categories(data_dir)
    tariffs = load_tariffs(data_dir / "tariffs.json")
    formulas = load_formulas(data_dir / "formulas.json")
    for c in cats:
        for r in c.weeks:
            if str(r.method["formula_version"]) not in formulas:
                raise BuildError(f"{r.source}: формула {r.method['formula_version']} "
                                 "не описана в formulas.json")
    pages = collect_pages(settings, cats, tariffs, formulas)

    archive = [r.archive_path for c in cats for r in c.weeks]
    check_and_update_lock(lock, archive, update_lock)

    # Собираем во временную папку и подменяем целиком: полусобранный сайт не выкатывается.
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    css_ver = copy_static(tmp)
    env = make_env(settings)
    for p in pages:
        write(tmp, p.path, render_page(env, settings, p, css_ver))
    notfound = Page("/404.html", "404.html", "Страница не найдена", "Страница не найдена.",
                    dt.date.today(), in_sitemap=False, noindex=True)
    (tmp / "404.html").write_text(render_page(env, settings, notfound, css_ver), encoding="utf-8")
    (tmp / "robots.txt").write_text(robots_txt(settings), encoding="utf-8")
    (tmp / "sitemap.xml").write_text(sitemap_xml(settings, pages), encoding="utf-8")
    (tmp / "llms.txt").write_text(llms_txt(settings, cats), encoding="utf-8")

    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    return pages


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Сборка статического сайта GEO-аудита")
    ap.add_argument("--out", type=Path, default=SITE_ROOT / "dist")
    ap.add_argument("--strict", action="store_true",
                    help="боевая сборка: все настройки владельца обязательны")
    ap.add_argument("--no-update-lock", action="store_true",
                    help="не дописывать новые недели в archive_urls.lock")
    args = ap.parse_args(argv)
    try:
        s = load_settings(strict=args.strict)
        pages = build(args.out, s, update_lock=not args.no_update_lock)
    except (ConfigError, DataError, BuildError) as e:
        print(f"ОШИБКА СБОРКИ: {e}", file=sys.stderr)
        return 1
    print(f"Собрано страниц: {len(pages)} -> {args.out}")
    if not args.strict and not (s.telegram_bot and s.owner_name and s.owner_inn and s.domain):
        print("Внимание: часть настроек не задана (см. site/settings.env.example); "
              "для выкатки используйте --strict.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
