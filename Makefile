# Сайт GEO-аудита: make build | make test | make serve
PYTHON ?= python3.12
VENV   := .venv
PY     := $(VENV)/bin/python
PORT   ?= 8000

# Настройки владельца (не в git). Без файла собирается локальная версия с заглушками.
-include site/settings.env
export SITE_DOMAIN SITE_NAME TELEGRAM_BOT OWNER_NAME OWNER_INN

.PHONY: build build-prod test serve up clean test-factory

$(PY): site/requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q -r site/requirements.txt
	@touch $(PY)

build: $(PY)
	cd site && ../$(PY) -m generator

# Боевая сборка: все настройки обязательны, затем тесты. Любая ошибка — ненулевой код.
build-prod: $(PY)
	cd site && ../$(PY) -m generator --strict
	$(PY) -m pytest site/tests -q

test: $(PY)
	$(PY) -m pytest site/tests -q

# Локальный просмотр: адреса и канонические ссылки — на localhost.
serve: $(PY)
	cd site && SITE_DOMAIN= ../$(PY) -m generator
	@echo "http://localhost:$(PORT)/"
	$(PY) -m http.server $(PORT) --bind 127.0.0.1 --directory site/dist

up:
	docker compose -f docker-compose.site.yml up -d

clean:
	rm -rf site/dist site/dist.tmp

# Линия (база, бот, воркеры). Интеграционные тесты — на настоящем PostgreSQL 16:
#   TEST_DATABASE_URL=postgresql://postgres:<пароль>@localhost:55432/postgres make test-factory
test-factory: $(PY)
	$(PY) -m pip install -q -r app/requirements-dev.txt
	@test -n "$(TEST_DATABASE_URL)" || (echo "задайте TEST_DATABASE_URL (см. app/README.md)"; exit 1)
	TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(PY) -m pytest app/tests -q
