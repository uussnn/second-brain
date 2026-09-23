-- GEO-аудит dark factory — схема БД v0.1 (PostgreSQL 16)
-- Схемы:
--   core    — аналитика и замеры, БЕЗ персональных данных
--   line    — канбан-буферы, ОТК, изолятор брака, андон
--   billing — тарифы, подписки, платежи (без платёжных реквизитов)
--   pd      — единственное место с ПДн: Telegram ID и согласие
--   growth  — автономный выбор категорий, журнал решений, экономика категорий

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA core;
CREATE SCHEMA line;
CREATE SCHEMA billing;
CREATE SCHEMA pd;
CREATE SCHEMA growth;

-- =====================================================================
-- CORE: площадки, категории, бренды, товары
-- =====================================================================

CREATE TABLE core.marketplaces (
  id    smallserial PRIMARY KEY,
  code  text UNIQUE NOT NULL                -- 'wb', позже 'ozon'
);

CREATE TABLE core.categories (
  id             bigserial PRIMARY KEY,
  marketplace_id smallint NOT NULL REFERENCES core.marketplaces,
  parent_id      bigint REFERENCES core.categories,
  external_id    text,                      -- id категории на площадке
  name           text NOT NULL,
  is_tracked     boolean NOT NULL DEFAULT false,  -- входит в еженедельный замер
  UNIQUE (marketplace_id, external_id)
);

CREATE TABLE core.brands (
  id             bigserial PRIMARY KEY,
  canonical_name text NOT NULL UNIQUE
);

-- Сведение вариантов написания к бренду
CREATE TABLE core.brand_aliases (
  alias    text PRIMARY KEY,                -- нормализованный вариант (lower, без пунктуации)
  brand_id bigint NOT NULL REFERENCES core.brands,
  source   text NOT NULL DEFAULT 'auto'     -- auto | extractor | master
);

CREATE TABLE core.products (
  id             bigserial PRIMARY KEY,
  marketplace_id smallint NOT NULL REFERENCES core.marketplaces,
  external_sku   text NOT NULL,             -- nmId на WB
  brand_id       bigint REFERENCES core.brands,
  category_id    bigint REFERENCES core.categories,
  UNIQUE (marketplace_id, external_sku)
);

-- Снимки карточек: сырьё целиком, чтобы пересчитывать анализ
CREATE TABLE core.product_snapshots (
  id          bigserial PRIMARY KEY,
  product_id  bigint NOT NULL REFERENCES core.products,
  captured_at timestamptz NOT NULL DEFAULT now(),
  source      text NOT NULL,                -- public_parser | seller_api | analytics_service
  raw         jsonb NOT NULL,
  attributes  jsonb,                        -- нормализованные атрибуты
  fill_rate   numeric(5,4)                  -- заполненность против топа категории
);
CREATE INDEX ON core.product_snapshots (product_id, captured_at DESC);

-- =====================================================================
-- CORE: аккаунты и магазины (много магазинов на аккаунт)
-- =====================================================================

CREATE TABLE core.accounts (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind       text NOT NULL DEFAULT 'seller',   -- seller | agency (позже, white-label)
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.shops (
  id                bigserial PRIMARY KEY,
  account_id        uuid NOT NULL REFERENCES core.accounts,
  marketplace_id    smallint NOT NULL REFERENCES core.marketplaces,
  external_shop_id  text,
  seller_api_secret_ref text,   -- имя секрета в файле настроек; сам токен в БД не хранится
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (marketplace_id, external_shop_id)
);

CREATE TABLE core.shop_brands (
  shop_id  bigint REFERENCES core.shops ON DELETE CASCADE,
  brand_id bigint REFERENCES core.brands,
  PRIMARY KEY (shop_id, brand_id)
);

-- =====================================================================
-- CORE: модели, запросы, замеры
-- =====================================================================

CREATE TABLE core.ai_models (
  id              smallserial PRIMARY KEY,
  provider        text NOT NULL,            -- aitunnel, запасной поставщик
  model_code      text NOT NULL,            -- напр. линейка perplexity sonar
  has_web_search  boolean NOT NULL,
  is_active       boolean NOT NULL DEFAULT true,
  UNIQUE (provider, model_code)
);

CREATE TYPE core.query_type AS ENUM
  ('general', 'constrained', 'comparative', 'problem', 'brand');

-- shop_id NULL  -> набор категории (общий для всех замеров категории)
-- shop_id задан -> брендовые запросы конкретного клиента
-- После frozen_at набор не меняется: новая формулировка = новая версия
CREATE TABLE core.query_sets (
  id          bigserial PRIMARY KEY,
  category_id bigint NOT NULL REFERENCES core.categories,
  shop_id     bigint REFERENCES core.shops,
  version     int NOT NULL DEFAULT 1,
  frozen_at   timestamptz,
  UNIQUE NULLS NOT DISTINCT (category_id, shop_id, version)
);

CREATE TABLE core.queries (
  id           bigserial PRIMARY KEY,
  query_set_id bigint NOT NULL REFERENCES core.query_sets,
  qtype        core.query_type NOT NULL,
  text         text NOT NULL,
  in_mini_set  boolean NOT NULL DEFAULT false,  -- входит в 10 запросов мини-аудита
  UNIQUE (query_set_id, text)
);

CREATE TYPE core.measurement_kind AS ENUM
  ('category', 'mini_audit', 'full_audit', 'monitoring', 'calibration');

CREATE TABLE core.measurements (
  id             bigserial PRIMARY KEY,
  kind           core.measurement_kind NOT NULL,
  category_id    bigint NOT NULL REFERENCES core.categories,
  shop_id        bigint REFERENCES core.shops,       -- NULL для замера категории и калибровки
  runs_per_query smallint NOT NULL DEFAULT 3,
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz
);

-- Какие наборы запросов вошли в замер (категория + брендовые клиента)
CREATE TABLE core.measurement_query_sets (
  measurement_id bigint REFERENCES core.measurements,
  query_set_id   bigint REFERENCES core.query_sets,
  PRIMARY KEY (measurement_id, query_set_id)
);

-- Прогон = запрос × модель × номер повтора
CREATE TABLE core.runs (
  id             bigserial PRIMARY KEY,
  measurement_id bigint NOT NULL REFERENCES core.measurements,
  query_id       bigint NOT NULL REFERENCES core.queries,
  model_id       smallint NOT NULL REFERENCES core.ai_models,
  run_no         smallint NOT NULL CHECK (run_no BETWEEN 1 AND 5),
  status         text NOT NULL DEFAULT 'pending',    -- pending | ok | error
  cost_rub       numeric(10,4),
  requested_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (measurement_id, query_id, model_id, run_no)
);

CREATE TABLE core.responses (
  run_id        bigint PRIMARY KEY REFERENCES core.runs,
  raw_text      text NOT NULL,
  raw_json      jsonb,                      -- полный ответ API
  model_version text,                       -- версия, которую вернул провайдер (для дрейфа)
  received_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.response_sources (
  id       bigserial PRIMARY KEY,
  run_id   bigint NOT NULL REFERENCES core.responses(run_id),
  url      text NOT NULL,
  domain   text NOT NULL,
  position smallint
);
CREATE INDEX ON core.response_sources (domain);

CREATE TABLE core.mentions (
  id                bigserial PRIMARY KEY,
  run_id            bigint NOT NULL REFERENCES core.responses(run_id),
  extractor_version text NOT NULL,
  raw_name          text NOT NULL,          -- как написано в ответе
  brand_id          bigint REFERENCES core.brands,   -- NULL до сведения
  product_id        bigint REFERENCES core.products,
  position          smallint NOT NULL,
  tone              smallint CHECK (tone BETWEEN -1 AND 1),
  evidence          text,                   -- фрагмент ответа для сверки ОТК
  verified          boolean                 -- ОТК: упоминание найдено в сыром ответе
);
CREATE INDEX ON core.mentions (brand_id);

-- Три цифры для клиента; версия формулы позволяет пересчитывать историю
CREATE TABLE core.scores (
  measurement_id  bigint REFERENCES core.measurements,
  brand_id        bigint REFERENCES core.brands,
  formula_version text NOT NULL,
  share           numeric(6,5) NOT NULL,    -- доля в ответах с весом позиции
  gap_to_leader   numeric(6,5),
  source_gaps     jsonb,                    -- домены лидеров, где бренда нет
  computed_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (measurement_id, brand_id, formula_version)
);

CREATE TABLE core.reports (
  id             bigserial PRIMARY KEY,
  measurement_id bigint NOT NULL REFERENCES core.measurements,
  shop_id        bigint REFERENCES core.shops,
  kind           text NOT NULL,             -- mini | full | monitoring | rating
  file_ref       text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  sent_at        timestamptz
);

-- =====================================================================
-- LINE: канбан, изолятор брака, андон
-- =====================================================================

CREATE TYPE line.stream AS ENUM ('acquisition', 'service');

CREATE TABLE line.workshops (
  id     smallint PRIMARY KEY,              -- 1..6
  code   text UNIQUE NOT NULL,              -- leads, mini_audit, funnel, sales, monitoring, retention
  stream line.stream NOT NULL
);

-- Супермаркет-буфер перед цехом-потребителем
CREATE TABLE line.buffers (
  code        text PRIMARY KEY,             -- leads_store, mini_audit_store, onboarding ...
  workshop_id smallint NOT NULL REFERENCES line.workshops,
  card_limit  int NOT NULL CHECK (card_limit > 0),   -- N = D × L × (1+α) / C
  max_age     interval,                     -- старше — брак (лиды 14 дней, мини-аудиты 7)
  params      jsonb                         -- {D, L, alpha, C} для пересчёта N
);

CREATE TYPE line.item_status AS ENUM
  ('queued', 'in_progress', 'done', 'quarantined', 'expired', 'cancelled');

-- Карточка канбана. payload — только ссылки на сущности core, без ПДн
CREATE TABLE line.work_items (
  id            bigserial PRIMARY KEY,
  buffer_code   text NOT NULL REFERENCES line.buffers,
  status        line.item_status NOT NULL DEFAULT 'queued',
  payload       jsonb NOT NULL,
  priority      smallint NOT NULL DEFAULT 0,
  scheduled_for timestamptz NOT NULL DEFAULT now(),  -- хейдзунка: разнесение по дням
  enqueued_at   timestamptz NOT NULL DEFAULT now(),
  started_at    timestamptz,
  finished_at   timestamptz,
  attempts      smallint NOT NULL DEFAULT 0,
  locked_by     text,
  parent_id     bigint REFERENCES line.work_items
);
CREATE INDEX ON line.work_items (buffer_code, scheduled_for, priority DESC)
  WHERE status = 'queued';

-- Защита от ошибок: карточку нельзя положить в полный буфер
CREATE FUNCTION line.enforce_card_limit() RETURNS trigger AS $$
DECLARE
  wip int;
  lim int;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(NEW.buffer_code));
  SELECT card_limit INTO lim FROM line.buffers WHERE code = NEW.buffer_code;
  SELECT count(*) INTO wip FROM line.work_items
   WHERE buffer_code = NEW.buffer_code AND status IN ('queued', 'in_progress');
  IF wip >= lim THEN
    RAISE EXCEPTION 'kanban limit reached for %', NEW.buffer_code;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_card_limit BEFORE INSERT ON line.work_items
  FOR EACH ROW EXECUTE FUNCTION line.enforce_card_limit();

-- Воркер забирает карточку так:
--   UPDATE line.work_items SET status='in_progress', started_at=now(),
--          attempts=attempts+1, locked_by=$1
--   WHERE id = (SELECT id FROM line.work_items
--               WHERE buffer_code=$2 AND status='queued' AND scheduled_for<=now()
--               ORDER BY priority DESC, scheduled_for
--               FOR UPDATE SKIP LOCKED LIMIT 1)
--   RETURNING *;

-- Изолятор брака: останавливается деталь, а не линия
CREATE TABLE line.defects (
  id           bigserial PRIMARY KEY,
  work_item_id bigint NOT NULL REFERENCES line.work_items,
  check_code   text NOT NULL,   -- schema_invalid | mention_not_in_raw | expired | drift ...
  details      jsonb,
  decided_by   text,            -- auto | master_model
  decision     text,            -- retry | discard | escalate
  created_at   timestamptz NOT NULL DEFAULT now(),
  resolved_at  timestamptz
);

CREATE TABLE line.andon_events (
  id          bigserial PRIMARY KEY,
  level       text NOT NULL CHECK (level IN ('info', 'master', 'emergency')),
  code        text NOT NULL,    -- bot_blocked | legal_claim | platform_rules | model_drift | tax_limit
  details     jsonb,
  created_at  timestamptz NOT NULL DEFAULT now(),
  notified_at timestamptz,      -- когда ушёл сигнал в Telegram
  resolved_at timestamptz
);

-- Диспетчерская: WIP, выход, время прохождения (закон Литтла)
CREATE VIEW line.buffer_stats AS
SELECT b.code,
       b.card_limit,
       count(*) FILTER (WHERE w.status IN ('queued', 'in_progress'))            AS wip,
       count(*) FILTER (WHERE w.status = 'done'
                          AND w.finished_at > now() - interval '7 days') / 7.0  AS throughput_per_day,
       avg(w.finished_at - w.enqueued_at) FILTER (WHERE w.status = 'done'
                          AND w.finished_at > now() - interval '7 days')        AS lead_time,
       count(*) FILTER (WHERE w.status IN ('quarantined', 'expired')
                          AND w.enqueued_at > now() - interval '7 days')        AS defects_7d
FROM line.buffers b
LEFT JOIN line.work_items w ON w.buffer_code = b.code
GROUP BY b.code, b.card_limit;

-- =====================================================================
-- BILLING: реквизиты карт — только у платёжного сервиса
-- =====================================================================

CREATE TABLE billing.tariffs (
  code       text PRIMARY KEY,
  name       text NOT NULL,
  price_rub  numeric(10,2) NOT NULL,
  period     interval,                      -- NULL для разовых (полный аудит)
  sku_limit  int,
  is_active  boolean NOT NULL DEFAULT true
);

CREATE TABLE billing.subscriptions (
  id                   bigserial PRIMARY KEY,
  account_id           uuid NOT NULL REFERENCES core.accounts,
  tariff_code          text NOT NULL REFERENCES billing.tariffs,
  status               text NOT NULL,       -- active | past_due | cancelled
  current_period_start timestamptz NOT NULL,
  current_period_end   timestamptz NOT NULL,
  prepaid_until        timestamptz           -- годовая предоплата
);

CREATE TABLE billing.payments (
  id                  bigserial PRIMARY KEY,
  account_id          uuid NOT NULL REFERENCES core.accounts,
  purpose             text NOT NULL,        -- full_audit | subscription | implementation
  amount_rub          numeric(10,2) NOT NULL,
  provider            text NOT NULL,
  provider_payment_id text UNIQUE NOT NULL,
  receipt_id          text,                 -- чек «Мой налог»
  status              text NOT NULL,        -- pending | paid | refunded
  paid_at             timestamptz
);

CREATE TABLE billing.refunds (
  id          bigserial PRIMARY KEY,
  payment_id  bigint NOT NULL REFERENCES billing.payments,
  amount_rub  numeric(10,2) NOT NULL,
  reason_code text NOT NULL,
  automatic   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Для сигнала о лимите самозанятости (сам лимит — в настройках, не в SQL)
CREATE VIEW billing.revenue_by_year AS
SELECT date_trunc('year', p.paid_at)::date AS year,
       sum(p.amount_rub) - coalesce(sum(r.amount_rub), 0) AS net_revenue_rub
FROM billing.payments p
LEFT JOIN billing.refunds r ON r.payment_id = p.id
WHERE p.paid_at IS NOT NULL
GROUP BY 1;

-- Все расходы. Реклама и эксперименты — из фонда развития, не операционные
CREATE TABLE billing.expenses (
  id         bigserial PRIMARY KEY,
  fund       text NOT NULL CHECK (fund IN ('operations', 'development')),
  category   text NOT NULL,   -- api | server | payment_fee | ads | new_category | backup_provider ...
  amount_rub numeric(12,2) NOT NULL CHECK (amount_rub > 0),
  spent_at   timestamptz NOT NULL DEFAULT now(),
  ref        jsonb             -- ссылка на кампанию, эксперимент, счёт поставщика
);

-- Закрытие месяца: 60% от (выручка − возвраты − налог − операционные) в развитие
CREATE TABLE billing.period_closings (
  period       date PRIMARY KEY,          -- первое число месяца
  revenue_rub  numeric(12,2) NOT NULL,
  refunds_rub  numeric(12,2) NOT NULL,
  tax_rub      numeric(12,2) NOT NULL,    -- резерв налога самозанятого
  opex_rub     numeric(12,2) NOT NULL,
  net_rub      numeric(12,2) GENERATED ALWAYS AS
               (revenue_rub - refunds_rub - tax_rub - opex_rub) STORED,
  dev_share    numeric(3,2) NOT NULL DEFAULT 0.60,  -- фиксированное правило, не самообучается
  dev_rub      numeric(12,2) NOT NULL,    -- 0, если net_rub <= 0
  owner_rub    numeric(12,2) NOT NULL,
  closed_at    timestamptz NOT NULL DEFAULT now()
);

-- Баланс фонда развития: тратить можно только накопленное
CREATE VIEW billing.dev_fund_balance AS
SELECT coalesce((SELECT sum(dev_rub) FROM billing.period_closings), 0)
     - coalesce((SELECT sum(amount_rub) FROM billing.expenses WHERE fund = 'development'), 0)
       AS balance_rub;

-- =====================================================================
-- GROWTH: автономный выбор категорий
-- =====================================================================

-- Правила. self_tunable = false — самообучение не меняет
CREATE TABLE growth.rules (
  code         text PRIMARY KEY,
  value        jsonb NOT NULL,
  self_tunable boolean NOT NULL,
  note         text
);
INSERT INTO growth.rules VALUES
 ('dev_share',          '0.60', false, '60% чистого результата в фонд развития'),
 ('data_floor_share',   '0.15', false, 'минимум фонда развития на разведку категорий'),
 ('ramp_months',        '3',    false, 'разгон; после — окупилась или закрыта полностью'),
 ('reserve_active_ads', 'true', false, 'реклама окупаемых категорий резервируется до запуска новых'),
 ('restricted',         '["лекарства","БАДы","алкоголь","табак","18+"]', false,
                        'категории, куда система не заходит'),
 ('ramp_cost_estimate', 'null', true,  'оценка стоимости разгона, уточняется по факту'),
 ('owner_digest',       '"monthly"', false, 'сводка решений в Telegram без ответа');

CREATE TYPE growth.stage AS ENUM
  ('candidate', 'scouting', 'ramp_up', 'active', 'closed');

CREATE TABLE growth.category_lifecycle (
  category_id  bigint PRIMARY KEY REFERENCES core.categories,
  stage        growth.stage NOT NULL DEFAULT 'candidate',
  stage_since  timestamptz NOT NULL DEFAULT now(),
  ramp_ends_at timestamptz,          -- ramp_up + 3 месяца
  closed_at    timestamptz           -- сырые данные не удаляются
);

-- Журнал решений: прогноз при решении, факт при разборе
CREATE TABLE growth.decisions (
  id             bigserial PRIMARY KEY,
  kind           text NOT NULL,      -- open_category | close_category | enter_marketplace
  category_id    bigint REFERENCES core.categories,
  marketplace_id smallint REFERENCES core.marketplaces,
  made_at        timestamptz NOT NULL DEFAULT now(),
  model_version  text NOT NULL,      -- версия модели выбора
  rationale      jsonb NOT NULL,     -- основания: концентрация ответов ИИ, число селлеров...
  forecast       jsonb NOT NULL,     -- прогноз выручки, стоимости разгона, подписчиков
  review_due_at  timestamptz NOT NULL,
  actual         jsonb,
  reviewed_at    timestamptz,
  error          jsonb               -- прогноз − факт: материал для обучения
);

-- Привязка денег к категориям для расчёта окупаемости
ALTER TABLE billing.payments ADD COLUMN category_id bigint REFERENCES core.categories;
ALTER TABLE billing.expenses ADD COLUMN category_id bigint REFERENCES core.categories;

CREATE VIEW growth.category_economics AS
SELECT c.id AS category_id,
       m.month,
       coalesce(p.revenue, 0)                              AS revenue_rub,
       coalesce(e.spend, 0) + coalesce(r.api_cost, 0)      AS cost_rub,
       coalesce(p.revenue, 0) - coalesce(e.spend, 0) - coalesce(r.api_cost, 0) AS net_rub
FROM core.categories c
CROSS JOIN LATERAL (
  SELECT generate_series(date_trunc('month', now()) - interval '11 months',
                         date_trunc('month', now()), interval '1 month')::date AS month
) m
LEFT JOIN LATERAL (
  SELECT sum(amount_rub) AS revenue FROM billing.payments
  WHERE category_id = c.id AND status = 'paid'
    AND date_trunc('month', paid_at)::date = m.month
) p ON true
LEFT JOIN LATERAL (
  SELECT sum(amount_rub) AS spend FROM billing.expenses
  WHERE category_id = c.id AND date_trunc('month', spent_at)::date = m.month
) e ON true
LEFT JOIN LATERAL (
  SELECT sum(ru.cost_rub) AS api_cost
  FROM core.runs ru JOIN core.measurements ms ON ms.id = ru.measurement_id
  WHERE ms.category_id = c.id AND date_trunc('month', ru.requested_at)::date = m.month
) r ON true
WHERE EXISTS (SELECT 1 FROM growth.category_lifecycle l
              WHERE l.category_id = c.id AND l.stage <> 'candidate');

-- =====================================================================
-- PD: единственные персональные данные
-- =====================================================================

CREATE TABLE pd.telegram_links (
  account_id       uuid PRIMARY KEY REFERENCES core.accounts ON DELETE CASCADE,
  telegram_user_id bigint UNIQUE NOT NULL,
  consent_at       timestamptz NOT NULL,
  consent_version  text NOT NULL            -- версия политики ПДн
);

-- Доступ к pd — только у роли бота; воркеры цехов её не получают
REVOKE ALL ON SCHEMA pd FROM PUBLIC;
-- CREATE ROLE bot_role LOGIN PASSWORD '...';   -- пароль из файла настроек
-- GRANT USAGE ON SCHEMA pd TO bot_role;
-- GRANT SELECT, INSERT, DELETE ON pd.telegram_links TO bot_role;
