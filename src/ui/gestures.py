"""Жесты пункта и категории.

Наборы обработчиков передаются видам одним объектом, а обёртки
приспосабливают методы приложения к тому, что ждёт flet: обработчику
нужен сам вид (пункт или категория), а не только событие."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from ui.views import CategoryView, ItemView


def no_op(event: ft.ControlEvent):
    """Заглушка обработчика: тап по кнопке даёт ripple, но ничего не делает."""


def item_event_handler(
    handler: Callable[[ItemView | CategoryView], object] | None,
    view: ItemView | CategoryView,
):
    """Обработчик жеста пункта или категории: передаёт приложению сам вид.

    Flet ждёт от асинхронного обработчика корутину, а `lambda`, возвращающая
    корутину, — обычная функция: её результат никто не ждёт. Поэтому обёртка —
    `async def`, а результат вызывается, только если это корутина: выделение и
    тап асинхронные (виброотклик), отмена перетаскивания — синхронная.
    """

    async def handle(event: ft.ControlEvent | None) -> None:
        if handler is None:
            return
        result = handler(view)
        if isinstance(result, Awaitable):
            await result

    return handle


def view_event_handler(
    handler: Callable[[ItemView | CategoryView, ft.Event], object] | None,
    view: ItemView | CategoryView,
):
    """Обработчик события с видом и самим событием: жесты и отметка пункта.

    Flet передаёт событие первым аргументом, а обработчику приложения нужен ещё
    и вид, к которому событие относится (пункт или категория), поэтому
    обработчики замыкаются на вид. Из события берутся координаты пальца (жесты
    перетаскивания) либо новое значение чекбокса; сам вид известен заранее.
    Обработчик может быть синхронным (движение) и асинхронным (отпускание
    сохраняет порядок, переключение отметки пишет в БД), поэтому результат
    ожидается только если это корутина.
    """

    async def handle(event: ft.Event) -> None:
        if handler is None:
            return
        result = handler(view, event)
        if isinstance(result, Awaitable):
            await result

    return handle


@dataclass(frozen=True)
class ItemGestures:
    """Жесты пункта и переключение его отметки.

    Пункт создаётся категорией, поэтому обработчики передаются одним объектом:
    шесть отдельных параметров раздували бы конструкторы `CategoryView` и
    `ItemView`. `long_press` и `tap` вызываются без события (пункт уже известен),
    `drag_*` и `toggle` — с событием: из него берутся координаты пальца у
    жестов, а у отметки — новое значение чекбокса.
    """

    long_press: Callable[[ItemView], object] | None = None
    drag_start: Callable[[ItemView, ft.LongPressStartEvent], object] | None = None
    drag_move: Callable[[ItemView, ft.LongPressMoveUpdateEvent], object] | None = None
    drag_end: Callable[[ItemView, ft.LongPressEndEvent], object] | None = None
    drag_cancel: Callable[[ItemView], object] | None = None
    tap: Callable[[ItemView], object] | None = None
    toggle: Callable[[ItemView, ft.ControlEvent], object] | None = None


@dataclass(frozen=True)
class CategoryGestures:
    """Жесты категории: выделение и перетаскивание всей панели.

    Категория ловит их сама (как и пункт), а не через `ReorderableListView`:
    штатный drag прокручивал список, когда край экрана касалась любая часть
    категории, и длинная категория уезжала сразу (см. `_autoscroll_span()`).
    Внутри панели лежат строки пунктов со своими жестами — они глубже в дереве и
    выигрывают арену, поэтому долгое нажатие по пункту поднимает пункт.
    Обработчики передаются одним объектом: `drag_*` получают ещё и событие
    жеста — из него берутся координаты пальца.
    """

    long_press: Callable[[CategoryView], object] | None = None
    drag_start: Callable[[CategoryView, ft.LongPressStartEvent], object] | None = None
    drag_move: Callable[
        [CategoryView, ft.LongPressMoveUpdateEvent], object
    ] | None = None
    drag_end: Callable[[CategoryView, ft.LongPressEndEvent], object] | None = None
    drag_cancel: Callable[[CategoryView], object] | None = None
