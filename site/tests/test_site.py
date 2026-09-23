import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import html5lib
import pytest

from generator import fmt
from generator.build import read_lock
from generator.config import SITE_ROOT
from generator.data import PD_PATTERNS, load_categories

CATS = load_categories(SITE_ROOT / "data")
RATINGS = [r for c in CATS for r in c.weeks]


class Collector(HTMLParser):
    """Собирает то, что видит краулер без JavaScript."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.jsonld, self.scripts, self.refs, self.tags = [], [], [], [], []
        self._in = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag == "script":
            self._in = "ld" if a.get("type") == "application/ld+json" else "js"
            self.scripts.append(a)
        elif tag == "style":
            self._in = "style"
        for key in ("href", "src", "srcset", "action", "poster", "data"):
            if a.get(key):
                self.refs.append((tag, key, a[key], a.get("rel", "")))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._in = None

    def handle_data(self, data):
        if self._in == "ld":
            self.jsonld.append(data)
        elif self._in is None:
            self.text.append(data)

    @property
    def plain(self):
        return re.sub(r"[ \t\r\n]+", " ", " ".join(self.text))


def parse(path):
    c = Collector()
    c.feed(path.read_text(encoding="utf-8"))
    return c


def page(dist, url_path):
    return dist / url_path.lstrip("/") / "index.html"


# ------------------------------------------------------------ страницы собираются

EXPECTED = ["/", "/ratings/", "/method/", "/pricing/", "/offer/", "/privacy/", "/contacts/"]


@pytest.mark.parametrize("path", EXPECTED + [c.path for c in CATS] + [r.archive_path for r in RATINGS])
def test_page_exists(dist, path):
    assert page(dist, path).is_file(), path


def test_service_files(dist):
    for name in ("robots.txt", "sitemap.xml", "llms.txt", "404.html", "static/style.css", "static/icon.svg"):
        assert (dist / name).is_file(), name


def test_html_is_valid(html_files):
    parser = html5lib.HTMLParser(strict=True, namespaceHTMLElements=False)
    for f in html_files:
        text = f.read_text(encoding="utf-8")
        assert text.startswith("<!DOCTYPE html>"), f
        parser.parse(text)  # strict: исключение при любой ошибке разбора
        assert not parser.errors, (f, parser.errors)


def test_page_basics(html_files, settings):
    for f in html_files:
        c = parse(f)
        tags = c.tags
        assert ("html", {"lang": "ru"}) in tags, f
        assert sum(1 for t, _ in tags if t == "h1") == 1, f"{f}: ровно один h1"
        canon = [a["href"] for t, a in tags if t == "link" and a.get("rel") == "canonical"]
        assert len(canon) == 1 and canon[0].startswith(settings.base_url + "/"), f
        titles = [t for t, _ in tags if t == "title"]
        assert len(titles) == 1, f


def test_canonical_matches_location(dist, settings):
    for f in dist.rglob("index.html"):
        c = parse(f)
        canon = next(a["href"] for t, a in c.tags if t == "link" and a.get("rel") == "canonical")
        rel = "/" + str(f.parent.relative_to(dist)).replace("\\", "/") + "/"
        assert canon == settings.url(rel.replace("/./", "/")), f


# ------------------------------------------------------------ JSON-LD

def ld_types(obj):
    graph = obj.get("@graph", [obj])
    return {n["@type"] for n in graph}


def test_jsonld_parses_everywhere(html_files):
    for f in html_files:
        c = parse(f)
        assert len(c.jsonld) == 1, f
        data = json.loads(c.jsonld[0])
        assert data["@context"] == "https://schema.org"
        assert {"Organization", "WebSite"} <= ld_types(data), f


def test_jsonld_rating(dist):
    for r in RATINGS:
        data = json.loads(parse(page(dist, r.archive_path)).jsonld[0])
        nodes = {n["@type"]: n for n in data["@graph"]}
        ds = nodes["Dataset"]
        assert ds["dateModified"] == r.measured_at.isoformat()
        assert ds["variableMeasured"]
        items = nodes["ItemList"]["itemListElement"]
        assert [i["name"] for i in items] == [b.brand for b in r.brands]


def test_jsonld_faq(dist):
    data = json.loads(parse(page(dist, "/method/")).jsonld[0])
    faq = next(n for n in data["@graph"] if n["@type"] == "FAQPage")
    assert len(faq["mainEntity"]) >= 5
    text = parse(page(dist, "/method/")).plain
    for q in faq["mainEntity"]:
        assert q["name"] in text  # FAQ в разметке совпадает с видимым текстом


# ------------------------------------------------------------ контент без JS

def test_no_javascript(html_files):
    for f in html_files:
        c = parse(f)
        assert all(s.get("type") == "application/ld+json" for s in c.scripts), f
        assert not any(k.startswith("on") for _, a in c.tags for k in a), f"{f}: обработчик on*"


@pytest.mark.parametrize("r", RATINGS, ids=lambda r: r.archive_path)
def test_rating_text_in_raw_html(dist, r):
    paths = [r.archive_path] + ([r.category_path] if r is next(c for c in CATS if c.slug == r.slug).latest else [])
    for p in paths:
        c = parse(page(dist, p))
        text = c.plain
        assert f"{r.name} — неделя {r.week}" in text
        rows = re.findall(r"<tr>(.*?)</tr>", page(dist, p).read_text(encoding="utf-8"), re.S)
        body = [row for row in rows if "<th scope=\"row\">" in row]
        assert len(body) == len(r.brands)
        for b, row in zip(r.brands, body):
            assert f">{b.rank}<" in row
            assert f">{b.brand}<" in row
            assert f">{fmt.pct(b.share)}<" in row
            assert f">{fmt.pp(b.change)}<" in row
        assert fmt.date_ru(r.measured_at) in text
        assert 'href="/method/"' in page(dist, p).read_text(encoding="utf-8")


def test_rating_answer_first(dist):
    """h1 → вывод → таблица → дата замера и методология."""
    html = page(dist, CATS[0].path).read_text(encoding="utf-8")
    order = [html.index("<h1>"), html.index('class="lead"'), html.index("<table"), html.index("<time")]
    assert order == sorted(order)


# ------------------------------------------------------------ внешние ресурсы

def test_no_external_resources(html_files, settings):
    allowed_links = {"t.me"}  # кнопка в Telegram-бота — обычная ссылка, не ресурс
    own = urlparse(settings.base_url).netloc
    for f in html_files:
        for tag, key, value, rel in parse(f).refs:
            u = urlparse(value)
            if not u.netloc or u.netloc == own:
                continue
            assert tag == "a" and u.netloc in allowed_links, f"{f}: внешняя ссылка {value}"


def test_css_has_no_external(dist):
    css = (dist / "static/style.css").read_text(encoding="utf-8")
    assert "@import" not in css
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", css)


# ------------------------------------------------------------ персональные данные

def test_no_personal_data(html_files, dist, settings):
    contacts = page(dist, "/contacts/")
    for f in html_files + [dist / "llms.txt", dist / "sitemap.xml"]:
        text = parse(f).plain if f.suffix == ".html" else f.read_text(encoding="utf-8")
        if f == contacts:
            # здесь ФИО и ИНН самозанятого — по закону, из настроек
            text = text.replace(settings.owner_name, "").replace(settings.owner_inn, "")
        for rx in PD_PATTERNS:
            assert not rx.search(text), f"{f}: {rx.search(text).group(0)!r}"


def test_contacts_from_settings(dist, settings):
    text = parse(page(dist, "/contacts/")).plain
    assert settings.owner_name in text and settings.owner_inn in text


def test_owner_data_not_in_repo(settings):
    for f in list((SITE_ROOT / "generator").rglob("*.py")) + list((SITE_ROOT / "templates").rglob("*")):
        text = f.read_text(encoding="utf-8")
        assert settings.owner_name not in text and settings.owner_inn not in text


# ------------------------------------------------------------ архив

def test_archive_urls_unchanged(dist):
    """Ни один адрес из прошлых сборок не пропал."""
    for p in read_lock(SITE_ROOT / "archive_urls.lock"):
        assert page(dist, p).is_file(), f"архивный адрес пропал: {p}"


def test_archive_lock_is_up_to_date():
    """Новая неделя должна попасть в archive_urls.lock (make build дописывает его)."""
    assert {r.archive_path for r in RATINGS} <= set(read_lock(SITE_ROOT / "archive_urls.lock"))


# ------------------------------------------------------------ GEO/SEO файлы

def test_robots(dist, settings):
    text = (dist / "robots.txt").read_text()
    for bot in ("YandexBot", "Googlebot", "PerplexityBot", "OAI-SearchBot", "GPTBot", "ClaudeBot"):
        assert f"User-agent: {bot}\nAllow: /" in text
    assert "Disallow: /\n" not in text
    assert f"Sitemap: {settings.url('/sitemap.xml')}" in text


def test_sitemap(dist, settings):
    import xml.etree.ElementTree as ET
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.parse(dist / "sitemap.xml").getroot()
    urls = {u.find("s:loc", ns).text: u.find("s:lastmod", ns).text for u in root.findall("s:url", ns)}
    for r in RATINGS:
        assert urls[settings.url(r.archive_path)] == r.measured_at.isoformat()
    for p in ("/", "/ratings/", "/method/", "/pricing/", "/contacts/"):
        assert settings.url(p) in urls
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in urls.values())


def test_llms_txt(dist, settings):
    text = (dist / "llms.txt").read_text()
    assert text.startswith("# ")
    for c in CATS:
        assert settings.url(c.path) in text


def test_drafts_marked(dist):
    for p in ("/offer/", "/privacy/"):
        html = page(dist, p).read_text(encoding="utf-8")
        assert "ЧЕРНОВИК — заменяется документом цифрового юриста" in html
        assert '<meta name="robots" content="noindex">' in html


def test_pricing_from_data(dist):
    tariffs = json.loads((SITE_ROOT / "data/tariffs.json").read_text())
    text = parse(page(dist, "/pricing/")).plain
    for t in tariffs:
        assert (t["name"] in text) == t["is_active"], t["code"]


def test_method_shows_position_weights(dist):
    formulas = json.loads((SITE_ROOT / "data/formulas.json").read_text())
    html = page(dist, "/method/").read_text(encoding="utf-8")
    text = parse(page(dist, "/method/")).plain
    faq = json.loads(parse(page(dist, "/method/")).jsonld[0])
    answers = " ".join(n["acceptedAnswer"]["text"] for node in faq["@graph"] if node["@type"] == "FAQPage"
                       for n in node["mainEntity"])
    for version, f in formulas.items():
        assert f"Формула {version}" in text
        for w in f["position_weights"] + [f["tail_weight"]]:
            assert f">{fmt.num(w)}<" in html
        assert f"Веса в формуле {version}: 1-я позиция — 1, 2-я позиция — 0,7" in answers
