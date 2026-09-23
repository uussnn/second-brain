-- Роли приложений. Пароли задаёт db/03-roles.sh из переменных окружения.
--   bot_role    — Telegram-бот: единственный, кто видит схему pd (Telegram ID и согласия)
--   worker_role — воркеры цехов: core, line, billing, growth; без доступа к pd
-- Выполняется владельцем схем (postgres). Повторный запуск безопасен.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bot_role') THEN
    CREATE ROLE bot_role LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'worker_role') THEN
    CREATE ROLE worker_role LOGIN;
  END IF;
END $$;

-- Общий доступ к рабочим схемам
GRANT USAGE ON SCHEMA core, line, billing, growth TO bot_role, worker_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, line, billing, growth
  TO bot_role, worker_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core, line, billing, growth
  TO bot_role, worker_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, line, billing, growth
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bot_role, worker_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA core, line, billing, growth
  GRANT USAGE, SELECT ON SEQUENCES TO bot_role, worker_role;

-- Правила самообучения с self_tunable = false не меняет никто из приложений
REVOKE INSERT, UPDATE, DELETE ON growth.rules FROM bot_role, worker_role;

-- Персональные данные — только бот (см. конец schema_v0_1.sql)
REVOKE ALL ON SCHEMA pd FROM worker_role;
GRANT USAGE ON SCHEMA pd TO bot_role;
GRANT SELECT, INSERT, DELETE ON pd.telegram_links TO bot_role;
