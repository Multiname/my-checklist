"""Точка входа приложения: `main(page)` собирает экран и открывает данные."""

import asyncio
from pathlib import Path

import flet as ft

import main
import storage
from support import FakePage, FakeStorage
from ui.app import ChecklistApp


def test_app_module_is_importable():
    assert callable(main.main)


def test_main_adds_the_screen_and_opens_storage(monkeypatch):
    page = FakePage()
    database = FakeStorage()
    monkeypatch.setattr(main, "open_storage", lambda: database)

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
    # Исправная БД: никаких сообщений о потере данных.
    assert page.messages == []
    # Пустая БД: в стеке список и button_area, где видна только одна кнопка.
    stack = page.controls[0].content
    assert isinstance(stack, ft.Stack)
    buttons = stack.controls[-1].content.controls
    assert [button.visible for button in buttons] == [True, False, False]


def test_main_reports_storage_error_instead_of_the_screen(monkeypatch):
    """БД не открылась — вместо экрана текст с причиной, приложение не падает."""

    def fail():
        raise storage.StorageError("нет доступа")

    page = FakePage()
    monkeypatch.setattr(main, "open_storage", fail)

    asyncio.run(main.main(page))

    assert len(page.controls) == 1
    assert page.controls[0].value == (
        "Не удалось открыть данные приложения: нет доступа"
    )
    # Список не построен: данных нет, показывать нечего.
    assert page.services == []


def test_mount_reports_the_copy_of_a_corrupt_database():
    """Повреждённая БД заменена пустой: пользователь узнаёт, где копия."""
    page = FakePage()
    database = FakeStorage()
    database.recovered_backup = Path("app.db.corrupt-20260101-120000")
    app = ChecklistApp(page, storage=database)

    asyncio.run(app.mount())

    assert page.messages == [
        "Файл данных был повреждён: создана пустая база. Прежние данные "
        "потеряны (копия: app.db.corrupt-20260101-120000)."
    ]
    assert app.views == []
