"""Обход известных ошибок flet 1.1.2, без которых не работает перетаскивание.

Обход применяется один раз из точки входа (src/main.py) и меняет поведение flet
глобально; при обновлении flet его стоит проверить и убрать
(docs/KnownIssues.md).
"""

from __future__ import annotations

import flet as ft

_applied = False


def patch_long_press_move_event() -> None:
    """Обход ошибки flet 1.1.2 в событии движения после долгого нажатия.

    Клиент присылает координаты в полях ``l``, ``g``, ``ofo``, ``lofo``, а класс
    `LongPressMoveUpdateEvent` объявляет ``offset_from_origin`` с
    ``data_field="of"`` (опечатка в библиотеке). Из-за неё разбор события падает
    с ``TypeError: missing 1 required keyword-only argument:
    'offset_from_origin'`` — проверено на устройстве. Без этого события нельзя
    вести перетаскивание пункта одним жестом: `on_long_press_start` даёт только
    точку нажатия, а движение пальца — лишь оно.

    Патч подставляет нулевое смещение, если его не передали: обработчику нужны
    только ``local_position`` и ``global_position``, а остальные поля события
    заполняются клиентом как обычно. Ошибка исправлена в flet после 1.1.2 —
    тогда патч можно убрать.

    Повторный вызов ничего не делает: иначе обёртки складывались бы друг на
    друга (это же нужно тестам, которые создают приложения несколько раз).
    """
    global _applied
    if _applied:
        return
    _applied = True
    original_init = ft.LongPressMoveUpdateEvent.__init__

    def patched_init(self, *args, **kwargs):
        kwargs.setdefault("offset_from_origin", ft.Offset(0, 0))
        original_init(self, *args, **kwargs)

    ft.LongPressMoveUpdateEvent.__init__ = patched_init
