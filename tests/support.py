"""Общие фейки и помощники тестов: страница, хранилище, события жестов."""

import asyncio

import flet as ft

import domain
import storage
from ui import theme
from ui.actions import ButtonAction
from ui.app import ChecklistApp
from ui.geometry import category_panel_height


def default_actions():
    """Действия слотов, когда ничего не выделено: виден только плюс."""
    return [
        ButtonAction(theme.LABEL_CREATE_CATEGORY),
        ButtonAction(theme.LABEL_RENAME_CATEGORY, visible=False),
        ButtonAction(theme.LABEL_DELETE_CATEGORY, visible=False),
    ]


def media(*, bottom_padding=16.0, bottom_inset=0.0, pixel_ratio=3.5):
    return ft.PageMediaData(
        padding=ft.Padding.only(bottom=bottom_padding),
        view_padding=ft.Padding.only(bottom=bottom_padding),
        view_insets=ft.Padding.only(bottom=bottom_inset),
        device_pixel_ratio=pixel_ratio,
        orientation=ft.Orientation.PORTRAIT,
    )


class FakeView:
    """Корневое представление страницы: перехват «назад» (PopScope)."""

    def __init__(self):
        self.can_pop = True
        self.pops = []

    async def confirm_pop(self, should_pop):
        self.pops.append(should_pop)


class FakePage:
    def __init__(self):
        self.tasks = []
        self.updates = 0
        # Клиентских данных о системе ещё нет — клавиатура считается закрытой.
        self.media = media(pixel_ratio=0)
        self.views = [FakeView()]
        self.services = []
        self.controls = []
        self.messages = []
        # Размер окна в логических пикселях: нужен зоне автопрокрутки.
        self.height = 800

    def run_task(self, handler, *args):
        self.tasks.append((handler, args))

    def update(self, *controls):
        self.updates += 1

    def add(self, *controls):
        self.controls.extend(controls)
        self.update()

    def show_dialog(self, dialog):
        self.messages.append(dialog.content.value)


class FakeHaptic:
    def __init__(self):
        self.calls = []

    async def medium_impact(self):
        self.calls.append("medium_impact")


class FakeStorage:
    """Хранилище в памяти: повторяет правила настоящего, но без SQLite.

    Правила, от которых зависит экран, повторяются явно: нормализация названий,
    каскад удаления категории, порядок в списках и явная запись отметки. Иначе
    тест экрана проходил бы и на поведении, которого у настоящего хранилища нет.
    """

    def __init__(self):
        self.saved = []
        self.moved = []
        self.moved_items = []
        self.deleted = []
        self.deleted_items = []
        self.checked = []
        self.created_categories = []
        self.created_items = []
        self.item_titles = []
        self.categories = []
        self.items = []
        self.fail_move = False
        self.fail_move_item = False
        self.fail_save = False
        self.fail_delete = False
        self.fail_delete_item = False
        self.fail_create_category = False
        self.fail_create_item = False
        self.fail_item_title = False
        self.fail_check = False
        self.recovered_backup = None

    def list_categories(self):
        return list(self.categories)

    def list_items(self):
        return list(self.items)

    def create_category(self, title=domain.DEFAULT_CATEGORY_TITLE):
        """Повторяет правила настоящего хранилища: конец списка и нормализация."""
        self.created_categories.append(title)
        if self.fail_create_category:
            raise storage.StorageError("нет места")
        category = domain.Category(
            id=max((item.id for item in self.categories), default=0) + 1,
            title=domain.normalize_title(title, domain.DEFAULT_CATEGORY_TITLE),
            position=len(self.categories),
        )
        self.categories.append(category)
        return category

    def set_category_title(self, category_id, title):
        self.saved.append((category_id, title))
        if self.fail_save:
            raise storage.StorageError("нет места")
        title = domain.normalize_title(title, domain.DEFAULT_CATEGORY_TITLE)
        # Название хранится в БД: список категорий в памяти отражает запись,
        # как и у настоящего хранилища.
        self.categories = [
            domain.Category(id=item.id, title=title, position=item.position)
            if item.id == category_id
            else item
            for item in self.categories
        ]
        return title

    def move_category(self, category_id, new_position):
        """Повторяет правила настоящего хранилища: подрезка позиции и порядок."""
        self.moved.append((category_id, new_position))
        if self.fail_move:
            raise storage.StorageError("нет места")
        ids = [item.id for item in self.categories]
        moved = self.categories.pop(ids.index(category_id))
        new_position = max(0, min(new_position, len(self.categories)))
        self.categories.insert(new_position, moved)
        return [
            domain.Category(id=item.id, title=item.title, position=position)
            for position, item in enumerate(self.categories)
        ]

    def delete_category(self, category_id):
        """Повторяет правила настоящего хранилища: каскад, удаление и порядок без дыр."""
        self.deleted.append(category_id)
        if self.fail_delete:
            raise storage.StorageError("нет места")
        ids = [item.id for item in self.categories]
        self.categories.pop(ids.index(category_id))
        # Пункты удалённой категории уходят каскадом (ON DELETE CASCADE).
        self.items = [item for item in self.items if item.category_id != category_id]
        return [
            domain.Category(id=item.id, title=item.title, position=position)
            for position, item in enumerate(self.categories)
        ]

    def create_item(self, category_id, title=domain.DEFAULT_ITEM_TITLE):
        """Повторяет правила настоящего хранилища: конец категории и отметка 0."""
        self.created_items.append((category_id, title))
        if self.fail_create_item:
            raise storage.StorageError("нет места")
        item = domain.Item(
            id=max((item.id for item in self.items), default=0) + 1,
            category_id=category_id,
            title=domain.normalize_title(title, domain.DEFAULT_ITEM_TITLE),
            is_checked=False,
            position=sum(1 for item in self.items if item.category_id == category_id),
        )
        self.items.append(item)
        return item

    def set_item_title(self, item_id, title):
        self.item_titles.append((item_id, title))
        if self.fail_item_title:
            raise storage.StorageError("нет места")
        title = domain.normalize_title(title, domain.DEFAULT_ITEM_TITLE)
        self.items = [
            domain.Item(
                id=item.id,
                category_id=item.category_id,
                title=title,
                is_checked=item.is_checked,
                position=item.position,
            )
            if item.id == item_id
            else item
            for item in self.items
        ]
        return title

    def set_item_checked(self, item_id, is_checked):
        """Повторяет правила настоящего хранилища: проверка пункта и явное значение."""
        self.checked.append((item_id, is_checked))
        if self.fail_check:
            raise storage.StorageError("нет места")
        self.items = [
            domain.Item(
                id=item.id,
                category_id=item.category_id,
                title=item.title,
                is_checked=(is_checked if item.id == item_id else item.is_checked),
                position=item.position,
            )
            for item in self.items
        ]
        return is_checked

    def delete_item(self, item_id):
        """Повторяет правила настоящего хранилища: удаление и порядок без дыр."""
        self.deleted_items.append(item_id)
        if self.fail_delete_item:
            raise storage.StorageError("нет места")
        deleted = next(item for item in self.items if item.id == item_id)
        category_id = deleted.category_id
        remaining = sorted(
            (
                item
                for item in self.items
                if item.category_id == category_id and item.id != item_id
            ),
            key=lambda item: item.position,
        )
        orders = [
            domain.Item(
                id=item.id,
                category_id=category_id,
                title=item.title,
                is_checked=item.is_checked,
                position=index,
            )
            for index, item in enumerate(remaining)
        ]
        self.items = [
            item for item in self.items if item.category_id != category_id
        ] + orders
        return orders

    def move_item(self, item_id, category_id, new_position):
        """Повторяет правила настоящего хранилища: порядок в обеих категориях."""
        self.moved_items.append((item_id, category_id, new_position))
        if self.fail_move_item:
            raise storage.StorageError("нет места")
        moved = next(item for item in self.items if item.id == item_id)
        previous_category_id = moved.category_id
        affected = (
            [previous_category_id]
            if previous_category_id == category_id
            else [previous_category_id, category_id]
        )
        orders = {}
        for affected_id in affected:
            remaining = [
                item
                for item in self.items
                if item.category_id == affected_id and item.id != item_id
            ]
            remaining.sort(key=lambda item: item.position)
            if affected_id == category_id:
                position = max(0, min(new_position, len(remaining)))
                remaining.insert(position, moved)
            orders[affected_id] = [
                domain.Item(
                    id=item.id,
                    category_id=affected_id,
                    title=item.title,
                    is_checked=item.is_checked,
                    position=index,
                )
                for index, item in enumerate(remaining)
            ]
        untouched = [item for item in self.items if item.category_id not in orders]
        self.items = untouched + [
            item for affected_items in orders.values() for item in affected_items
        ]
        return orders


def category(category_id, title):
    return domain.Category(id=category_id, title=title, position=category_id - 1)


def make_app(*titles):
    """Приложение с категориями из titles, без страницы: только состояние."""
    page = FakePage()
    haptic = FakeHaptic()
    storage = FakeStorage()
    app = ChecklistApp(page, storage=storage, haptic=haptic)
    views = [
        app._append_category(category(index + 1, title))
        for index, title in enumerate(titles)
    ]
    storage.categories = [view.category for view in views]
    return page, app, haptic, views


def category_start_event(view, *, local_y=0.0, global_y=0.0):
    """Долгое нажатие на названии категории: событие начала перетаскивания."""
    return ft.LongPressStartEvent(
        name="long_press_start",
        control=view.gesture_area,
        local_position=ft.Offset(0, local_y),
        global_position=ft.Offset(0, global_y),
    )


def category_move_event(view, global_y):
    return ft.LongPressMoveUpdateEvent(
        name="long_press_move_update",
        control=view.gesture_area,
        local_position=ft.Offset(0, global_y),
        global_position=ft.Offset(0, global_y),
        offset_from_origin=ft.Offset(0, 0),
        local_offset_from_origin=ft.Offset(0, 0),
    )


def category_end_event(view, global_y):
    return ft.LongPressEndEvent(
        name="long_press_end",
        control=view.gesture_area,
        local_position=ft.Offset(0, global_y),
        global_position=ft.Offset(0, global_y),
        velocity=ft.Offset(0, 0),
    )


def press_category(app, view, *, at=300.0):
    """Одно долгое нажатие по названию: start, затем long_press.

    Перетаскивание этим жестом не начинается: категория только выделяется.
    """
    asyncio.run(
        view.gesture_area.on_long_press_start(category_start_event(view, global_y=at))
    )
    asyncio.run(view.gesture_area.on_long_press(None))


def pick_up_category(app, view, *, at=300.0):
    """Поднимает категорию, как на устройстве: выделил, отпустил, зажал снова."""
    press_category(app, view, at=at)
    press_category(app, view, at=at)


def drag_category_to(app, view, model_y):
    """Ведёт палец в координату модели списка (с учётом привязки и прокрутки)."""
    drag = app._category_drag
    asyncio.run(
        view.gesture_area.on_long_press_move_update(
            category_move_event(view, model_y + drag.origin_y - app._scroll_pixels)
        )
    )


def drag_category_to_screen(app, view, global_y):
    """Ведёт палец в экранную координату: для проверки зоны автопрокрутки."""
    asyncio.run(
        view.gesture_area.on_long_press_move_update(category_move_event(view, global_y))
    )


def drop_category(app, view, model_y):
    drag = app._category_drag
    asyncio.run(
        view.gesture_area.on_long_press_end(
            category_end_event(view, model_y + drag.origin_y - app._scroll_pixels)
        )
    )


def fake_focus(monkeypatch):
    """Заменяет focus() у поля: настоящий вызов требует живого клиента."""
    focused = []

    async def focus(field):
        focused.append(field)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return focused


def slot_actions(app):
    """Действия трёх слотов button_area: подпись, обработчик и видимость.

    Один снимок вместо восьми отдельных assert: слоты постоянные, и важно не
    только что действие нужное, но и что два других слота показывают то же, что
    и раньше.
    """
    return [
        (button.content.semantics_label, button.on_click, button.visible)
        for button in app.button_area.content.controls
    ]


def start_rename(app, view):
    """Открывает ввод названия с прежним значением — как кнопка «карандаш»."""
    return app._begin_title_input(view, view.title)


def commit_title(app, view, value):
    """Вводит новое название и завершает ввод — как кнопка действия клавиатуры."""
    field = start_rename(app, view)
    field.value = value
    asyncio.run(app._finish_title_input(view))
    return field


def item(item_id, category_id, title, is_checked=False, position=0):
    return domain.Item(
        id=item_id,
        category_id=category_id,
        title=title,
        is_checked=is_checked,
        position=position,
    )


def make_app_with_items():
    """Приложение «Дом»/«Работа» с двумя пунктами в «Доме»."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    first = home.append_item(item(1, home.category.id, "Молоко"))
    second = home.append_item(item(2, home.category.id, "Хлеб", position=1))
    app.storage.items = [first.item, second.item]
    return page, app, haptic, home, work, first, second


def measure(app, *, title_height=30.0, item_height=50.0, width=300.0):
    """Проставляет размеры, которые клиент присылает событием size_change."""
    for category in app.views:
        category.title_height = title_height
        category.height = category_panel_height(
            title_height, [item_height] * len(category.items)
        )
        category.width = width
        for item_view in category.items:
            item_view.height = item_height
            item_view.width = width


def long_press_start_event(
    view, *, local_y=0.0, global_y=0.0, local_x=0.0, global_x=0.0
):
    return ft.LongPressStartEvent(
        name="long_press_start",
        control=view.row,
        local_position=ft.Offset(local_x, local_y),
        global_position=ft.Offset(global_x, global_y),
    )


def drag_move_event(view, global_y, global_x=0.0):
    return ft.LongPressMoveUpdateEvent(
        name="long_press_move_update",
        control=view.row,
        local_position=ft.Offset(0, global_y),
        global_position=ft.Offset(global_x, global_y),
        offset_from_origin=ft.Offset(0, 0),
        local_offset_from_origin=ft.Offset(0, 0),
    )


def drag_end_event(view, global_y):
    return ft.LongPressEndEvent(
        name="long_press_end",
        control=view.row,
        local_position=ft.Offset(0, global_y),
        global_position=ft.Offset(0, global_y),
        velocity=ft.Offset(0, 0),
    )


def press_item(view, *, at=300.0):
    """Одно долгое нажатие по пункту: start, затем long_press.

    Перетаскивание этим жестом не начинается: пункт только выделяется.
    """
    asyncio.run(view.row.on_long_press_start(long_press_start_event(view, global_y=at)))
    asyncio.run(view.row.on_long_press(None))


def pick_up_item(view, *, at=300.0):
    """Поднимает пункт, как на устройстве: выделил, отпустил, зажал снова."""
    press_item(view, at=at)
    press_item(view, at=at)


def drag_to_global(app, view, global_y, global_x=0.0):
    asyncio.run(
        view.row.on_long_press_move_update(drag_move_event(view, global_y, global_x))
    )


def drop_at_global(app, view, global_y):
    asyncio.run(view.row.on_long_press_end(drag_end_event(view, global_y)))


def drag_item_to(app, view, model_y):
    """Ведёт палец в координату модели списка (с учётом привязки и прокрутки)."""
    drag = app._item_drag
    drag_to_global(app, view, model_y + drag.origin_y - app._scroll_pixels)


def drop_item(app, view, model_y):
    drag = app._item_drag
    drop_at_global(app, view, model_y + drag.origin_y - app._scroll_pixels)


class FakeScrollList:
    """Список, который запоминает заказы прокрутки вместо обращения к клиенту.

    Реальный `ListView.scroll_to()` требует живого клиента («Control must be
    added to the page first»), поэтому в тестах список подменяется этой
    заглушкой: `controls` повторяет список элементов, `calls` — заказы прокрутки.
    """

    def __init__(self, on_scroll=None):
        self.controls = []
        self.calls = []
        self._on_scroll = on_scroll

    async def scroll_to(self, **kwargs):
        self.calls.append(kwargs)
        if self._on_scroll is not None:
            self._on_scroll(kwargs)


def scroll_spy(app, on_scroll=None):
    """Подменяет список «шпионом»: в тестах клиента нет, `scroll_to` некуда идти.

    Содержимое на момент подмены переносится в заглушку: дальше приложение
    дописывает в `controls` так же, как дописывало бы в настоящий список.
    """
    fake = FakeScrollList(on_scroll)
    fake.controls = list(app.category_list.controls)
    app.category_list = fake
    return fake


def scroll_event(
    *, pixels, max_scroll_extent=1000.0, viewport=550.0, event_type=None
):
    return ft.OnScrollEvent(
        name="scroll",
        control=ft.Column(),
        event_type=event_type or ft.ScrollType.UPDATE,
        pixels=pixels,
        min_scroll_extent=0.0,
        max_scroll_extent=max_scroll_extent,
        viewport_dimension=viewport,
    )


def select_item(app, view):
    """Выделяет пункт так же, как пользователь: долгим нажатием."""
    asyncio.run(app._on_item_long_press(view))
