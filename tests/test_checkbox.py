"""Отметка пунктов: чекбокс, прозрачный запирающий слой и сохранение
отметки в хранилище."""

import asyncio

import flet as ft

import storage
from support import (
    FakeHaptic,
    FakePage,
    FakeStorage,
    category,
    item,
    make_app,
    make_app_with_items,
    measure,
    pick_up_item,
    select_item,
)
from ui import theme
from ui.app import ChecklistApp
from ui.controls import create_checkbox_blocker


# Отметка пунктов — задача 8 этапа 3.


def test_checkbox_tap_marks_item_and_saves_it():
    page, app, haptic, home, work, first, second = make_app_with_items()
    page.updates = 0

    asyncio.run(first.checkbox.on_change(None))

    # Отметка записана в БД, чекбокс и модель показывают одно и то же.
    assert app.storage.checked == [(first.item.id, True)]
    assert first.item.is_checked is True
    assert first.checkbox.value is True
    # Отмеченный пункт серый: и название, и сама отметка.
    assert first.title_text.style == theme.ITEM_CHECKED_TITLE_STYLE
    assert first.title_text.style.color == theme.ITEM_CHECKED_COLOR
    assert first.checkbox.active_color == theme.ITEM_CHECKED_COLOR
    # Тап по чекбоксу ничего не выделяет и не трогает соседний пункт.
    assert app._selected_item is None
    assert app._selected_view is None
    assert first.selected is False
    assert second.checkbox.value is False
    assert second.title_text.style == theme.ITEM_TITLE_STYLE
    assert page.updates == 1


def test_checkbox_tap_clears_mark():
    page, app, haptic, home, work, first, second = make_app_with_items()
    first.set_checked(True)

    asyncio.run(first.checkbox.on_change(None))

    assert app.storage.checked == [(first.item.id, False)]
    assert first.item.is_checked is False
    assert first.checkbox.value is False
    assert first.checkbox.active_color is None
    assert first.title_text.style == theme.ITEM_TITLE_STYLE


def test_checked_item_survives_a_restart():
    """Отметка сохраняется в БД и восстанавливается при повторном запуске."""
    page = FakePage()
    storage = FakeStorage()
    storage.categories = [category(1, "Дом")]
    storage.items = [item(1, 1, "Молоко", is_checked=True)]
    app = ChecklistApp(page, storage=storage, haptic=FakeHaptic())

    asyncio.run(app.mount())

    view = app.views[0].items[0]
    assert view.checkbox.value is True
    assert view.item.is_checked is True
    assert view.title_text.style == theme.ITEM_CHECKED_TITLE_STYLE


def test_checkbox_tap_is_ignored_while_a_category_is_selected():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)
    page.updates = 0

    asyncio.run(first.checkbox.on_change(None))

    # По спеке отметка меняется, только когда ничего не выделено.
    assert app.storage.checked == []
    assert first.item.is_checked is False
    assert first.checkbox.value is False
    assert first.title_text.style == theme.ITEM_TITLE_STYLE
    # Выделение категории тапом по чекбоксу не снимается.
    assert app._selected_view is home
    assert home.selected is True
    assert page.updates == 1


def test_checkbox_tap_is_ignored_while_an_item_is_selected():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, second)
    page.updates = 0

    asyncio.run(first.checkbox.on_change(None))

    assert app.storage.checked == []
    assert first.item.is_checked is False
    assert first.checkbox.value is False
    assert app._selected_item is second
    assert second.selected is True


def test_checkbox_tap_is_ignored_while_a_title_is_edited():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    report = work.append_item(item(1, work.category.id, "Отчёт"))
    app.storage.items = [report.item]
    app._begin_title_input(home)

    asyncio.run(report.checkbox.on_change(None))

    assert app.storage.checked == []
    assert report.item.is_checked is False
    assert report.checkbox.value is False


def test_checkbox_write_error_keeps_mark_and_reports():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app.storage.fail_check = True

    asyncio.run(first.checkbox.on_change(None))

    # Коммит до UI: при ошибке отметка и цвет остаются прежними.
    assert first.item.is_checked is False
    assert first.checkbox.value is False
    assert first.checkbox.active_color is None
    assert first.title_text.style == theme.ITEM_TITLE_STYLE
    assert page.messages == ["Не удалось сохранить отметку"]


def test_drag_proxy_shows_the_checked_look():
    """Поднятая копия строки повторяет отметку и серый цвет пункта."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    first.set_checked(True)
    measure(app)

    pick_up_item(first)

    proxy = app._item_drag.proxy
    checkbox, title = proxy.content.controls
    assert checkbox.value is True
    assert checkbox.active_color == theme.ITEM_CHECKED_COLOR
    assert title.style == theme.ITEM_CHECKED_TITLE_STYLE


def test_checkbox_blocker_is_a_transparent_hidden_layer():
    """Слой-перехватчик не рисуется и не попадает в TalkBack."""
    blocker = create_checkbox_blocker()

    assert blocker.visible is False
    assert (blocker.left, blocker.top, blocker.right, blocker.bottom) == (0, 0, 0, 0)
    assert blocker.content.bgcolor == ft.Colors.TRANSPARENT
    assert blocker.on_tap is not None
    assert blocker.exclude_from_semantics is True


def test_checkbox_is_blocked_while_a_category_is_selected():
    """Пока категория выделена, чекбоксы не реагируют на тап вовсе.

    Слой прозрачный, поэтому вид чекбокса не меняется (в отличие от
    `disabled`): он лишь не даёт клиенту нарисовать переключение.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    assert first.checkbox_blocker.visible is False

    app._select_category(home)

    assert first.checkbox_blocker.visible is True
    assert second.checkbox_blocker.visible is True

    app._deselect()

    assert first.checkbox_blocker.visible is False
    assert second.checkbox_blocker.visible is False


def test_checkbox_is_blocked_while_an_item_is_selected():
    page, app, haptic, home, work, first, second = make_app_with_items()

    select_item(app, second)

    assert first.checkbox_blocker.visible is True
    assert second.checkbox_blocker.visible is True

    app._deselect()

    assert first.checkbox_blocker.visible is False
    assert second.checkbox_blocker.visible is False


def test_checkbox_is_blocked_while_a_title_is_edited():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    report = work.append_item(item(1, work.category.id, "Отчёт"))
    app.storage.items = [report.item]

    app._begin_title_input(home)
    assert report.checkbox_blocker.visible is True

    asyncio.run(app._finish_title_input(home))
    assert report.checkbox_blocker.visible is False


def test_checkbox_blocker_does_not_hide_the_checkbox_itself():
    """Слой лежит поверх чекбокса и не заменяет его: вид и размер те же."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    stack = first.checkbox_area

    assert stack.controls[0] is first.checkbox
    assert stack.controls[1] is first.checkbox_blocker
    assert stack.clip_behavior == ft.ClipBehavior.HARD_EDGE
    # Размер стека задаёт чекбокс: слой позиционирован по его краям.
    assert first.checkbox_blocker.left == 0
    assert first.checkbox_blocker.top == 0
    assert first.checkbox_blocker.right == 0
    assert first.checkbox_blocker.bottom == 0
