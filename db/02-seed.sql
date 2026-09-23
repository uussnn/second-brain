-- Справочники, без которых линия не запускается. Выполняется один раз при создании базы.

INSERT INTO core.marketplaces (code) VALUES ('wb');

-- Шесть цехов (раздел 5 брифа). Воронку (3) обслуживает Telegram-бот.
INSERT INTO line.workshops (id, code, stream) VALUES
  (1, 'leads',      'acquisition'),
  (2, 'mini_audit', 'acquisition'),
  (3, 'funnel',     'acquisition'),
  (4, 'sales',      'acquisition'),
  (5, 'monitoring', 'service'),
  (6, 'retention',  'service');

-- Буферы-супермаркеты перед цехом-потребителем (раздел 6 брифа).
-- card_limit — стартовое значение: D и L неизвестны до первых недель работы,
-- дальше лимит пересчитывается по N = D × L × (1 + α) / C (самообучение, раздел 8).
INSERT INTO line.buffers (code, workshop_id, card_limit, max_age, params) VALUES
  ('leads_store',      2, 200, interval '14 days',
   '{"D": null, "L": null, "alpha": 0.15, "C": null, "note": "замер старше 2 недель — брак"}'),
  ('mini_audit_store', 3, 100, interval '7 days',
   '{"D": null, "L": null, "alpha": 0.15, "C": null, "note": "мини-аудит старше недели не отправляется"}'),
  ('onboarding',       5,  20, interval '1 day',
   '{"D": null, "L": null, "alpha": 0.15, "C": null, "note": "первый замер в течение суток"}');
