"""Экран приложения: список категорий, button_area, выделение, ввод
названий и оба перетаскивания.

Состояние всего экрана — в `ChecklistApp`; виды элементов — в
`ui.views`, раскладка перетаскивания — в `ui.geometry`, шаблоны
контролов — в `ui.controls`. Хранилище синхронное: вызовы идут через
`asyncio.to_thread`, а запись выполняется до обновления экрана."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Sequence

import flet as ft

import domain
from storage import Storage
from ui.actions import ButtonAction, bind_button, create_button_area
from ui.controls import (
    create_category_area,
    create_category_list,
    create_category_proxy,
    create_item_gap,
    create_item_proxy,
    item_slot_height,
)
from ui.drag import CategoryDrag, ItemDrag
from ui.geometry import (
    CategorySpan,
    base_row_top,
    build_category_spans,
    build_drag_spans,
    category_base_top,
    category_panel_height,
    category_span_at,
    drag_slot_at,
)
from ui.gestures import CategoryGestures, ItemGestures
from ui.theme import (
    AUTOSCROLL_EDGE,
    AUTOSCROLL_EXTENT_EPS,
    AUTOSCROLL_HYSTERESIS,
    AUTOSCROLL_REST,
    AUTOSCROLL_SPEED,
    CATEGORY_SPACING,
    CATEGORY_TITLE_HEIGHT_FALLBACK,
    ITEM_DRAG_THRESHOLD,
    ITEM_ROW_HEIGHT_FALLBACK,
    LABEL_ADD_ITEM,
    LABEL_CREATE_CATEGORY,
    LABEL_DELETE_CATEGORY,
    LABEL_DELETE_ITEM,
    LABEL_RENAME_CATEGORY,
    LABEL_RENAME_ITEM,
    LIST_BOTTOM_PADDING,
    LIST_PADDING,
    SCROLL_INTERVAL_DRAG,
    SCROLL_INTERVAL_IDLE,
)
from ui.views import CategoryView, ItemView, TitledView

logger = logging.getLogger(__name__)


class ChecklistApp:
    """Экран списка категорий и обработчики button_area."""

    def __init__(
        self,
        page: ft.Page,
        storage: Storage,
        haptic: ft.HapticFeedback | None = None,
    ) -> None:
        self.page = page
        self.storage = storage
        # Сервис виброотклика: если не передан, создаётся в mount().
        self.haptic = haptic
        # Категории в порядке списка: индекс в нём совпадает с индексом
        # элемента в списке и с индексом в событиях перетаскивания.
        self.views: list[CategoryView] = []
        self.category_list = create_category_list()
        # Прокрутка нужна автопрокрутке при перетаскивании: по её событиям
        # видно, насколько содержимое уехало под пальцем.
        self.category_list.on_scroll = self._on_scroll
        # Текущая частота событий прокрутки: в покое редкая, при перетаскивании
        # частая (см. `_set_scroll_interval`).
        self._scroll_interval = SCROLL_INTERVAL_IDLE
        self.category_area = create_category_area(
            self.category_list, self._on_tap, self._on_tap_cancel
        )
        self._editing_view: TitledView | None = None
        # Выделен ровно один элемент — категория или пункт: выделение категории
        # снимается при выделении пункта и наоборот (см. docs/Project.md).
        self._selected_view: CategoryView | None = None
        self._selected_item: ItemView | None = None
        # Идёт перетаскивание категории: кнопки button_area скрыты целиком.
        self._dragging = False
        # Перетаскивание пункта: состояние жеста, категория с зазором и
        # последняя точка пальца (по ней считается место вставки).
        self._item_drag: ItemDrag | None = None
        # Перетаскивание категории: состояние жеста, прокси и зазор.
        self._category_drag: CategoryDrag | None = None
        self._gap_category: CategoryView | None = None
        self._pointer_y: float | None = None
        # Контролы, которые сдвинулись с прошлого показа экрана при
        # перетаскивании: прокси и зазор (см. `_flush_drag`).
        self._drag_controls: list[ft.Control] = []
        # Элемент списка, который держит зазор категории.
        self._category_gap_control: ft.Control | None = None
        # Прокрутка списка: нужна и автопрокрутке, и пересчёту места вставки.
        self._scroll_pixels = 0.0
        self._viewport: float | None = None
        # Докуда список может прокрутиться вниз: приходит с `on_scroll`, до
        # первой прокрутки неизвестно.
        self._max_scroll_extent: float | None = None
        # Жесты пунктов передаются категориям одним объектом: пункт создаётся
        # категорией и сам сообщает приложению, что с ним делают.
        self.gestures = ItemGestures(
            long_press=self._on_item_long_press,
            drag_start=self._on_item_drag_start,
            drag_move=self._on_item_drag_move,
            drag_end=self._on_item_drag_end,
            drag_cancel=self._on_item_drag_cancel,
            tap=self._on_item_tap,
            toggle=self.toggle_item_checked,
        )
        # Перетаскивание категории ведёт приложение: жест — долгое нажатие на
        # названии, дальше свои прокси, зазор и автопрокрутка по названию.
        self.category_gestures = CategoryGestures(
            long_press=self._on_category_long_press,
            drag_start=self._on_category_drag_start,
            drag_move=self._on_category_drag_move,
            drag_end=self._on_category_drag_end,
            drag_cancel=self._on_category_drag_cancel,
        )
        self.button_area = create_button_area(self._actions())
        (
            self.plus_button,
            self.pencil_button,
            self.trash_button,
        ) = self.button_area.content.controls
        # Прокси перетаскиваемого пункта живёт здесь же, выше списка: он должен
        # рисоваться поверх панелей категорий. Стек создаётся сразу, а не в
        # mount(), чтобы перетаскивание работало и в тестах без экрана.
        self.stack = ft.Stack(
            expand=True,
            fit=ft.StackFit.EXPAND,
            controls=[self.category_area, self.button_area],
        )
        self._keyboard_open = False
        # Тап вне поля закрыл клавиатуру: следующий on_tap списка — тот же
        # самый тап, он не должен снимать выделение (см. _on_tap).
        self._tap_ended_input = False
        self._apply_selection()

    async def mount(self) -> None:
        """Загружает категории и пункты из БД и собирает экран."""
        categories = await asyncio.to_thread(self.storage.list_categories)
        items = await asyncio.to_thread(self.storage.list_items)
        items_by_category: dict[int, list[domain.Item]] = {}
        for item in items:
            items_by_category.setdefault(item.category_id, []).append(item)
        for category in categories:
            self._append_category(category, items_by_category.get(category.id, ()))
        if self.haptic is None:
            self.haptic = ft.HapticFeedback()
            self.page.services.append(self.haptic)
        self.page.add(
            ft.SafeArea(
                expand=True,
                content=self.stack,
            )
        )
        # Жест «назад» на Android закрывает клавиатуру, не снимая фокус
        # с поля и не присылая on_blur: ввод завершаем по скрытию клавиатуры.
        self.page.on_media_change = self._on_media_change
        # «Назад» при выделенной категории перехватывается: вместо выхода
        # из приложения снимается выделение (см. _on_confirm_pop).
        self.page.views[0].on_confirm_pop = self._on_confirm_pop
        # Обработчики выше назначены после add() — отправляем их клиенту.
        self.page.update()
        if self.storage.recovered_backup is not None:
            self._show_message(
                "Файл данных был повреждён: создана пустая база. Прежние данные "
                f"потеряны (копия: {self.storage.recovered_backup.name})."
            )

    @staticmethod

    # Ввод названия: поле на месте названия, его завершение и клавиатура.

    def _keyboard_visible(media: ft.PageMediaData) -> bool:
        """Клавиатура открыта. При adjustResize её высота не попадает в
        view_insets: Flutter отдаёт нулевой нижний системный отступ, и
        единственный признак — пропавший нижний padding навигации."""
        if media.device_pixel_ratio == 0:
            # page.media ещё не обновлён клиентом: данных о системе нет.
            return False
        return media.view_insets.bottom > 0 or media.padding.bottom == 0

    def _on_media_change(self, media: ft.PageMediaData) -> None:
        if self._keyboard_visible(media):
            self._keyboard_open = True
        elif self._keyboard_open:
            self._keyboard_open = False
            self._commit_editing()

    def _commit_editing(self) -> None:
        view = self._editing_view
        if view is not None:
            self.page.run_task(self._finish_title_input, view)

    async def _start_title_input(
        self,
        view: TitledView,
        initial: str | None = None,
        scroll_to_end: bool = False,
    ) -> None:
        """Показывает поле ввода на месте названия и открывает клавиатуру.

        ``initial`` — прежнее название: при переименовании поле заполнено им.
        ``scroll_to_end`` — для новой категории: она добавлена в конец, и её
        надо доскроллить, чтобы поле было видно. Новый пункт может быть и не
        последним на экране, поэтому для него прокрутку делает сам Flutter:
        поле в фокусе он показывает на экране. Переименовываемый элемент
        (категория или пункт) уже выделен на экране — прокрутка ему не нужна.
        """
        field = self._begin_title_input(view, initial)
        if scroll_to_end:
            await self.category_list.scroll_to(offset=-1)
        await field.focus()

    def _begin_title_input(
        self, view: TitledView, initial: str | None = None
    ) -> ft.TextField:
        """Переводит название в режим ввода и скрывает кнопки button_area."""
        field = view.create_input(
            value=initial or "",
            on_commit=self._title_commit_handler(view),
            on_tap_outside=self._title_tap_outside_handler(view),
        )
        view.show_input(field)
        self._editing_view = view
        self._tap_ended_input = False
        # Пока идёт ввод, кнопки скрыты: клавиатура иначе поднимала бы их
        # вместе с содержимым, и они перекрывали бы список.
        self._apply_selection()
        # Клавиатура может быть уже открыта (ввод уже начат).
        self._keyboard_open = self._keyboard_visible(self.page.media)
        # Патч с новым полем должен уйти раньше вызова focus(): иначе клиент
        # ещё не знает контрол, к которому относится вызов.
        self.page.update()
        return field

    def _title_commit_handler(self, view: TitledView):
        async def commit(event: ft.ControlEvent) -> None:
            await self._finish_title_input(view)

        return commit

    def _title_tap_outside_handler(self, view: TitledView):
        """Тап вне поля: завершает ввод и помечает, что тап уже обработан.

        `on_tap_outside` приходит на нажатие, а `on_tap` списка — на отпускание,
        поэтому без флага тот же самый тап снял бы выделение, чего спека не
        разрешает. Флаг выставляется, только если ввод ещё идёт: если тап
        списка пришёл первым и уже завершил ввод, помечать нечего.
        """

        async def tap_outside(event: ft.ControlEvent) -> None:
            if view.input is None:
                return
            self._tap_ended_input = True
            await self._finish_title_input(view)

        return tap_outside

    async def _finish_title_input(self, view: TitledView) -> None:
        """Сохраняет введённое название и возвращает на место поля текст.

        Название категории и название пункта вводятся одинаково; различаются
        только дефолт (``view.default_title``) и операция хранилища
        (``view.save_title``).
        """
        field = view.input
        if field is None:
            # on_blur приходит после on_submit/on_tap_outside — второй раз не пишем.
            return
        view.input = None
        if self._editing_view is view:
            self._editing_view = None
        new_title = domain.normalize_title(field.value, view.default_title)
        if new_title != view.title:
            try:
                # Коммит в БД — до обновления UI: при ошибке экран не меняется.
                new_title = await asyncio.to_thread(
                    view.save_title, self.storage, new_title
                )
            except Exception:
                logger.exception("Не удалось сохранить название")
                self._show_message("Не удалось сохранить название")
            else:
                view.title = new_title
        view.show_title()
        if self._editing_view is None:
            # Ввод завершён — кнопки возвращаются в правый нижний угол.
            self._apply_selection()
        # Финиш может прийти из задачи (закрытие клавиатуры), а не из события:
        # автообновление в этом случае не сработает, поэтому обновляем явно.
        self.page.update()

    # Операции с данными: категории, пункты и сообщения об ошибках.

    async def create_category(self, event: ft.ControlEvent) -> None:
        """create_category: категория в конец списка, затем ввод названия."""
        try:
            category = await asyncio.to_thread(self.storage.create_category)
        except Exception:
            logger.exception("Не удалось создать категорию")
            self._show_message("Не удалось создать категорию")
            return
        view = self._append_category(category)
        await self._start_title_input(view, scroll_to_end=True)

    async def add_item(self, event: ft.ControlEvent | None = None) -> None:
        """add_item: пункт в конец выделенной категории, затем ввод названия.

        Запись в БД — до обновления экрана: при ошибке новый пункт не
        появляется и показывается сообщение. Поле ввода открывается сразу
        после создания пункта, с пустым значением и подсказкой «Пункт»:
        не введённое название остаётся дефолтным. Поля в фокусе Flutter сам
        показывает на экране, поэтому список к новому пункту прокручивается
        без явного scroll_to: категория не обязательно последняя.
        """
        view = self._selected_view
        if view is None or self._editing_view is not None:
            # Кнопка показана только при выделенной категории; ввод названия
            # скрывает button_area целиком, повторный вызов невозможен.
            return
        try:
            item = await asyncio.to_thread(self.storage.create_item, view.category.id)
        except Exception:
            logger.exception("Не удалось добавить пункт")
            self._show_message("Не удалось добавить пункт")
            return
        item_view = view.append_item(item)
        await self._start_title_input(item_view)

    async def rename_category(
        self, event: ft.ControlEvent | None = None
    ) -> None:
        """rename_category: ввод нового названия вместо названия категории.

        Поле открывается с прежним названием выделенной категории, поэтому
        ввод можно дополнить, а не набирать заново. Выделение при
        переименовании не снимается: после сохранения кнопки
        `rename_category`/`delete_category` остаются на месте.
        """
        view = self._selected_view
        if view is None or self._editing_view is not None:
            # Кнопка показана только при выделенной категории; ввод названия
            # скрывает button_area целиком, повторный вызов невозможен.
            return
        await self._start_title_input(view, initial=view.title)

    async def rename_item(self, event: ft.ControlEvent | None = None) -> None:
        """rename_item: ввод нового названия вместо названия пункта.

        Поле открывается с прежним названием выделенного пункта, поэтому
        ввод можно дополнить, а не набирать заново. Выделение при
        переименовании не снимается: после сохранения кнопки
        `rename_item`/`delete_item` остаются на месте. Ввод на месте названия
        обслуживает та же машинерия, что и у категории: `ItemView` — это
        `TitledView`, а запись идёт в `Storage.set_item_title()`.
        """
        view = self._selected_item
        if view is None or self._editing_view is not None:
            # Кнопка показана только при выделенном пункте; ввод названия
            # скрывает button_area целиком, повторный вызов невозможен.
            return
        await self._start_title_input(view, initial=view.title)

    async def delete_category(self, event: ft.ControlEvent | None = None) -> None:
        """delete_category: удаляет выделенную категорию из списка и из БД.

        Запись в БД — до обновления экрана: при ошибке категория остаётся на
        месте и показывается сообщение. Вместе с категорией каскадом уходят её
        пункты (см. docs/features/feature-storage.md). Выделение снимается:
        удалённой категории больше нет, кнопки возвращаются к исходному составу.
        Порядок оставшихся берётся из БД, как и после перетаскивания.
        """
        view = self._selected_view
        if view is None:
            # Кнопка показана только при выделенной категории.
            return
        editing = self._editing_view
        if editing is not None and (editing is view or editing in view.items):
            # Ввод названия скрывает button_area целиком, так что сюда не
            # попадают; если состояние всё же такое, поле уходит вместе
            # с панелью, а не остаётся фокусом у несуществующей категории
            # или её пункта.
            editing.input = None
            self._editing_view = None
            self._keyboard_open = False
        try:
            ordered = await asyncio.to_thread(
                self.storage.delete_category, view.category.id
            )
        except Exception:
            logger.exception("Не удалось удалить категорию")
            self._show_message("Не удалось удалить категорию")
            return
        self._remove_view(view)
        self._selected_view = None
        if (
            self._selected_item is not None
            and self._selected_item.category_view is view
        ):
            # Выделение пункта и категории взаимоисключающие, поэтому через UI
            # такое состояние недостижимо; на случай рассинхронизации пункт
            # снимаем вместе с его панелью.
            self._selected_item.set_selected(False)
            self._selected_item = None
        self._apply_category_order(ordered)
        self._apply_selection()
        self.page.update()

    async def delete_item(self, event: ft.ControlEvent | None = None) -> None:
        """delete_item: удаляет выделенный пункт из списка и из БД.

        Запись в БД — до обновления экрана: при ошибке пункт остаётся на месте
        и показывается сообщение. Выделение снимается: удалённого пункта больше
        нет, кнопки возвращаются к исходному составу. Порядок оставшихся берётся
        из БД, как и после перетаскивания, поэтому дыр в позициях не остаётся.
        """
        view = self._selected_item
        if view is None:
            # Кнопка показана только при выделенном пункте.
            return
        category = view.category_view
        if category is None or view not in category.items:
            return
        editing = self._editing_view
        if editing is view:
            # Ввод названия скрывает button_area целиком, так что сюда не
            # попадают; если состояние всё же такое, поле уходит вместе со
            # строкой, а не остаётся фокусом у несуществующего пункта.
            editing.input = None
            self._editing_view = None
            self._keyboard_open = False
        try:
            remaining = await asyncio.to_thread(
                self.storage.delete_item, view.item.id
            )
        except Exception:
            logger.exception("Не удалось удалить пункт")
            self._show_message("Не удалось удалить пункт")
            return
        self._selected_item = None
        view.set_selected(False)
        self._apply_item_orders({category.category.id: remaining})
        self._apply_selection()
        self.page.update()

    async def toggle_item_checked(
        self, view: ItemView, event: ft.ControlEvent | None = None
    ) -> None:
        """Отметка пункта: тап по чекбоксу переключает состояние и пишет его в БД.

        По спеке отметка переключается, только когда не выделена ни категория, ни
        пункт (docs/features/feature-item.md). Обычный тап в это время до
        чекбокса не доходит — его ловит прозрачный запирающий слой
        (`create_checkbox_blocker`), поэтому клиент даже не рисует переключение.
        Проверка здесь остаётся страховкой: событие может прийти от TalkBack
        (он активирует чекбокс без тапа) или когда выделение появилось между
        событием и обработкой. Тогда значение из модели уходит обратно клиенту.

        Запись — до обновления экрана: при ошибке чекбокс и цвет названия
        остаются прежними, показывается сообщение. Новое значение приходит из
        хранилища, которое принимает его явно (`Storage.set_item_checked`), а не
        инвертирует, так что повторное событие не перевернёт отметку обратно.
        """
        if (
            self._selected_view is not None
            or self._selected_item is not None
            or self._editing_view is not None
        ):
            view.set_checked(view.item.is_checked)
            self.page.update()
            return
        target = not view.item.is_checked
        try:
            checked = await asyncio.to_thread(
                self.storage.set_item_checked, view.item.id, target
            )
        except Exception:
            logger.exception("Не удалось сохранить отметку пункта")
            self._show_message("Не удалось сохранить отметку")
            view.set_checked(view.item.is_checked)
            self.page.update()
            return
        view.set_checked(checked)
        self.page.update()

    def _append_category(
        self, category: domain.Category, items: Sequence[domain.Item] = ()
    ) -> CategoryView:
        view = CategoryView(
            category,
            items,
            gestures=self.gestures,
            category_gestures=self.category_gestures,
        )
        self.views.append(view)
        self.category_list.controls.append(view.item)
        return view

    def _remove_view(self, view: CategoryView) -> None:
        """Убирает категорию из списка в памяти и из списка элементов."""
        if view in self.views:
            self.views.remove(view)
        self.category_list.controls = [item.item for item in self.views]

    def _apply_category_order(self, ordered: list[domain.Category]) -> None:
        """Приводит список категорий в памяти к порядку, сохранённому в БД."""
        by_id = {item.category.id: item for item in self.views}
        self.views = [
            by_id[category.id] for category in ordered if category.id in by_id
        ]
        for category in ordered:
            view = by_id.get(category.id)
            if view is not None:
                view.category = category
        self.category_list.controls = [item.item for item in self.views]

    def _apply_item_orders(self, orders: dict[int, list[domain.Item]]) -> None:
        """Раскладывает пункты затронутых категорий по порядку из БД.

        После переноса пункта хранилище возвращает порядок прежней и новой
        категорий, и он — источник истины, как и у категорий. Строки пунктов не
        пересоздаются: они переезжают между контейнерами как есть (клиент
        сопоставляет контролы по идентификатору), поэтому отметки, размеры и
        выделение сохраняются.
        """
        by_id = {
            item_view.item.id: item_view
            for category in self.views
            for item_view in category.items
        }
        for category in self.views:
            ordered = orders.get(category.category.id)
            if ordered is None:
                continue
            item_views: list[ItemView] = []
            for item in ordered:
                item_view = by_id.get(item.id)
                if item_view is None:
                    continue
                item_view.item = item
                item_view.category_view = category
                item_views.append(item_view)
            category.items = item_views
            category.items_box.content.controls = [
                item_view.cell for item_view in item_views
            ]
            category._sync_items_box()

    def _show_message(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    # Выделение, тапы и кнопки button_area.

    def _select_category(self, view: CategoryView) -> None:
        """Выделяет категорию: другой цвет панели и состав кнопок.

        Выделение применяется идемпотентно: повторный вызов для уже выделенной
        категории всё равно отправляет изменения клиенту — начинающемуся
        перетаскиванию нужен свежий вид элемента. Выделенным может быть только
        один элемент, поэтому выделение с пункта снимается.
        """
        self._clear_item_selection()
        if view is not self._selected_view:
            if self._selected_view is not None:
                self._selected_view.set_selected(False)
            self._selected_view = view
            view.set_selected(True)
        self._apply_selection()
        self.page.update()

    def _select_item(self, view: ItemView) -> None:
        """Выделяет пункт: розовый фон строки и кнопки пункта.

        Розовый — тот же `ITEM_PANEL_SELECTED_COLOR`, что и у выделенной
        категории. Категория при этом не выделена: выделен всегда ровно один
        элемент, поэтому выделение с категории снимается.
        """
        if self._selected_view is not None:
            self._selected_view.set_selected(False)
            self._selected_view = None
        if view is not self._selected_item:
            self._clear_item_selection()
            self._selected_item = view
        view.set_selected(True)
        self._apply_selection()
        self.page.update()

    def _clear_item_selection(self) -> None:
        """Снимает выделение с пункта, если он выделен."""
        view = self._selected_item
        if view is None:
            return
        self._selected_item = None
        view.set_selected(False)

    def _deselect(self) -> None:
        """Снимает выделение с категории или пункта: выделен всегда один."""
        view = self._selected_view
        item_view = self._selected_item
        if view is None and item_view is None:
            return
        self._selected_view = None
        self._selected_item = None
        if view is not None:
            view.set_selected(False)
        if item_view is not None:
            item_view.set_selected(False)
        self._apply_selection()
        self.page.update()

    def _on_tap(self, event: ft.ControlEvent | None = None) -> None:
        """Тап по списку завершает ввод названия или снимает выделение.

        Тап, которым закрывают клавиатуру, выделение не снимает: ввод
        завершается, а выделенная категория остаётся выделенной (см.
        feature-category.md). Тот же тап приходит и вторым событием — тапом
        списка; его отсекает флаг `_tap_ended_input`, выставленный
        обработчиком `on_tap_outside` поля ввода.
        """
        # Тап возможен только когда перетаскивания уже нет. Если система
        # прервала жест, не прислав on_reorder_end, кнопки остались бы скрытыми.
        self._end_drag()
        if self._editing_view is not None:
            # Ввод закончится сохранением названия; выделение не трогаем.
            self._commit_editing()
            return
        if self._tap_ended_input:
            # Это тот же тап, что уже закрыл клавиатуру (on_tap_outside поля
            # приходит раньше on_tap списка): выделение остаётся.
            self._tap_ended_input = False
            return
        self._deselect()

    async def _on_item_tap(self, view: ItemView) -> None:
        """Тап по пункту: внутри выделенной категории он выделяет пункт.

        Тап по пункту в невыделенной категории — обычный тап по области списка:
        он снимает выделение. Тап, которым закрывают клавиатуру, выделение не
        снимает, а ввод названия — завершает.
        """
        # Тап возможен только когда перетаскивания уже нет. Если система
        # прервала жест, не прислав on_reorder_end, кнопки остались бы скрытыми.
        self._end_drag()
        if self._editing_view is not None:
            # Ввод закончится сохранением названия; выделение не трогаем.
            self._commit_editing()
            return
        if self._tap_ended_input:
            # Это тот же тап, что уже закрыл клавиатуру (on_tap_outside поля
            # приходит раньше события пункта): выделение остаётся.
            self._tap_ended_input = False
            return
        if (
            view.category_view is not None
            and view.category_view is self._selected_view
        ):
            self._select_item(view)
            if self.haptic is not None:
                await self.haptic.medium_impact()
            return
        self._deselect()

    def _on_tap_cancel(self, event: ft.ControlEvent | None = None) -> None:
        """Жест перестал быть тапом: флаг «этот тап закрыл клавиатуру» снят.

        Иначе, если тап вне поля превратится в прокрутку, флаг остался бы
        выставленным и съел следующий, уже обычный тап по списку.
        """
        self._tap_ended_input = False

    async def _on_confirm_pop(self, event: ft.ControlEvent) -> None:
        """Кнопка или жест «назад»: завершает ввод или снимает выделение.

        Приложение при этом не закрывается. «Назад» во время ввода названия
        сохраняет введённое название и оставляет выделение: по спеке ввод
        заканчивается и кнопкой «назад» (см. feature-category.md). Пока
        открыта клавиатура, первый «назад» обычно забирает Android; сюда он
        приходит, когда клавиатуры уже нет или её закрытие не отследилось.
        """
        view = self.page.views[-1]
        if self._editing_view is not None:
            await self._finish_title_input(self._editing_view)
            await view.confirm_pop(False)
            return
        selected = (
            self._selected_view is not None or self._selected_item is not None
        )
        if selected:
            self._deselect()
        await view.confirm_pop(not selected)

    def _actions(self) -> tuple[ButtonAction, ButtonAction, ButtonAction]:
        """Действия трёх слотов button_area для текущего выделения.

        Слоты постоянные (плюс, карандаш, корзина), иконки у категорий и
        пунктов совпадают, поэтому при смене выделения меняется действие
        каждого слота, а не набор кнопок (см. docs/Project.md).

        Без выделения виден только плюс — создание категории. При выделенной
        категории плюс добавляет пункт, а карандаш и корзина работают с этой
        категорией. При выделенном пункте плюс скрыт, а карандаш и корзина
        работают с пунктом.
        """
        if self._selected_item is not None:
            return (
                ButtonAction(LABEL_CREATE_CATEGORY, self.create_category, visible=False),
                ButtonAction(LABEL_RENAME_ITEM, self.rename_item),
                ButtonAction(LABEL_DELETE_ITEM, self.delete_item),
            )
        if self._selected_view is not None:
            return (
                ButtonAction(LABEL_ADD_ITEM, self.add_item),
                ButtonAction(LABEL_RENAME_CATEGORY, self.rename_category),
                ButtonAction(LABEL_DELETE_CATEGORY, self.delete_category),
            )
        return (
            ButtonAction(LABEL_CREATE_CATEGORY, self.create_category),
            ButtonAction(LABEL_RENAME_CATEGORY, self.rename_category, visible=False),
            ButtonAction(LABEL_DELETE_CATEGORY, self.delete_category, visible=False),
        )

    def _set_checkboxes_blocked(self, blocked: bool) -> None:
        """Запирает или отпускает чекбоксы всех пунктов.

        Отметку можно менять только когда ничего не выделено и не идёт ввод
        названия ([feature-item.md](features/feature-item.md)), поэтому в
        остальное время чекбоксы не должны реагировать на тап. Слой над
        чекбоксом прозрачный: внешний вид не меняется, в отличие от `disabled`.
        """
        for category in self.views:
            for item_view in category.items:
                item_view.set_checkbox_blocked(blocked)

    def _apply_selection(self) -> None:
        """Показывает действия, подходящие текущему выделению и вводу."""
        selected = self._selected_view is not None or self._selected_item is not None
        editing = self._editing_view is not None
        for button, action in zip(
            (self.plus_button, self.pencil_button, self.trash_button),
            self._actions(),
            strict=True,
        ):
            bind_button(button, action)
        # Пока что-то выделено или идёт ввод, чекбоксы не реагируют на тап: иначе
        # клиент на мгновение нарисовал бы переключение, а сервер его откатил.
        self._set_checkboxes_blocked(selected or editing)
        # Пока идёт ввод названия или перетаскивание (категории или пункта),
        # контейнер скрыт целиком (см. feature-button-area.md): кнопки не
        # должны заслонять список в момент, когда по нему ведут пальцем.
        self.button_area.visible = (
            not editing and not self._dragging and self._item_drag is None
        )
        # Пока категория или пункт выделены или идёт ввод названия, «назад»
        # перехватывается вместо закрытия приложения: он снимает выделение
        # либо завершает ввод (см. _on_confirm_pop).
        self.page.views[0].can_pop = not selected and not editing

    # Перетаскивание: общее для категории и пункта.

    def _end_drag(self) -> None:
        """Снимает любое перетаскивание: категории или пункта.

        Нужен как страховка на случай, когда система прервала жест и событие
        об отпускании не пришло: иначе кнопки остались бы скрытыми, а прокси
        перетаскивания — висеть поверх списка.
        """
        if (
            not self._dragging
            and self._item_drag is None
            and self._category_drag is None
        ):
            return
        self._dragging = False
        self._finish_item_drag()
        self._finish_category_drag()
        self._apply_selection()
        self.page.update()

    def _active_drag(self) -> ItemDrag | CategoryDrag | None:
        """Текущее перетаскивание: категории или пункта (одно за раз)."""
        return self._item_drag or self._category_drag

    def _finish_active_drag(self) -> None:
        """Завершает текущее перетаскивание без записи порядка."""
        if self._item_drag is not None:
            self._finish_item_drag()
        elif self._category_drag is not None:
            self._finish_category_drag()

    def _refresh_target(self, drag: ItemDrag | CategoryDrag) -> bool:
        """Пересчитывает место вставки после прокрутки списка."""
        if isinstance(drag, CategoryDrag):
            return self._update_category_target(drag)
        return self._update_drag_target(drag)

    def _item_metrics(self) -> list[tuple[float, list[float]]]:
        """Высоты строк: измеренные, а для невидимых строк — оценка.

        Клиент присылает `size_change` только для того, что реально разложено:
        строки за пределами видимой области размеров не имеют, пока не попадут
        в неё. Измеренные высоты берутся как есть, остальные оцениваются по
        среднему измеренному (или по шаблону, если измерений нет вовсе). На
        место вставки под пальцем это не влияет: строки рядом с пальцем видны и
        измерены, а оценка нужна только невидимым строкам ниже или выше экрана.
        """
        measured_items = [
            item_view.height
            for category in self.views
            for item_view in category.items
            if item_view.height is not None
        ]
        item_height = (
            sum(measured_items) / len(measured_items)
            if measured_items
            else ITEM_ROW_HEIGHT_FALLBACK
        )
        measured_titles = [
            category.title_height
            for category in self.views
            if category.title_height is not None
        ]
        title_height = (
            sum(measured_titles) / len(measured_titles)
            if measured_titles
            else CATEGORY_TITLE_HEIGHT_FALLBACK
        )
        return [
            (
                category.title_height
                if category.title_height is not None
                else title_height,
                [
                    item_view.height
                    if item_view.height is not None
                    else item_height
                    for item_view in category.items
                ],
            )
            for category in self.views
        ]

    # Перетаскивание категории: свой жест, прокси, зазор и автопрокрутка.
    #
    # Перетаскивание начинается только у выделенной категории: долгое нажатие
    # сначала выделяет её (палец отпускается), и лишь второе нажатие по ней же
    # поднимает панель. Так случайное долгое нажатие не двигает список.
    #
    # Штатный ReorderableListView автопрокручивает список, когда край экрана
    # касается любая часть перетаскиваемой категории (у него `_dragTargetRect` —
    # весь элемент). У длинной категории этот прямоугольник выходит за край
    # сразу, поэтому список начинал ехать в первый же миг перетаскивания. Здесь
    # зона автопрокрутки считается по полосе названия (`CategoryDrag.title_span`),
    # а порядок сохраняется по отпусканию, как и у пункта.

    async def _on_category_long_press(self, view: CategoryView) -> None:
        """Долгое нажатие на панели: выделение и виброотклик.

        Виброотклик даётся на каждое долгое нажатие: первое выделяет категорию,
        второе по ней же поднимает её для перетаскивания — пользователь должен
        почувствовать оба. Пока идёт ввод названия, выделение не меняется:
        долгое нажатие в поле — это работа с текстом.
        """
        if self._editing_view is not None:
            return
        self._select_category(view)
        if self.haptic is not None:
            await self.haptic.medium_impact()

    def _on_category_drag_start(
        self, view: CategoryView, event: ft.LongPressStartEvent
    ) -> None:
        """Категория «поднимается»: панель сворачивается, над списком — прокси.

        Поднимается только **выделенная** категория: перетаскивание начинается
        вторым долгим нажатием, после того как первое выделило категорию и палец
        был отпущен. Событие приходит до `on_long_press` этого жеста, поэтому
        здесь видно выделение, оставшееся от прошлого жеста, а не текущее.
        Размеры панели приходят от клиента (`size_change`): без них не из чего
        построить ни прокси, ни зазор, поэтому долгое нажатие просто выделяет
        категорию.
        """
        if (
            self._editing_view is not None
            or self._item_drag is not None
            or self._category_drag is not None
        ):
            return
        if view is not self._selected_view:
            return
        global_position = event.global_position
        local_position = event.local_position
        if global_position is None or local_position is None:
            return
        if view not in self.views:
            return
        if view.height is None or view.width is None:
            return
        index = self.views.index(view)
        # Точка нажатия приходит в координатах панели: прокси встаёт по её верху.
        grab_y = local_position.y
        drag = CategoryDrag(
            view=view,
            source=index,
            height=view.height,
            width=view.width,
            title_height=view.title_height or CATEGORY_TITLE_HEIGHT_FALLBACK,
            origin_y=global_position.y
            - grab_y
            - category_base_top(self._category_slot_heights(), index)
            + self._scroll_pixels,
            grab_y=grab_y,
            start_y=global_position.y,
            target=index,
        )
        self._category_drag = drag
        self._pointer_y = global_position.y
        # Пока категория перетаскивается, кнопки скрыты целиком.
        self._dragging = True
        # Драгу нужна частая позиция прокрутки: по ней пересчитывается место
        # вставки и продолжается проход автопрокрутки.
        self._set_scroll_interval(SCROLL_INTERVAL_DRAG)
        view.collapse()
        drag.proxy = create_category_proxy(view, drag.width)
        # Категория едет в своём столбце: прокси встаёт ровно над списком
        # (у содержимого списка отступ `LIST_PADDING`) и по горизонтали не
        # двигается — как и панель, которую вёл клиент.
        drag.proxy.left = LIST_PADDING
        self.stack.controls.append(drag.proxy)
        self._place_category_gap(drag)
        self._move_category_proxy(drag, global_position.y)
        self._apply_selection()
        self.page.update()

    def _on_category_drag_move(
        self, view: CategoryView, event: ft.LongPressMoveUpdateEvent
    ) -> None:
        """Палец движется: прокси идёт за ним, зазор переезжает на новую цель.

        Экран обновляется только в сдвинувшихся местах (`_flush_drag`): полный
        патч страницы на каждое событие движения не успевал за пальцем.
        """
        drag = self._category_drag
        if drag is None or drag.view is not view:
            return
        self._pointer_y = event.global_position.y
        self._move_category_proxy(drag, self._pointer_y)
        self._update_category_target(drag)
        self._update_autoscroll(drag)
        self._flush_drag(drag)

    async def _on_category_drag_end(
        self, view: CategoryView, event: ft.LongPressEndEvent
    ) -> None:
        """Палец отпущен: категория встаёт на новое место, порядок пишется в БД.

        Запись — до обновления списка: при ошибке порядок в памяти и на экране
        остаётся прежним, показывается сообщение (как у остальных операций).
        Порядок из БД — источник истины: им обновляются позиции.
        """
        drag = self._category_drag
        if drag is None or drag.view is not view:
            self._end_drag()
            return
        if event.global_position is not None:
            # Точка отпускания уточняет цель: последнее движение могло прийти
            # раньше, чем палец остановился.
            self._pointer_y = event.global_position.y
            self._update_category_target(drag)
        target = drag.target
        self._finish_category_drag()
        if target == drag.source:
            self.page.update()
            return
        try:
            ordered = await asyncio.to_thread(
                self.storage.move_category, view.category.id, target
            )
        except Exception:
            logger.exception("Не удалось сохранить порядок категорий")
            self._show_message("Не удалось сохранить порядок категорий")
            self.page.update()
            return
        self._apply_category_order(ordered)
        self.page.update()

    def _on_category_drag_cancel(self, view: CategoryView) -> None:
        """Жест отменён: прокси и зазор убираются, порядок не меняется."""
        drag = self._category_drag
        if drag is None or drag.view is not view:
            return
        self._finish_category_drag()
        self.page.update()

    def _finish_category_drag(self) -> None:
        """Возвращает список в обычный вид после перетаскивания категории.

        Прокси убирается со стека, зазор — из отступов элементов списка, панель
        снова получает свою высоту, а начатая автопрокрутка останавливается.
        """
        drag = self._category_drag
        if drag is None:
            return
        self._category_drag = None
        # Проход по краю списка мог ещё идти: отменяем его, иначе список
        # продолжал бы ехать после отпускания категории.
        drag.epoch += 1
        if drag.autoscroll:
            drag.autoscroll = 0
            self.page.run_task(self._cancel_scroll)
        if drag.proxy is not None:
            for position, control in enumerate(self.stack.controls):
                if control is drag.proxy:
                    self.stack.controls.pop(position)
                    break
        self._clear_category_gap()
        drag.view.restore()
        # В покое позиция прокрутки нужна редко: события не должны отнимать
        # кадры у инерционной прокрутки.
        self._set_scroll_interval(SCROLL_INTERVAL_IDLE)
        self._dragging = False
        self._apply_selection()
        # Всё сдвинувшееся покажет полный `page.update()` вызывающего: копить
        # его в списке точечных обновлений незачем.
        self._drag_controls.clear()

    def _category_slot_heights(self) -> list[float]:
        """Высоты слотов категорий: панель вместе с промежутком до следующей.

        Берётся измеренная панель, а если клиент её ещё не присылал (категория
        за пределами видимой области) — высота по шаблону.
        """
        heights: list[float] = []
        for view, (title_height, row_heights) in zip(
            self.views, self._item_metrics(), strict=True
        ):
            panel_height = (
                view.height
                if view.height is not None
                else category_panel_height(title_height, row_heights)
            )
            heights.append(panel_height + CATEGORY_SPACING)
        return heights

    def _category_spans(self, drag: CategoryDrag) -> list[CategorySpan]:
        """Раскладка списка при текущем месте зазора."""
        return build_category_spans(
            self._category_slot_heights(),
            dragged=drag.source,
            target=drag.target,
        )

    def _update_category_target(self, drag: CategoryDrag) -> bool:
        """Пересчитывает место вставки по текущей точке пальца.

        ``True`` — цель изменилась и зазор переехал.
        """
        if self._pointer_y is None or drag.source >= len(self.views):
            return False
        target = category_span_at(
            self._category_spans(drag),
            self._model_y(drag, self._pointer_y),
        )
        if target == drag.target:
            return False
        drag.target = target
        self._place_category_gap(drag)
        return True

    def _place_category_gap(self, drag: CategoryDrag) -> None:
        """Ставит зазор на место вставки: отступом соседнего элемента списка.

        Зазор — `margin` того элемента, перед которым категория встанет (или
        нижний отступ последнего из оставшихся, если место — конец списка). Так
        список остаётся прежним: элементы не переставляются и не пересоздаются.
        Высота зазора — целый слот категории, поэтому остальные панели не
        сдвигаются.

        Отступ никогда не ставится элементу **поднятой** категории: клиент
        применяет `margin` к контейнеру, пересоздавая его поддерево, — вместе с
        ним пропадает распознаватель жеста, и перетаскивание обрывается на
        первом же обновлении экрана. Панель тогда замирает на месте, а
        отпускание пальца до приложения не доходит: выйти из drag можно только
        тапом, снимающим выделение. Поэтому место в конце списка отдаётся
        нижним отступом предыдущей категории — свёрнутая панель места не
        занимает, и раскладка от такой замены не меняется (проверено на
        устройстве).
        """
        position = drag.target if drag.target < drag.source else drag.target + 1
        control: ft.Control | None = None
        if position < len(self.views):
            control = self.views[position].item
            margin = ft.Margin.only(top=drag.slot_height)
        else:
            for view in reversed(self.views):
                if view is not drag.view:
                    control = view.item
                    margin = ft.Margin.only(bottom=drag.slot_height)
                    break
        if control is not self._category_gap_control:
            self._clear_category_gap()
        if control is None:
            return
        # У последней оставшейся панели зазор может перейти на другой край
        # той же обёртки. В этом случае достаточно одного точечного патча.
        control.margin = margin
        self._category_gap_control = control
        self._drag_controls.append(control)

    def _clear_category_gap(self) -> None:
        """Снимает зазор с элемента списка, который его держал."""
        control = self._category_gap_control
        if control is None:
            return
        control.margin = None
        self._category_gap_control = None
        self._drag_controls.append(control)

    def _move_category_proxy(self, drag: CategoryDrag, pointer_y: float) -> None:
        """Двигает прокси категории за пальцем — только по вертикали."""
        if drag.proxy is None:
            return
        drag.panel_top = pointer_y - drag.grab_y
        drag.proxy.top = drag.panel_top - drag.origin_y

    # Перетаскивание пункта: прокси, зазор и место вставки.

    async def _on_item_long_press(self, view: ItemView) -> None:
        """Долгое нажатие по пункту: пункт выделяется и даёт виброотклик.

        Долгое нажатие перехватывает пункт, а не список: иначе оно начинало бы
        перетаскивание категории (см. `create_item_row`). Пока идёт ввод
        названия, выделение не меняется — как и при тапе, которым закрывают
        клавиатуру.

        Событие приходит после `on_long_press_start` этого же жеста: первое
        нажатие только выделяет пункт, а подъём начался, если пункт был выделен
        раньше (снимается лишь застрявшее перетаскивание категории).
        """
        self._finish_category_drag()
        if self._editing_view is not None:
            return
        self._select_item(view)
        if self.haptic is not None:
            await self.haptic.medium_impact()

    def _on_item_drag_start(
        self, view: ItemView, event: ft.LongPressStartEvent
    ) -> None:
        """Долгое нажатие принято: пункт «поднимается» и готов к перетаскиванию.

        Поднимается только **выделенный** пункт: перетаскивание начинается
        вторым долгим нажатием, после того как первое выделило пункт и палец был
        отпущен. Событие приходит до `on_long_press` этого жеста, поэтому здесь
        видно выделение, оставшееся от прошлого жеста. Дальше этот жест даёт
        `on_long_press_move_update`, а отпускание — `on_long_press_end`.

        Размеры строк приходят от клиента (`size_change`). Без размера самой
        нажатой строки перетаскивание не начинается: её нечем свернуть и не из
        чего построить прокси, поэтому долгое нажатие просто выделяет пункт.
        """
        if (
            self._editing_view is not None
            or self._item_drag is not None
            or self._category_drag is not None
        ):
            return
        if view is not self._selected_item:
            return
        source = view.category_view
        global_position = event.global_position
        local_position = event.local_position
        if source is None or global_position is None or local_position is None:
            return
        if view.height is None or view.width is None:
            return
        if source not in self.views or view not in source.items:
            return
        metrics = self._item_metrics()
        category_index = self.views.index(source)
        source_index = source.items.index(view)
        # Экранный верх содержимого списка: от него считаются и модель, и
        # положение прокси (Stack лежит ровно над областью списка). Точка
        # нажатия внутри строки плюс её верх в модели дают этот верх.
        drag = ItemDrag(
            view=view,
            source=(category_index, source_index),
            height=view.height,
            origin_y=global_position.y
            - local_position.y
            - base_row_top(metrics, category_index, source_index)
            + self._scroll_pixels,
            grab_y=local_position.y,
            start_y=global_position.y,
            target=(category_index, source_index),
        )
        self._item_drag = drag
        self._pointer_y = global_position.y
        # Пока идёт drag, позиция прокрутки нужна часто (см. _on_scroll).
        self._set_scroll_interval(SCROLL_INTERVAL_DRAG)
        # Строка сворачивается, а на её место встают зазор и прокси. Зазор
        # занимает целый слот строки, поэтому пункты не сдвигаются.
        view.collapse()
        drag.gap = create_item_gap(item_slot_height(drag.height))
        self._place_gap(drag, drag.target)
        drag.proxy = create_item_proxy(view)
        # Пункт едет в своём столбце: прокси встаёт ровно над строкой списка
        # (у содержимого списка отступ `LIST_PADDING`) и по горизонтали не
        # двигается — как панель категории, которую клиент ведёт только вдоль
        # оси списка.
        drag.proxy.left = LIST_PADDING
        self.stack.controls.append(drag.proxy)
        self._move_proxy(drag, global_position.y)
        # Кнопки прячутся сразу, не дожидаясь события выделения: порядок двух
        # событий долгого нажатия задаёт клиент, а drag уже начался.
        self._apply_selection()
        self.page.update()

    def _on_item_drag_move(
        self, view: ItemView, event: ft.LongPressMoveUpdateEvent
    ) -> None:
        """Палец движется: прокси идёт за ним, зазор переезжает на новую цель.

        Раскладка пересчитывается через текущее положение зазора, поэтому
        перестановка начинается, когда палец проходит середину соседней
        строки, — как и при перетаскивании категории. Порог и цель считаются по
        вертикальному сдвигу: движение вбок пункт не переставляет и прокси не
        сдвигает. Экран обновляется только в сдвинувшихся местах
        (`_flush_drag`): полный патч страницы не успевал за пальцем.
        """
        drag = self._item_drag
        if drag is None or drag.view is not view:
            return
        self._pointer_y = event.global_position.y
        if not drag.moved:
            if abs(self._pointer_y - drag.start_y) < ITEM_DRAG_THRESHOLD:
                return
            drag.moved = True
        self._move_proxy(drag, self._pointer_y)
        self._update_drag_target(drag)
        self._update_autoscroll(drag)
        self._flush_drag(drag)

    async def _on_item_drag_end(
        self, view: ItemView, event: ft.LongPressEndEvent
    ) -> None:
        """Палец отпущен: пункт встаёт на новое место, порядок пишется в БД.

        Запись — до обновления списка: при ошибке порядок в памяти и на экране
        остаётся прежним, показывается сообщение (как у остальных операций).
        Порядок из БД применяется к пунктам прежней и новой категории, поэтому
        перенос в другую категорию ничем не отличается от перестановки внутри
        своей. Выделение переживает перетаскивание, как и у категории.
        """
        drag = self._item_drag
        if drag is None or drag.view is not view:
            self._end_drag()
            return
        if drag.moved and event.global_position is not None:
            # Точка отпускания уточняет цель: последнее движение могло прийти
            # раньше, чем палец остановился.
            self._pointer_y = event.global_position.y
            self._update_drag_target(drag)
        target = drag.target
        self._finish_item_drag()
        source = view.category_view
        if not drag.moved or source is None:
            # Жест без движения: это было выделение, а не перетаскивание.
            self.page.update()
            return
        target_category = self.views[target[0]]
        if target_category is source and target[1] == drag.source[1]:
            self.page.update()
            return
        try:
            orders = await asyncio.to_thread(
                self.storage.move_item,
                view.item.id,
                target_category.category.id,
                target[1],
            )
        except Exception:
            logger.exception("Не удалось переместить пункт")
            self._show_message("Не удалось переместить пункт")
            self.page.update()
            return
        self._apply_item_orders(orders)
        self.page.update()

    def _on_item_drag_cancel(self, view: ItemView) -> None:
        """Жест отменён: прокси и зазор убираются, порядок не меняется."""
        drag = self._item_drag
        if drag is None or drag.view is not view:
            return
        self._finish_item_drag()
        self.page.update()

    def _finish_item_drag(self) -> None:
        """Возвращает список в обычный вид после перетаскивания пункта.

        Прокси убирается со стека, зазор — из контейнера пунктов, свёрнутая
        строка снова получает свою высоту, а начатая автопрокрутка
        останавливается. Порядок пунктов на этом шаге не меняется: его применяет
        вызывающий по данным хранилища.
        """
        drag = self._item_drag
        if drag is None:
            return
        self._item_drag = None
        # Проход по краю списка мог ещё идти: отменяем его, иначе список
        # продолжал бы ехать после отпускания пункта.
        drag.epoch += 1
        if drag.autoscroll:
            drag.autoscroll = 0
            self.page.run_task(self._cancel_scroll)
        if drag.proxy is not None:
            for position, control in enumerate(self.stack.controls):
                if control is drag.proxy:
                    self.stack.controls.pop(position)
                    break
        self._drop_gap()
        drag.view.restore()
        # В покое позиция прокрутки нужна редко: события не должны отнимать
        # кадры у инерционной прокрутки.
        self._set_scroll_interval(SCROLL_INTERVAL_IDLE)
        self._apply_selection()
        # Всё сдвинувшееся покажет полный `page.update()` вызывающего.
        self._drag_controls.clear()

    def _place_gap(self, drag: ItemDrag, target: tuple[int, int]) -> None:
        """Ставит зазор на место вставки; прежняя категория его теряет.

        Высота зазора — целый слот пункта, она одна и та же в любой категории:
        свёрнутая строка теперь не занимает места вовсе (её ячейка сворачивается
        вместе со строкой), поэтому остатка на месте пункта не остаётся — ни в
        своей категории, ни в чужой.
        """
        if drag.gap is None:
            return
        category = self.views[target[0]]
        if self._gap_category is not None and self._gap_category is not category:
            self._gap_category.remove_gap()
            self._drag_controls.append(self._gap_category.item)
        category.place_gap(drag.gap, target[1], drag.view)
        self._drag_controls.append(category.item)
        self._gap_category = category

    def _drop_gap(self) -> None:
        """Убирает зазор из списка."""
        if self._gap_category is not None:
            self._gap_category.remove_gap()
            self._gap_category = None

    def _model_y(self, drag: ItemDrag, pointer_y: float) -> float:
        """Координата модели под пальцем с учётом прокрутки списка."""
        return pointer_y - drag.origin_y + self._scroll_pixels

    def _move_proxy(self, drag: ItemDrag, pointer_y: float) -> None:
        """Двигает прокси строки за пальцем — только по вертикали.

        По горизонтали пункт не едет: в списке он живёт в одном столбце, и
        переставлять его вбок некуда. Так же ведёт себя категория — клиент
        двигает её только вдоль оси списка, и копия пункта должна выглядеть
        так же. Поэтому здесь меняется только ``top``, а ``left`` выставлен при
        подъёме.
        """
        if drag.proxy is None:
            return
        drag.proxy.top = pointer_y - drag.origin_y - drag.grab_y

    def _update_drag_target(self, drag: ItemDrag) -> bool:
        """Пересчитывает место вставки по текущей точке пальца.

        ``True`` — цель изменилась и зазор переехал: экран нужно обновить.
        Раскладка строится от текущего зазора, поэтому палец сравнивается с
        серединами строк так, как они видны на экране. Высоты берутся заново:
        пока шла прокрутка, строки попадали в видимую область и измерялись.
        """
        if not drag.moved or self._pointer_y is None:
            return False
        spans = build_drag_spans(
            self._item_metrics(),
            source=drag.source,
            height=drag.height,
            target=drag.target,
        )
        category_index, insert_index = drag_slot_at(
            spans, self._model_y(drag, self._pointer_y)
        )
        if category_index >= len(self.views):
            return False
        if (category_index, insert_index) == drag.target:
            return False
        drag.target = (category_index, insert_index)
        self._place_gap(drag, drag.target)
        return True

    # Показ сдвинувшегося при перетаскивании: только изменённые контролы.

    def _flush_drag(self, drag: ItemDrag | CategoryDrag) -> None:
        """Показывает на экране прокси и зазор после движения пальца.

        `page.update()` без аргументов патчит всю страницу: сервер сравнивает
        с прошлым показом **всё** дерево контролов. Список собран целиком
        (`build_controls_on_demand=False`), поэтому на 40 категориях по 5
        пунктов один такой вызов на телефоне занимает ≈45 мс — а движение
        пальца приходит 120 раз в секунду. Прокси тогда догонял палец рывками
        по нескольку событий сразу: `page.update()` не успевал за жестом.

        Поэтому в движении патчатся только сдвинувшиеся контролы: прокси и то,
        что переставил зазор. Их поддеревья — десятки контролов, а не всё
        дерево страницы: ≈2 мс вместо 45. Полное обновление остаётся там, где
        меняется структура экрана: начало и конец перетаскивания (прокси
        появляется в `Stack` и исчезает из него).
        """
        controls = list(self._drag_controls)
        self._drag_controls.clear()
        if drag.proxy is not None:
            controls.insert(0, drag.proxy)
        if controls:
            self.page.update(*controls)

    def _flush_gap(self) -> None:
        """Показывает только новый зазор: прокси при автопрокрутке не едет.

        Автопрокрутка двигает содержимое под неподвижным пальцем: прокси стоит
        на месте, а зазор переезжает на новую строку. Патч одного-двух
        контролов вместо всей страницы — см. `_flush_drag`.
        """
        controls = list(self._drag_controls)
        self._drag_controls.clear()
        if controls:
            self.page.update(*controls)

    # Прокрутка и автопрокрутка у краёв экрана.

    def _set_scroll_interval(self, interval: int) -> None:
        """Меняет частоту событий прокрутки: редкую в покое, частую в drag.

        Каждое событие `on_scroll` клиент отправляет в Python, и на обычной
        прокрутке — особенно инерционной, когда палец уже отпущен, — эти
        сообщения только отнимают кадры у анимации. Позиция списка нужна лишь
        к началу перетаскивания и во время него, поэтому в покое события
        приходят редко (`SCROLL_INTERVAL_IDLE`), а пока идёт drag — часто
        (`SCROLL_INTERVAL_DRAG`): по ним пересчитывается место вставки и
        продолжается проход автопрокрутки.

        Новое значение уходит клиенту ближайшим `page.update()` — тем же, что
        показывает прокси и скрывает кнопки, — поэтому отдельных обновлений
        экрана правка не добавляет.
        """
        if interval == self._scroll_interval:
            return
        self._scroll_interval = interval
        self.category_list.scroll_interval = interval

    def _on_scroll(self, event: ft.OnScrollEvent) -> None:
        """Список прокрутился: место вставки пересчитывается под пальцем.

        Автопрокрутка двигает содержимое, а палец стоит на месте, поэтому
        координата модели под ним меняется — зазор переезжает вместе с ней.
        Прокси двигать не нужно: он привязан к пальцу.

        Прокрутку ведёт клиент, так что событие — единственный способ узнать,
        где сейчас содержимое и докуда оно может ехать. По концу прохода
        прокрутка продолжается, только если список за проход стал выше: зазор
        переезжает, и конец списка уезжает вниз.

        Прокрутка пользователя (событие `user`) означает, что перетаскивание
        пункта уже кончилось: пока жест жив, список двигает только
        автопрокрутка. Так выходит, если система оборвала жест, не прислав
        отпускания — например, строка ушла из списка вместе с распознавателем.
        Тогда перетаскивание снимается: иначе прокси висел бы поверх списка, а
        автопрокрутка возвращала бы список к краю, за который его уводит палец.
        """
        delta = event.pixels - self._scroll_pixels
        self._scroll_pixels = event.pixels
        self._viewport = event.viewport_dimension
        if math.isfinite(event.max_scroll_extent):
            # У безгранично прокручиваемого списка тут бесконечность: она
            # сломала бы расчёт длительности прохода.
            self._max_scroll_extent = event.max_scroll_extent
        drag = self._active_drag()
        if drag is None:
            return
        if event.event_type == ft.ScrollType.START:
            # Размеры на начало прохода: с ними сравнивается конец прохода.
            drag.pass_extent = event.max_scroll_extent
        elif event.event_type == ft.ScrollType.USER:
            # Список поехал от пальца — жест перетаскивания потерян.
            drag.autoscroll = 0
            self._finish_active_drag()
            self.page.update()
            return
        if delta and self._refresh_target(drag):
            # Прокси при автопрокрутке стоит под пальцем: патчится только зазор.
            self._flush_gap()
        if event.event_type == ft.ScrollType.END and drag.autoscroll > 0:
            # Продолжение — только если конец списка уехал вниз: остаток «до
            # края» для этого не годится, он положителен и тогда, когда список
            # отъехал от края сам.
            grown = (
                drag.pass_extent is not None
                and event.max_scroll_extent
                > drag.pass_extent + AUTOSCROLL_EXTENT_EPS
            )
            drag.pass_extent = event.max_scroll_extent
            if grown:
                self.page.run_task(self._scroll_to_edge, drag, drag.epoch)

    def _autoscroll_span(
        self, drag: ItemDrag | CategoryDrag
    ) -> tuple[float, float] | None:
        """Полоса, которую автопрокрутка сравнивает с краями экрана.

        У пункта это сам палец, у категории — область названия поднятой панели:
        категория «касается» края только названием, а не любым своим пунктом.
        Иначе длинная категория, чей низ уходит за экран, начинала бы прокрутку
        в первый же миг перетаскивания.
        """
        if isinstance(drag, CategoryDrag):
            return drag.title_span()
        if self._pointer_y is None:
            return None
        return self._pointer_y, self._pointer_y

    def _autoscroll_direction(self, drag: ItemDrag | CategoryDrag) -> int:
        """Куда прокручивать список: -1 вверх, 1 вниз, 0 — не надо.

        Зона — `AUTOSCROLL_EDGE` у верхней и нижней границы видимой области
        списка: содержимое уезжает под пальцем, поэтому до невидимой категории
        можно добраться, не отпуская пункт. Пока прокрутка идёт, зона шире на
        `AUTOSCROLL_HYSTERESIS`: палец, стоящий на самой границе зоны, не должен
        выключать и снова включать её дрожанием в пиксель.
        """
        span = self._autoscroll_span(drag)
        if span is None:
            return 0
        edge = AUTOSCROLL_EDGE + (AUTOSCROLL_HYSTERESIS if drag.autoscroll else 0)
        top = drag.origin_y
        bottom = top + self._list_viewport(drag)
        if span[0] < top + edge:
            return -1
        if span[1] > bottom - edge:
            return 1
        return 0

    def _list_viewport(self, drag: ItemDrag | CategoryDrag) -> float:
        """Высота видимой области списка в логических пикселях.

        После первой прокрутки её присылает клиент (`on_scroll`), до этого она
        оценивается по размеру окна за вычетом отступов представления и
        системной навигации. Оценка нужна только для зоны автопрокрутки:
        ошибка в несколько пикселей ей не мешает.
        """
        if self._viewport:
            return self._viewport
        height = self.page.height or 0
        media = self.page.media
        bottom_padding = (media.padding.bottom if media else 0) or 0
        view = self.page.views[0] if self.page.views else None
        view_padding = getattr(view, "padding", None)
        view_bottom = getattr(view_padding, "bottom", 0) or 0
        return max(height - bottom_padding - view_bottom - drag.origin_y, 0)

    def _update_autoscroll(self, drag: ItemDrag | CategoryDrag) -> None:
        """Включает, выключает или разворачивает автопрокрутку.

        Саму прокрутку выполняет клиент: ему заказывается один анимированный
        проход до края списка. Поэтому позиция идёт его кадрами, а не рывками из
        Python. Раньше шаг 12 px заказывался раз в 40 мс, и каждый заказ ждал
        ответа клиента: позиция менялась ~25 раз в секунду, а неравномерность
        ответов добавляла рывки — прокрутка получалась дёрганой.
        """
        direction = self._autoscroll_direction(drag)
        if direction == drag.autoscroll:
            return
        was = drag.autoscroll
        drag.autoscroll = direction
        # Прошлый проход отменяется: его задача проверит номер и выйдет, а
        # анимацию в клиенте останавливает `_cancel_scroll`.
        drag.epoch += 1
        if was:
            self.page.run_task(self._cancel_scroll)
        if direction:
            self.page.run_task(self._scroll_to_edge, drag, drag.epoch)

    async def _scroll_to_edge(
        self, drag: ItemDrag | CategoryDrag, epoch: int
    ) -> None:
        """Анимированный проход списка до края, к которому ведёт палец.

        Длительность считается по оставшемуся пути, поэтому скорость одна и та
        же при любой длине списка, а край — точная цель: клиент берёт его сам
        (`offset=-1` — конец, `0` — начало) уже в момент прокрутки. Поэтому
        список никогда не уезжает за край и не пружинит обратно: раньше именно
        эти пружины (каждый шаг заказывался «на 12 px», в том числе когда
        прокручивать было уже некуда) и давали дёрганье у границы списка.
        """
        if (
            self._active_drag() is not drag
            or drag.epoch != epoch
            or not drag.autoscroll
        ):
            return
        distance = self._autoscroll_distance(drag)
        if distance <= AUTOSCROLL_REST:
            # Список уже у края: заказывать нечего, и повторять запросы нельзя —
            # каждый уход за край клиент возвращает пружиной.
            return
        # Докуда список мог прокрутиться вниз перед проходом: по этой величине
        # видно, вырос ли он за проход (см. _on_scroll).
        drag.pass_extent = self._max_scroll_extent
        await self.category_list.scroll_to(
            offset=-1.0 if drag.autoscroll > 0 else 0.0,
            duration=round(distance / AUTOSCROLL_SPEED * 1000),
            curve=ft.AnimationCurve.EASE,
        )

    async def _cancel_scroll(self) -> None:
        """Останавливает анимированную прокрутку там, где список стоит сейчас."""
        await self.category_list.scroll_to(delta=0)

    def _autoscroll_distance(self, drag: ItemDrag | CategoryDrag) -> float:
        """Сколько ещё можно прокрутить в сторону пальца, в пикселях.

        Нужна только для длительности прохода: цель у клиента абсолютная (край
        списка), поэтому ошибка в оценке меняет лишь скорость, а уехать за край
        она не даёт. Вверх остаток точный — это сама прокрутка (начало списка —
        нуль). Вниз берётся большее из измеренного (`on_scroll`) и оценённого по
        раскладке: измеренное могло устареть, если список вырос без прокрутки, а
        оценка — ошибиться на несколько пикселей, и остановиться раньше края
        хуже, чем заказать лишний проход в уже достигнутый край.
        """
        if drag.autoscroll > 0:
            measured = (
                self._max_scroll_extent - self._scroll_pixels
                if self._max_scroll_extent is not None
                else 0.0
            )
            estimated = (
                self._content_height(drag)
                - self._list_viewport(drag)
                - self._scroll_pixels
            )
            return max(measured, estimated, 0.0)
        return max(self._scroll_pixels, 0.0)

    def _content_height(self, drag: ItemDrag | CategoryDrag) -> float:
        """Высота содержимого списка по раскладке перетаскивания.

        Панели категорий не измеряются, но раскладка повторяет шаблон панели,
        так что низ последней категории вместе с нижним отступом списка — это
        почти точная высота содержимого.
        """
        if isinstance(drag, CategoryDrag):
            return self._category_spans(drag)[-1].bottom + LIST_BOTTOM_PADDING
        spans = build_drag_spans(
            self._item_metrics(),
            source=drag.source,
            height=drag.height,
            target=drag.target,
        )
        if not spans:
            return 0.0
        return spans[-1].bottom + LIST_BOTTOM_PADDING
