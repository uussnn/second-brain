# Сайт GEO-аудита

Статический сайт: Python 3.12 + Jinja2 → готовый HTML в `site/dist/`, раздаёт Caddy.
Весь контент есть в HTML (без JavaScript), внешних ресурсов нет. Задание — `TASK_site.md`.

## Команды

```sh
make build       # собрать site/dist из site/data (+ дописать новые недели в archive_urls.lock)
make test        # pytest: валидность, JSON-LD, текст без JS, внешние ресурсы, ПДн, архив
make serve       # собрать и открыть http://localhost:8000/
make build-prod  # боевая сборка: все настройки обязательны, затем тесты
make up          # поднять Caddy (docker-compose.site.yml), HTTPS для SITE_DOMAIN
```

Любая ошибка в данных, шаблонах или тестах даёт ненулевой код. Сборка идёт во временную
папку, поэтому при ошибке прежний `dist/` не трогается.

## Настройки

`site/settings.env` (не в git; образец — `site/settings.env.example`):
`SITE_DOMAIN`, `SITE_NAME`, `TELEGRAM_BOT`, `OWNER_NAME`, `OWNER_INN`.
ФИО и ИНН попадают только на `/contacts/`, в коде их нет. Без настроек сайт
собирается с заглушками, а `make build-prod` (`--strict`) в таком случае падает.

## Как добавить неделю рейтинга

1. Положите файл `site/data/ratings/<площадка>/<категория>/<ГГГГ-Wнн>.json`:
   ```json
   {
     "category": {"marketplace": "wb", "slug": "palatki", "name": "Туристические палатки"},
     "week": "2026-W40",
     "measured_at": "2026-09-28",
     "method": {"queries": 40, "models": ["sonar"], "runs": 3, "formula_version": "1.0"},
     "brands": [{"rank": 1, "brand": "…", "share": 0.31, "change": 0.02}]
   }
   ```
   `share` — доля от 0 до 1, `change` — разница с прошлой неделей (тоже доля) или `null` для
   бренда, которого раньше не было. Бренды идут по убыванию `share`, `rank` — подряд с 1.
   `measured_at` должна попадать в указанную ISO-неделю. Новая категория — новая папка
   (slug латиницей).
2. `make build` — появятся текущая страница категории и вечная страница недели,
   а её адрес допишется в `site/archive_urls.lock`.
3. `make test` и закоммитьте JSON вместе с `archive_urls.lock`.

Архивные адреса вечные: если адрес из `archive_urls.lock` не появился в сборке (например,
удалили JSON недели), сборка падает. Старые JSON не редактируются.

Генератор отклоняет бренды, похожие на персональные данные («ИП Фамилия», ИНН, телефон,
e-mail). Тестовые данные в репозитории — только вымышленные бренды «Тестбренд …».

## Как будет подключена база

Шаблоны получают объекты из `generator/data.py` (`Rating`, `Category`, `Tariff`), и
формат JSON повторяет будущую выгрузку из `schema_v0_1.sql`:

| JSON | Источник в PostgreSQL |
|---|---|
| `category.*` | `core.categories` + `core.marketplaces.code` (slug — новое поле или транслитерация `name`) |
| `week`, `measured_at` | `core.measurements` (`kind = 'category'`, `finished_at`) |
| `method` | число `core.queries` в наборе, `runs_per_query`, `core.ai_models.model_code`, `core.scores.formula_version` |
| `brands[].brand`, `share` | `core.brands.canonical_name`, `core.scores.share` |
| `brands[].change` | `share` минус `share` того же бренда в прошлом замере категории |
| `tariffs.json` | строки `billing.tariffs`; `period` выгружается с `SET intervalstyle = 'iso_8601'` |

Есть два пути, шаблоны не меняются ни в одном:
- **Выгрузка в файлы.** После еженедельного замера воркер пишет JSON в `site/data/`
  и запускает `make build-prod`. Это самый простой вариант, и проверки остаются прежними.
- **Прямое чтение.** `load_categories` и `load_tariffs` заменяются запросами к базе
  (роль только с `SELECT` на `core` и `billing`; к схеме `pd` доступа нет).
