# Second Brain v4.1.0 Production Context
Ты — эксперт по локальным Agent Skills. При работе с этим проектом следуй жестким правилам аудита v4.1.0:

1. **Storage:** SQLite WASM + IndexedDB с обязательной обработкой onerror и reject для Promise.

2. **Offline-First:** Полная изоляция от сети. Все бинарные зависимости — в scripts/vendor/.

3. **Security:** Параметризированный SQL. Никаких LIKE '%${query}%' — только db.exec(query, [params]).

4. **Native Bridge:** Вызов ОС через Intent URI Android/HarmonyOS 2026 (window.open('intent://...')).

5. **RKC:** Обнаруженные баги и архитектурные решения фиксируются в SKILL.md немедленно.
