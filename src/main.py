"""Точка входа приложения My checklist."""

from __future__ import annotations

import asyncio
import logging

import flet as ft

from storage import StorageError, open_storage
from ui.app import ChecklistApp
from ui.compat import patch_long_press_move_event

logger = logging.getLogger(__name__)

# Обход ошибки flet 1.1.2 в событии движения после долгого нажатия: без него
# перетаскивание пункта одним жестом не работает (см. ui/compat.py).
patch_long_press_move_event()

# Автообновление flet после каждого события выключено: приложение показывает
# изменения само (`page.update()` в каждом обработчике). Автообновление патчит
# **всю** страницу, а на длинном списке один такой патч стоит на телефоне
# десятки миллисекунд — и приходит после каждого события: прокрутки,
# `size_change`, касания. Из-за него перетаскивание не успевало за пальцем
# (см. docs/Project.md, «Патч всей страницы»).
ft.context.disable_auto_update()


async def main(page: ft.Page):
    page.title = "My checklist"
    # Светлая тема зафиксирована: иконки кнопок чёрные (см. docs/Design.md).
    page.theme_mode = ft.ThemeMode.LIGHT

    try:
        storage = await asyncio.to_thread(open_storage)
    except (StorageError, OSError) as error:
        logger.exception("Не удалось открыть БД")
        page.add(ft.Text(f"Не удалось открыть данные приложения: {error}"))
        return

    app = ChecklistApp(page, storage)
    await app.mount()


if __name__ == "__main__":
    ft.run(main)
