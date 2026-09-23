# Сайт GEO-аудита: make build | make test | make serve
PYTHON ?= python3.12
VENV   := .venv
PY     := $(VENV)/bin/python
PORT   ?= 8000

# Настройки владельца (не в git). Без файла собирается локальная версия с заглушками.
-include site/settings.env
export SITE_DOMAIN SITE_NAME TELEGRAM_BOT OWNER_NAME OWNER_INN

.PHONY: build build-prod test serve up clean

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
