"""Виды: категория и пункт на экране.

`TitledView` — общая часть обоих: название, ввод нового названия и
операция хранилища, которая его сохраняет. `CategoryView` держит пункты
и панель, `ItemView` — чекбокс, строку и отметку."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import flet as ft

import domain
from storage import Storage
from ui.controls import (
    category_panel_padding,
    create_category_content,
    create_category_input,
    create_category_item,
    create_category_panel,
    create_category_title,
    create_item_cell,
    create_item_checkbox,
    create_item_checkbox_area,
    create_item_input,
    create_item_panel,
    create_item_row,
    create_item_title,
    create_items_box,
    item_title_style,
)
from ui.gestures import (
    CategoryGestures,
    ItemGestures,
    item_event_handler,
    view_event_handler,
)
from ui.theme import (
    CATEGORY_ITEM_PADDING,
    CATEGORY_PANEL_COLOR,
    CATEGORY_PANEL_SELECTED_COLOR,
    CATEGORY_TITLE_PADDING,
    ITEM_CELL_PADDING,
    ITEM_CHECKED_COLOR,
    ITEM_PANEL_COLOR,
    ITEM_PANEL_SELECTED_COLOR,
    ITEMS_BOX_PADDING,
)


class TitledView:
    """Общая часть категории и пункта: название и ввод нового названия.

    Ввод устроен одинаково: поле занимает место названия (`title_slot`), а
    после завершения на его место возвращается текст. Различаются только
    стиль текста, подсказка и операция хранилища.
    """

    default_title: str

    def __init__(self, title: str) -> None:
        self.title = title
        self.input: ft.TextField | None = None
        self.title_text = self.create_title_text(title)
        self.title_slot = ft.Container(content=self.title_text)

    @property
    def is_editing(self) -> bool:
        return self.input is not None

    def show_input(self, field: ft.TextField) -> None:
        """Ставит поле ввода на место названия."""
        self.input = field
        self.title_slot.content = field

    def show_title(self) -> None:
        """Возвращает текст названия на место поля ввода."""
        self.input = None
        self.title_text.value = self.title
        self.title_slot.content = self.title_text

    # Реализуют подклассы: категория и пункт отличаются стилем и хранилищем.
    def create_title_text(self, title: str) -> ft.Text:
        raise NotImplementedError

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        raise NotImplementedError

    def save_title(self, storage: Storage, title: str) -> str:
        raise NotImplementedError


class CategoryView(TitledView):
    """Категория на экране: панель с названием, пункты, выделение и ввод."""

    default_title = domain.DEFAULT_CATEGORY_TITLE

    def __init__(
        self,
        category: domain.Category,
        items: Sequence[domain.Item] = (),
        *,
        gestures: ItemGestures | None = None,
        category_gestures: CategoryGestures | None = None,
    ) -> None:
        super().__init__(category.title)
        self.category = category
        # Обработчики жестов пунктов передаёт приложение: без них пункт не смог
        # бы выделяться и не знал бы о выделении своей категории.
        self.gestures = gestures or ItemGestures()
        # Обработчики перетаскивания самой категории: выделение и drag за
        # название.
        self.category_gestures = category_gestures or CategoryGestures()
        # Горизонтальный отступ названия переехал с панели на слот названия:
        # так фон выделенного пункта закрашивает всю ширину панели.
        self.title_slot.padding = CATEGORY_TITLE_PADDING
        # Высота названия нужна модели перетаскивания пунктов: по ней считается,
        # где внутри панели начинается контейнер пунктов.
        self.title_height: float | None = None
        self.title_slot.on_size_change = self._on_title_size_change
        # Размеры панели: приходят от клиента и нужны перетаскиванию категории —
        # по ним строятся прокси и зазор, а свёрнутая панель их не меняет.
        self.height: float | None = None
        self.width: float | None = None
        self._collapsed = False
        self.items: list[ItemView] = []
        self.items_box = create_items_box()
        # Зазор на месте вставки: лежит в контейнере пунктов, пока идёт
        # перетаскивание; создаётся приложением на каждый drag.
        self.gap_index: int | None = None
        self.panel = create_category_panel(
            create_category_content(self.title_slot, self.items_box)
        )
        self.panel.on_size_change = self._on_panel_size_change
        # Жесты категории — на обёртке панели, а не на названии: панель
        # сворачивается при перетаскивании, и распознаватель внутри неё клиент
        # пересоздал бы вместе с содержимым — жест оборвался бы на первом же
        # обновлении экрана (см. `collapse`). Так же устроена строка пункта.
        self.gesture_area = ft.GestureDetector(content=self.panel)
        self.gesture_area.on_long_press = item_event_handler(
            self.category_gestures.long_press, self
        )
        self.gesture_area.on_long_press_start = view_event_handler(
            self.category_gestures.drag_start, self
        )
        self.gesture_area.on_long_press_move_update = view_event_handler(
            self.category_gestures.drag_move, self
        )
        self.gesture_area.on_long_press_end = view_event_handler(
            self.category_gestures.drag_end, self
        )
        self.gesture_area.on_long_press_cancel = item_event_handler(
            self.category_gestures.drag_cancel, self
        )
        self.item = create_category_item(self.gesture_area)
        self.selected = False
        for item in items:
            self.append_item(item)
        self._sync_items_box()

    def create_title_text(self, title: str) -> ft.Text:
        return create_category_title(title)

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        return create_category_input(
            self.default_title, on_commit, value, on_tap_outside
        )

    def save_title(self, storage: Storage, title: str) -> str:
        return storage.set_category_title(self.category.id, title)

    def _on_title_size_change(self, event: ft.LayoutSizeChangeEvent) -> None:
        """Клиент сообщил высоту названия: она нужна модели перетаскивания."""
        self.title_height = event.height

    def _on_panel_size_change(self, event: ft.LayoutSizeChangeEvent) -> None:
        """Клиент сообщил размер панели: по нему строятся прокси и зазор.

        Пока панель свёрнута, её высота равна нулю — это не настоящий размер
        панели, и запоминать его нельзя (как и у свёрнутой строки пункта).
        """
        if self._collapsed:
            return
        self.height = event.height
        self.width = event.width

    @property
    def collapsed(self) -> bool:
        """Панель свёрнута: на её месте стоит зазор, сама она в прокси."""
        return self._collapsed

    def collapse(self) -> None:
        """Сворачивает панель: её место занимает зазор, а саму её показывает прокси.

        Высота меняется у самой панели, а не у обёртки с `GestureDetector`:
        иначе клиент пересоздал бы распознаватель, и жест перетаскивания
        оборвался бы на первом же обновлении экрана. Промежуток до следующей
        категории принадлежит обёртке, поэтому снимается и он: иначе на месте
        категории осталась бы лишняя высота — остаток, который пропадал бы
        только после отпускания.
        """
        self._collapsed = True
        self.panel.height = 0
        self.item.padding = None

    def restore(self) -> None:
        """Возвращает панель на место после перетаскивания."""
        self._collapsed = False
        self.panel.height = None
        self.item.padding = CATEGORY_ITEM_PADDING

    def place_gap(
        self, gap: ft.Container, index: int, dragged: ItemView | None = None
    ) -> None:
        """Ставит зазор на место вставки: перед строкой ``index``.

        ``index`` — номер строки среди оставшихся (без перетаскиваемой),
        ``0..n``: ``n`` — в конец категории. Контейнер пунктов остаётся
        видимым, пока в нём лежит свёрнутая строка: иначе она исчезла бы из
        дерева вместе с жестом.
        """
        controls: list[ft.Control] = []
        remaining = 0
        placed = False
        for view in self.items:
            if not placed and remaining == index:
                controls.append(gap)
                placed = True
            if view is not dragged:
                remaining += 1
            controls.append(view.cell)
        if not placed:
            controls.append(gap)
        self.items_box.content.controls = controls
        self.gap_index = index
        self._sync_items_box()

    def remove_gap(self) -> None:
        """Убирает зазор и возвращает контейнеру пунктов обычный вид."""
        self.items_box.content.controls = [view.cell for view in self.items]
        self.gap_index = None
        self._sync_items_box()

    def append_item(self, item: domain.Item) -> "ItemView":
        """Добавляет пункт в конец контейнера пунктов категории."""
        view = ItemView(item, self.gestures)
        view.category_view = self
        self.items.append(view)
        self.items_box.content.controls.append(view.cell)
        self._sync_items_box()
        return view

    def _sync_items_box(self) -> None:
        """Приводит контейнер пунктов и отступы панели к их содержимому.

        Промежуток между пунктами принадлежит ячейке строки, поэтому у панели
        нижний отступ на этот промежуток меньше, пока в контейнере есть что
        показывать. Если показывать нечего (в категории осталась только свёрнутая
        строка перетаскиваемого пункта), контейнер не занимает места вовсе: панель
        выглядит как у категории без пунктов, поэтому после отпускания её высота
        не меняется.
        """
        has_box = bool(self.items) or self.gap_index is not None
        has_content = self.gap_index is not None or any(
            not item.collapsed for item in self.items
        )
        self.items_box.visible = has_box
        self.items_box.padding = ITEMS_BOX_PADDING if has_content else None
        self.panel.padding = category_panel_padding(has_content)

    def set_selected(self, selected: bool) -> None:
        """Выделенная категория отличается от остальных цветом панели."""
        self.selected = selected
        self.panel.bgcolor = (
            CATEGORY_PANEL_SELECTED_COLOR if selected else CATEGORY_PANEL_COLOR
        )


class ItemView(TitledView):
    """Пункт на экране: чекбокс слева, название справа.

    Пункт лежит внутри панели категории, поэтому в обычном состоянии его фон
    прозрачный: сквозь него видна панель, в том числе когда категория выделена.
    Выделенный пункт закрашивается тем же цветом, что и выделенная категория.
    Отметка показывается чекбоксом из БД, а отмеченная строка — серая
    (`ITEM_CHECKED_COLOR`): тап по чекбоксу переключает отметку и пишет её в БД
    (см. `ChecklistApp.toggle_item_checked`).
    """

    default_title = domain.DEFAULT_ITEM_TITLE

    def __init__(
        self,
        item: domain.Item,
        gestures: ItemGestures | None = None,
    ) -> None:
        # Пункт запоминается до создания названия: от отмеченности зависит стиль
        # текста (отмеченный пункт — серый), а `create_title_text` вызывается
        # из конструктора базового класса.
        self.item = item
        super().__init__(item.title)
        self.gestures = gestures or ItemGestures()
        # Категория, в панели которой лежит пункт: по ней решается, что делает
        # тап — внутри выделенной категории он выделяет пункт.
        self.category_view: CategoryView | None = None
        self.selected = False
        # Размеры строки: приходят от клиента (`size_change`) и нужны модели
        # перетаскивания, чтобы знать, где кончается один пункт и начинается
        # следующий, а прокси — чтобы совпасть со строкой по размеру.
        self.height: float | None = None
        self.width: float | None = None
        # Название занимает всё место справа от чекбокса и переносится
        # на вторую строку внутри этой ширины.
        self.title_slot.expand = True
        self.checkbox = create_item_checkbox(item)
        # Чекбокс с прозрачным запирающим слоем: пока что-то выделено или идёт
        # ввод названия, слой виден и ловит тап, поэтому чекбокс не переключается
        # даже на мгновение (см. `create_checkbox_blocker`). Показывать слой
        # приложению помогает `_apply_selection()`.
        self.checkbox_area, self.checkbox_blocker = create_item_checkbox_area(
            self.checkbox
        )
        # Отметку переключает сам чекбокс: тап по нему не доходит до жестов
        # строки (вложенный распознаватель выигрывает арену), поэтому выделение
        # от него не меняется. Что делать с отметкой (её можно менять только
        # без выделения) решает приложение.
        self.checkbox.on_change = view_event_handler(self.gestures.toggle, self)
        self.panel = create_item_panel(self.checkbox_area, self.title_slot)
        self.row = create_item_row(self.panel)
        # Ячейка в контейнере пунктов: строка вместе с промежутком до следующей
        # (см. `create_item_cell`). Она же сворачивается вместе со строкой.
        self.cell = create_item_cell(self.row)
        self._collapsed = False
        # Жесты назначаются после создания строки: обработчики замыкаются на
        # сам пункт. Долгое нажатие приходит двумя событиями — `start` даёт
        # координаты пальца для перетаскивания, `long_press` выделяет пункт
        # (порядок событий задаёт Flutter: сначала `start`).
        self.row.on_tap = item_event_handler(self.gestures.tap, self)
        self.row.on_long_press = item_event_handler(self.gestures.long_press, self)
        self.row.on_long_press_start = view_event_handler(
            self.gestures.drag_start, self
        )
        self.row.on_long_press_move_update = view_event_handler(
            self.gestures.drag_move, self
        )
        self.row.on_long_press_end = view_event_handler(self.gestures.drag_end, self)
        self.row.on_long_press_cancel = item_event_handler(
            self.gestures.drag_cancel, self
        )
        self.row.on_size_change = self._on_row_size_change

    def _on_row_size_change(self, event: ft.LayoutSizeChangeEvent) -> None:
        """Клиент сообщил размер строки: он нужен модели перетаскивания.

        Пока строка свёрнута, её высота равна нулю — это не настоящий размер
        строки, и запоминать его нельзя.
        """
        if self._collapsed:
            return
        self.height = event.height
        self.width = event.width

    @property
    def collapsed(self) -> bool:
        """Строка свёрнута: она остаётся в дереве, но места не занимает."""
        return self._collapsed

    def collapse(self) -> None:
        """Сворачивает строку: её место занимает зазор, а саму строку показывает прокси.

        Высота меняется у самой панели строки, а не у обёртки над
        `GestureDetector`: иначе Flutter пересоздал бы распознаватель, и жест
        перетаскивания оборвался бы на первом же обновлении экрана. Промежуток до
        следующего пункта принадлежит ячейке, поэтому сворачивается и она: иначе
        в контейнере осталась бы лишняя высота на месте пункта.
        """
        self._collapsed = True
        self.panel.height = 0
        self.cell.padding = None
        self._sync_category()

    def restore(self) -> None:
        """Возвращает строку на место после перетаскивания."""
        self._collapsed = False
        self.panel.height = None
        self.cell.padding = ITEM_CELL_PADDING
        self._sync_category()

    def _sync_category(self) -> None:
        """Сообщает категории, что строк стало видно меньше или больше."""
        if self.category_view is not None:
            self.category_view._sync_items_box()

    def create_title_text(self, title: str) -> ft.Text:
        return create_item_title(title, checked=self.item.is_checked)

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        return create_item_input(self.default_title, on_commit, value, on_tap_outside)

    def save_title(self, storage: Storage, title: str) -> str:
        return storage.set_item_title(self.item.id, title)

    def set_checkbox_blocked(self, blocked: bool) -> None:
        """Запирает чекбокс прозрачным слоем, не меняя его вид.

        Клик по чекбоксу в запертом состоянии не доходит до него вовсе, поэтому
        он не переключается даже на мгновение (см. `create_checkbox_blocker`).
        """
        self.checkbox_blocker.visible = blocked

    def set_checked(self, checked: bool) -> None:
        """Применяет отметку к строке: чекбокс и серый цвет отмеченного пункта.

        Модель (`item`) и вид обновляются вместе: чекбокс показывает отметку из
        модели, а название перекрашивается в серый. Размер и положение строки
        при этом не меняются — меняются только цвета.
        """
        self.item = replace(self.item, is_checked=checked)
        self.checkbox.value = checked
        self.checkbox.active_color = ITEM_CHECKED_COLOR if checked else None
        self.title_text.style = item_title_style(checked)

    def set_selected(self, selected: bool) -> None:
        """Выделенный пункт красится тем же цветом, что и выделенная категория."""
        self.selected = selected
        self.panel.bgcolor = (
            ITEM_PANEL_SELECTED_COLOR if selected else ITEM_PANEL_COLOR
        )
