"""Состояние перетаскивания: пункта и категории.

Состояние живёт от подъёма до отпускания, а раскладку, прокси и зазор
считает `ChecklistApp` по моделям из `ui.geometry`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import flet as ft

from ui.theme import CATEGORY_PANEL_VERTICAL_PADDING, CATEGORY_SPACING

if TYPE_CHECKING:
    from ui.views import CategoryView, ItemView


@dataclass
class ItemDrag:
    """Перетаскивание пункта: состояние от долгого нажатия до отпускания.

    Строка «поднимается»: её панель сворачивается, в `Stack` над списком
    появляется её копия (`proxy`), которая двигается за пальцем по вертикали, а
    в контейнере пунктов на месте будущей вставки стоит зазор (`gap`). ``origin_y``
    — экранный верх содержимого списка, ``grab_y`` — высота, на которой палец взял
    строку, ``target`` — (категория, номер строки среди оставшихся), где сейчас
    зазор. Положение прокси по горизонтали не хранится: пункт едет в своём
    столбце, как категория. ``epoch`` нумерует запуски автопрокрутки, чтобы
    старый цикл не продолжал работать после остановки, а ``pass_extent`` — докуда
    список мог прокрутиться вниз в начале текущего прохода: по нему видно, вырос
    ли список за проход.
    """

    view: ItemView
    source: tuple[int, int]
    height: float
    origin_y: float
    grab_y: float
    start_y: float
    target: tuple[int, int]
    proxy: ft.Container | None = None
    gap: ft.Container | None = None
    moved: bool = False
    autoscroll: int = 0
    epoch: int = 0
    pass_extent: float | None = None


@dataclass
class CategoryDrag:
    """Перетаскивание категории: состояние от долгого нажатия до отпускания.

    Панель «поднимается»: её место в списке сворачивается, а над списком
    появляется её копия (`proxy`), которая двигается за пальцем по вертикали.
    На месте будущей вставки стоит зазор — `margin` соседнего элемента списка,
    перед которым категория встанет (или нижний отступ предыдущей, если место —
    конец списка, см. `_place_category_gap`). Самой поднятой панели отступ не
    назначается никогда: клиент пересоздаёт поддерево такого элемента вместе с
    распознавателем жеста. ``origin_y`` — экранный верх видимой области списка,
    ``grab_y`` — высота, на которой палец взял панель (считая от её верха, то
    есть с отступом панели), ``title_height`` — высота названия: по его полосе
    считается зона автопрокрутки. ``target`` — место вставки среди оставшихся
    категорий. Остальные поля — как у `ItemDrag`.
    """

    view: CategoryView
    source: int
    height: float
    width: float
    title_height: float
    origin_y: float
    grab_y: float
    start_y: float
    target: int
    proxy: ft.Container | None = None
    panel_top: float | None = None
    autoscroll: int = 0
    epoch: int = 0
    pass_extent: float | None = None

    @property
    def slot_height(self) -> float:
        """Сколько места занимает категория в списке: панель и промежуток."""
        return self.height + CATEGORY_SPACING

    def title_span(self) -> tuple[float, float] | None:
        """Экранные верх и низ области названия у поднятой панели.

        Зона автопрокрутки считается по этой полосе, а не по всей панели: иначе
        длинная категория касалась бы края экрана любым своим пунктом и список
        уезжал бы сразу после подъёма (см. `_autoscroll_span`).
        """
        if self.panel_top is None:
            return None
        top = self.panel_top + CATEGORY_PANEL_VERTICAL_PADDING
        return top, top + self.title_height
