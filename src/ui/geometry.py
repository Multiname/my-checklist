"""Геометрия списка для перетаскивания: раскладка, зазоры и места вставки.

Сервер не знает координат контролов, поэтому раскладка собирается из
высот, которые клиент присылает событием `size_change`, и констант
шаблона. Координаты — в логических пикселях, как и позиции пальца в
событиях жестов; начало координат — верх списка (отступ `LIST_PADDING`).
Абсолютное смещение не важно: в начале перетаскивания раскладка
привязывается к реальному положению нажатой строки
(см. `ChecklistApp._on_item_drag_start`)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ui.controls import category_panel_padding, item_slot_height
from ui.theme import (
    CATEGORY_ITEMS_TOP,
    CATEGORY_PANEL_VERTICAL_PADDING,
    CATEGORY_SPACING,
    ITEM_SPACING,
    LIST_PADDING,
)


# Геометрия списка для перетаскивания пунктов.
#
# Сервер не знает координат контролов, поэтому раскладка собирается из высот,
# которые клиент присылает событием `size_change` (`ItemView.height`,
# `CategoryView.title_height`), и констант шаблона. Координаты — в логических
# пикселях, как и позиции пальца в событиях жестов; начало координат — верх
# списка (отступ `LIST_PADDING`). Абсолютное смещение не важно: в начале
# перетаскивания раскладка привязывается к реальному положению нажатой строки
# (см. `ChecklistApp._on_item_drag_start`).


@dataclass(frozen=True)
class DragEntry:
    """Строка пункта или зазор на месте вставки в раскладке перетаскивания.

    ``row_index`` — номер строки среди оставшихся в категории (без
    перетаскиваемой); у зазора и у самой перетаскиваемой строки его нет.
    """

    top: float
    bottom: float
    row_index: int | None = None
    gap: bool = False

    @property
    def is_row(self) -> bool:
        return self.row_index is not None


@dataclass(frozen=True)
class DragSpan:
    """Панель категории в раскладке перетаскивания пункта."""

    top: float
    bottom: float
    items_top: float
    entries: tuple[DragEntry, ...]

    @property
    def row_count(self) -> int:
        """Сколько строк категории остаётся, не считая перетаскиваемой."""
        return sum(1 for entry in self.entries if entry.is_row)


def base_row_top(
    metrics: Sequence[tuple[float, Sequence[float]]],
    category_index: int,
    row_index: int,
) -> float:
    """Верх строки в исходной раскладке списка (до сворачивания строки).

    Нужен, чтобы привязать раскладку к пальцу: точка нажатия внутри строки
    минус её верх в модели — это экранное начало координат списка.
    """
    top = LIST_PADDING
    for index, (title_height, heights) in enumerate(metrics):
        items_top = (
            top
            + CATEGORY_PANEL_VERTICAL_PADDING
            + title_height
            + CATEGORY_ITEMS_TOP
        )
        if index == category_index:
            return items_top + sum(
                height + ITEM_SPACING for height in heights[:row_index]
            )
        top = _panel_bottom(items_top, heights) + CATEGORY_SPACING
    raise IndexError(category_index)


def build_drag_spans(
    metrics: Sequence[tuple[float, Sequence[float]]],
    *,
    source: tuple[int, int],
    height: float,
    target: tuple[int, int],
) -> list[DragSpan]:
    """Раскладка списка во время перетаскивания пункта.

    ``metrics`` — пары «высота названия категории, высоты её пунктов» в порядке
    списка. Строка перетаскиваемого пункта свёрнута и места не занимает, а на
    месте будущей вставки ``target`` стоит зазор высотой в целый слот пункта
    (`item_slot_height`): панели категорий расходятся так же, как при
    перетаскивании категории, и место вставки видно до отпускания. Слоты
    остальных пунктов — тоже целые: промежуток принадлежит ячейке строки, поэтому
    у панели нижний отступ на промежуток меньше, пока в ней есть что показывать
    (см. `category_panel_padding`). ``source`` — (категория, строка)
    перетаскиваемого пункта, ``target`` — (категория, номер строки среди
    оставшихся), куда он встанет.
    """
    spans: list[DragSpan] = []
    top = LIST_PADDING
    for category_index, (title_height, heights) in enumerate(metrics):
        items_top = (
            top
            + CATEGORY_PANEL_VERTICAL_PADDING
            + title_height
            + CATEGORY_ITEMS_TOP
        )
        # Слоты категории по порядку: высота, номер оставшейся строки (None —
        # свёрнутая строка или зазор), признак зазора.
        slots: list[tuple[float, int | None, bool]] = []
        remaining = 0
        for row_index, row_height in enumerate(heights):
            if (category_index, row_index) == source:
                slots.append((0.0, None, False))
                continue
            slots.append((row_height, remaining, False))
            remaining += 1
        if target[0] == category_index:
            position = len(slots)
            seen = 0
            for slot_index, (_, row_index, _) in enumerate(slots):
                if row_index is None:
                    continue
                if seen == target[1]:
                    position = slot_index
                    break
                seen += 1
            slots.insert(position, (item_slot_height(height), None, True))
        entries: list[DragEntry] = []
        # Низ содержимого контейнера и признак того, что показывать есть что:
        # зазор или хотя бы одна несвёрнутая строка.
        content_bottom = items_top
        has_content = False
        for slot_height, row_index, is_gap in slots:
            entries.append(
                DragEntry(
                    top=content_bottom,
                    bottom=content_bottom + slot_height,
                    row_index=row_index,
                    gap=is_gap,
                )
            )
            if is_gap:
                content_bottom += slot_height
                has_content = True
            elif row_index is not None:
                content_bottom += item_slot_height(slot_height)
                has_content = True
        if has_content:
            panel_bottom = content_bottom + category_panel_padding(True).bottom
        else:
            # Контейнер пунктов ничего не показывает и отступов не несёт: в
            # панели только название.
            panel_bottom = (
                items_top - CATEGORY_ITEMS_TOP + CATEGORY_PANEL_VERTICAL_PADDING
            )
        spans.append(
            DragSpan(
                top=top,
                bottom=panel_bottom,
                items_top=items_top,
                entries=tuple(entries),
            )
        )
        top = panel_bottom + CATEGORY_SPACING
    return spans


def _panel_bottom(items_top: float, heights: Sequence[float]) -> float:
    """Низ панели категории по её строкам (без зазоров перетаскивания)."""
    if heights:
        return (
            items_top
            + sum(heights)
            + ITEM_SPACING * (len(heights) - 1)
            + CATEGORY_PANEL_VERTICAL_PADDING
        )
    return items_top - CATEGORY_ITEMS_TOP + CATEGORY_PANEL_VERTICAL_PADDING


def category_panel_height(
    title_height: float, heights: Sequence[float]
) -> float:
    """Высота панели категории по шаблону: название, пункты и отступы.

    Нужна, когда клиент ещё не прислал размер самой панели (она за пределами
    видимой области). Считается по тем же правилам, что и `build_drag_spans`:
    промежуток принадлежит ячейке строки, поэтому нижний отступ панели меньше
    на него, пока в ней есть что показывать (`category_panel_padding`).
    """
    if heights:
        return (
            CATEGORY_PANEL_VERTICAL_PADDING
            + title_height
            + CATEGORY_ITEMS_TOP
            + sum(item_slot_height(height) for height in heights)
            + category_panel_padding(True).bottom
        )
    return CATEGORY_PANEL_VERTICAL_PADDING * 2 + title_height


def category_base_top(slots: Sequence[float], index: int) -> float:
    """Верх панели категории в модели списка (до её перетаскивания).

    Нужен, чтобы привязать раскладку к пальцу: экранная точка нажатия минус
    верх названия в модели — это экранное начало координат списка.
    """
    return LIST_PADDING + sum(slots[:index])


@dataclass(frozen=True)
class CategorySpan:
    """Категория или зазор на месте вставки в раскладке перетаскивания.

    ``index`` — номер категории среди оставшихся (без перетаскиваемой); у
    зазора его нет.
    """

    top: float
    bottom: float
    index: int | None = None

    @property
    def is_gap(self) -> bool:
        return self.index is None


def build_category_spans(
    slots: Sequence[float], *, dragged: int, target: int
) -> list[CategorySpan]:
    """Раскладка списка во время перетаскивания категории.

    ``slots`` — высоты слотов (панель вместе с промежутком до следующей) в
    порядке списка, ``dragged`` — индекс перетаскиваемой категории, ``target`` —
    место зазора среди оставшихся категорий (``0..n``). Слот перетаскиваемой
    свёрнут и места не занимает: на её месте стоит зазор той же высоты, поэтому
    остальные категории не сдвигаются ни в первый миг перетаскивания, ни после
    отпускания.
    """
    spans: list[CategorySpan] = []
    top = LIST_PADDING
    remaining = [index for index in range(len(slots)) if index != dragged]
    gap_height = slots[dragged] if dragged < len(slots) else 0.0
    for position in range(len(remaining) + 1):
        if position == target:
            spans.append(CategorySpan(top=top, bottom=top + gap_height))
            top += gap_height
        if position < len(remaining):
            index = remaining[position]
            spans.append(
                CategorySpan(top=top, bottom=top + slots[index], index=position)
            )
            top += slots[index]
    return spans


def category_span_at(spans: Sequence[CategorySpan], y: float) -> int:
    """Место вставки (номер среди оставшихся категорий) под координатой ``y``.

    Категория встаёт перед той, чья середина ниже пальца: перестановка
    начинается, когда палец проходит половину панели, а не на её границе.
    Зазор в подсчёте не участвует, поэтому место вставки не зависит от того,
    где зазор стоит сейчас, и не дрожит, когда он переезжает.
    """
    count = 0
    for span in spans:
        if span.is_gap:
            continue
        if y < (span.top + span.bottom) / 2:
            return count
        count += 1
    return count


def span_index_at(spans: Sequence[DragSpan], y: float) -> int:
    """Категория под координатой ``y`` или ближайшая к ней.

    Промежутки между категориями и отступы списка принадлежат ближайшей панели:
    отпускание пальца в промежутке не должно оставлять пункт без нового места.
    """
    for index, span in enumerate(spans):
        if span.top <= y <= span.bottom:
            return index
    best_index = 0
    best_distance: float | None = None
    for index, span in enumerate(spans):
        distance = span.top - y if y < span.top else y - span.bottom
        if best_distance is None or distance < best_distance:
            best_index, best_distance = index, distance
    return best_index


def drag_slot_at(spans: Sequence[DragSpan], y: float) -> tuple[int, int]:
    """Категория и место вставки (номер строки среди оставшихся) под пальцем.

    Пункт встаёт перед строкой, чья середина ниже пальца: перестановка
    начинается, когда палец проходит половину строки, а не на её границе.
    Зазор и свёрнутая строка в подсчёте не участвуют — поэтому место вставки
    не зависит от того, где зазор стоит сейчас.
    """
    index = span_index_at(spans, y)
    span = spans[index]
    if y < span.items_top:
        return index, 0
    for entry in span.entries:
        if not entry.is_row:
            continue
        if y < (entry.top + entry.bottom) / 2:
            return index, entry.row_index
    return index, span.row_count
