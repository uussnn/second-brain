"""Сборка должна падать на плохих данных — сайт выкатывается без людей."""
import json
import re
import shutil

import pytest

from generator.build import BuildError, build, rating_summary
from generator.config import SITE_ROOT, ConfigError, load_settings
from generator.data import DataError, load_categories
from generator import fmt


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(SITE_ROOT / "data", d)
    return d


def rating_file(data, week="2026-W39"):
    return data / "ratings/wb/palatki" / f"{week}.json"


def edit(path, fn):
    doc = json.loads(path.read_text(encoding="utf-8"))
    fn(doc)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def run(tmp_path, data, settings, lock=None):
    lock = lock or tmp_path / "lock"
    return build(tmp_path / "dist", settings, data_dir=data, lock=lock)


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["brands"][0].update(brand="ИП Иванов"), "персональные данные"),
    (lambda d: d["brands"][0].update(brand="Бренд 7701234567"), "персональные данные"),
    (lambda d: d["brands"][0].update(share=1.5), "share"),
    (lambda d: d["brands"][1].update(rank=5), "rank"),
    (lambda d: d["brands"][1].update(share=0.99), "убыванию"),
    (lambda d: d.update(measured_at="2026-10-15"), "вне указанной недели"),
    (lambda d: d.pop("method"), "method"),
    (lambda d: d["category"].update(slug="other"), "slug"),
])
def test_bad_data_fails(tmp_path, data, settings, mutate, message):
    edit(rating_file(data), mutate)
    with pytest.raises(DataError, match=message):
        run(tmp_path, data, settings)


def test_bad_week_name_fails(tmp_path, data, settings):
    rating_file(data).rename(rating_file(data).with_name("2026-39.json"))
    with pytest.raises(DataError):
        run(tmp_path, data, settings)


def test_removed_week_fails(tmp_path, data, settings):
    lock = tmp_path / "lock"
    run(tmp_path, data, settings, lock)
    rating_file(data, "2026-W37").unlink()
    with pytest.raises(BuildError, match="2026-W37"):
        run(tmp_path, data, settings, lock)


def test_new_week_appended_to_lock(tmp_path, data, settings):
    lock = tmp_path / "lock"
    run(tmp_path, data, settings, lock)
    src = rating_file(data)
    new = rating_file(data, "2026-W40")
    edit(src, lambda d: None)
    doc = json.loads(src.read_text(encoding="utf-8"))
    doc.update(week="2026-W40", measured_at="2026-09-28")
    new.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    run(tmp_path, data, settings, lock)
    assert "/ratings/wb/palatki/2026-W40/" in lock.read_text()
    assert (tmp_path / "dist/ratings/wb/palatki/2026-W40/index.html").is_file()


def test_failed_build_keeps_previous_dist(tmp_path, data, settings):
    run(tmp_path, data, settings)
    edit(rating_file(data), lambda d: d["brands"][0].update(share=-1))
    with pytest.raises(DataError):
        run(tmp_path, data, settings)
    assert (tmp_path / "dist/index.html").is_file()


def test_strict_settings():
    with pytest.raises(ConfigError, match="OWNER_INN"):
        load_settings({"SITE_DOMAIN": "a.test", "TELEGRAM_BOT": "some_bot", "OWNER_NAME": "X"}, strict=True)
    with pytest.raises(ConfigError):
        load_settings({"OWNER_INN": "123"})
    s = load_settings({})
    assert s.name == "GEO-аудит" and s.bot_url is None


def test_formatting():
    assert fmt.pct(0.31) == "31,0 %"
    assert fmt.pp(0.02) == "+2,0 п.п."
    assert fmt.pp(-0.015) == "−1,5 п.п."
    assert fmt.pp(0.0) == "0,0 п.п."
    assert fmt.pp(None) == "новый"
    assert fmt.plural(3, "прогон", "прогона", "прогонов") == "3 прогона"
    assert fmt.plural(11, "прогон", "прогона", "прогонов") == "11 прогонов"


def test_summary_is_short_and_from_data():
    for c in load_categories(SITE_ROOT / "data"):
        for r in c.weeks:
            s = rating_summary(r)
            sentences = re.split(r"(?<=\.)\s+(?=[А-ЯЁ])", s)
            assert 2 <= len(sentences) <= 3, s
            assert r.brands[0].brand in s


def test_formula_weights():
    from generator.data import load_formulas
    f = load_formulas(SITE_ROOT / "data/formulas.json")["1.0"]
    assert [f.weight(i) for i in range(1, 7)] == [1.0, 0.7, 0.5, 0.5, 0.5, 0.5]
    assert fmt.num(1.0) == "1" and fmt.num(0.7) == "0,7"


@pytest.mark.parametrize("formulas, message", [
    ({"1.0": {"position_weights": [0.9, 0.7], "tail_weight": 0.5}}, "первой позиции"),
    ({"1.0": {"position_weights": [1, 0.5, 0.7], "tail_weight": 0.5}}, "не должны расти"),
    ({"1.0": {"position_weights": [1, 0.7, 0.5], "tail_weight": 0.6}}, "tail_weight"),
])
def test_bad_formula_fails(tmp_path, data, settings, formulas, message):
    (data / "formulas.json").write_text(json.dumps(formulas), encoding="utf-8")
    with pytest.raises(DataError, match=message):
        run(tmp_path, data, settings)


def test_undescribed_formula_version_fails(tmp_path, data, settings):
    edit(rating_file(data), lambda d: d["method"].update(formula_version="2.0"))
    with pytest.raises(BuildError, match="2.0"):
        run(tmp_path, data, settings)


def test_inactive_tariff_hidden(tmp_path, data, settings):
    rows = json.loads((data / "tariffs.json").read_text(encoding="utf-8"))
    rows.append({"code": "legacy", "name": "Архивный тариф", "price_rub": 990, "period": "P1M",
                 "sku_limit": 10, "is_active": False})
    (data / "tariffs.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    run(tmp_path, data, settings)
    html = (tmp_path / "dist/pricing/index.html").read_text(encoding="utf-8")
    assert "Архивный тариф" not in html and "Полный аудит" in html
