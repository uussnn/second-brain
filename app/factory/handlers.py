"""Обработчики буферов: код буфера -> функция(WorkItem) -> Result.

Пока цеха не реализованы, здесь заглушки. Заглушка не выбрасывает карточки:
она отправляет их в изолятор с check_code='not_implemented', откуда их можно
вернуть в очередь, когда появится настоящий обработчик.
Обработчик не пишет в базу сам — он возвращает Result с новыми карточками,
а kanban.complete() сохраняет их вместе с отметкой done в одной транзакции.
Проверка результата (ОТК) — через исключение kanban.Defect.
"""

from __future__ import annotations

from typing import Callable

from .kanban import Defect, Result, WorkItem

Handler = Callable[[WorkItem], Result]


def not_implemented(item: WorkItem) -> Result:
    raise Defect("not_implemented", {"buffer": item.buffer_code})


HANDLERS: dict[str, Handler] = {
    # склад лидов -> цех 2: мини-аудит из среза замера категории -> mini_audit_store
    "leads_store": not_implemented,
    # склад мини-аудитов -> цех 3 (бот): отправка мини-аудита в Telegram
    "mini_audit_store": not_implemented,
    # очередь онбординга -> цех 5: первый замер подписчика в течение суток
    "onboarding": not_implemented,
}


def handler_for(buffer_code: str) -> Handler:
    return HANDLERS.get(buffer_code, not_implemented)
