"""Точка входа приложения: `main(page)` собирает экран и открывает данные."""

import asyncio

import flet as ft

import main
from support import FakePage, FakeStorage


def test_app_module_is_importable():
    assert callable(main.main)


def test_main_adds_the_screen_and_opens_storage(monkeypatch):
    page = FakePage()
    storage = FakeStorage()
    monkeypatch.setattr(main, "open_storage", lambda: storage)

    asyncio.run(main.main(page))

    assert page.title == "My checklist"
    # Светлая тема зафиксирована: иконки кнопок чёрные.
    assert page.theme_mode == ft.ThemeMode.LIGHT
    # Экран — SafeArea со стеком (список категорий и button_area).
    assert len(page.controls) == 1
    assert isinstance(page.controls[0], ft.SafeArea)
    # Ввод названия и «назад» обслуживает сама страница.
    assert page.on_media_change is not None
    assert page.views[0].on_confirm_pop is not None
    # Виброотклик — сервис страницы.
    assert len(page.services) == 1
    # Пустая БД: в стеке список и button_area, где видна только одна кнопка.
    stack = page.controls[0].content
    assert isinstance(stack, ft.Stack)
    buttons = stack.controls[-1].content.controls
    assert [button.visible for button in buttons] == [True, False, False]
