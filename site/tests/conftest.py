import sys
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SITE))

from generator.build import build  # noqa: E402
from generator.config import load_settings  # noqa: E402

# Вымышленные настройки владельца: только для тестов.
TEST_ENV = {
    "SITE_DOMAIN": "geo.example.test",
    "SITE_NAME": "GEO-аудит",
    "TELEGRAM_BOT": "example_geo_bot",
    "OWNER_NAME": "Тестов Тест Тестович",
    "OWNER_INN": "000000000000",
}


@pytest.fixture(scope="session")
def settings():
    return load_settings(TEST_ENV, strict=True)


@pytest.fixture(scope="session")
def built(tmp_path_factory, settings):
    """Сборка из site/data во временную папку. archive_urls.lock не меняется."""
    out = tmp_path_factory.mktemp("build") / "dist"
    pages = build(out, settings, update_lock=False)
    return out, pages


@pytest.fixture(scope="session")
def dist(built):
    return built[0]


@pytest.fixture(scope="session")
def html_files(dist):
    return sorted(dist.rglob("*.html"))
