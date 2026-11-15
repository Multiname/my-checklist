import asyncio
from pathlib import Path

import flet as ft
import pytest

import domain
import main
import storage


def default_actions():
    """Действия слотов, когда ничего не выделено: виден только плюс."""
    return [
        main.ButtonAction(main.LABEL_CREATE_CATEGORY),
        main.ButtonAction(main.LABEL_RENAME_CATEGORY, visible=False),
        main.ButtonAction(main.LABEL_DELETE_CATEGORY, visible=False),
    ]


def test_app_module_is_importable():
    assert callable(main.main)


def test_button_area_is_pinned_to_bottom_right():
    button_area = main.create_button_area(default_actions())

    assert button_area.right == main.BUTTON_AREA_MARGIN
    assert button_area.bottom == main.BUTTON_AREA_MARGIN


def test_button_area_has_three_permanent_slots():
    """Слоты постоянные: плюс, карандаш и корзина — по кнопке на слот."""
    buttons = main.create_button_area(default_actions()).content.controls

    assert [button.content.src for button in buttons] == list(main.BUTTON_ICONS)
    for button in buttons:
        assert button.width == main.BUTTON_SIZE
        assert button.height == main.BUTTON_SIZE
        assert button.border_radius == main.BUTTON_SIZE / 2


def test_button_area_binds_each_action_to_its_slot():
    actions = default_actions()

    buttons = main.create_button_area(actions).content.controls

    assert [button.content.semantics_label for button in buttons] == [
        action.label for action in actions
    ]
    assert [button.visible for button in buttons] == [True, False, False]


def test_button_area_requires_one_action_per_slot():
    with pytest.raises(ValueError):
        main.create_button_area([main.ButtonAction(main.LABEL_CREATE_CATEGORY)])


def test_buttons_are_clickable_with_ink_ripple():
    for button in main.create_button_area(default_actions()).content.controls:
        assert button.ink is True
        assert callable(button.on_click)


def test_plus_button_runs_given_handler():
    events = []
    actions = default_actions()
    actions[0] = main.ButtonAction(
        main.LABEL_CREATE_CATEGORY, lambda event: events.append(event)
    )
    plus_button = main.create_button_area(actions).content.controls[0]

    plus_button.on_click(None)

    assert len(events) == 1


def test_button_icons_exist_in_assets():
    assets_dir = Path(__file__).parent.parent / "src" / "assets"

    for icon in main.BUTTON_ICONS:
        assert (assets_dir / icon).is_file()


def test_category_panel_is_rectangular_with_title_on_top():
    panel = main.create_category_panel(main.create_category_title("Работа"))

    assert isinstance(panel, ft.Container)
    assert panel.content.value == "Работа"
    assert panel.content.style == main.CATEGORY_TITLE_STYLE
    assert panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert panel.border_radius == main.CATEGORY_PANEL_RADIUS
    assert panel.padding == main.CATEGORY_PANEL_PADDING
    # Горизонтальных отступов у панели нет: их несут название и пункты, иначе
    # выделенный пункт не смог бы закрасить панель до краёв.
    assert panel.padding.left == panel.padding.right == 0
    assert panel.padding.top == main.CATEGORY_PANEL_VERTICAL_PADDING
    assert panel.padding.bottom == main.CATEGORY_PANEL_VERTICAL_PADDING


def test_category_item_keeps_the_gap_inside_the_list_item():
    """Промежуток — часть элемента списка, панель остаётся панелью."""
    panel = main.create_category_panel("Работа")

    item = main.create_category_item(panel)

    assert item.content is panel
    assert item.padding == main.CATEGORY_ITEM_PADDING
    assert item.padding == ft.Padding.only(bottom=main.CATEGORY_SPACING)
    assert item.bgcolor is None
    assert item.margin is None


def test_category_area_only_wraps_the_list_for_taps():
    """Своей темы у области списка нет: прокси рисует приложение, а не клиент."""
    category_list = main.create_category_list()

    category_area = main.create_category_area(category_list, lambda event: None)

    assert category_area.content.content is category_list
    assert category_area.content.on_tap is not None
    assert category_area.theme is None


def test_category_list_scrolls_full_screen_above_button_area():
    category_list = main.create_category_list()

    assert isinstance(category_list, ft.ListView)
    assert category_list.expand is True
    # Список строится целиком: иначе scroll_to() после создания не работает.
    assert category_list.build_controls_on_demand is False
    assert category_list.auto_scroll is False
    assert category_list.padding.bottom >= main.BUTTON_AREA_HEIGHT


def test_category_input_shows_keyboard_and_commits_on_focus_loss():
    def on_commit(event):
        pass

    category_input = main.create_category_input("Категория", on_commit)

    assert category_input.autofocus is True
    assert category_input.hint_text == "Категория"
    assert category_input.on_submit is on_commit
    assert category_input.on_blur is on_commit
    assert category_input.on_tap_outside is on_commit


def test_category_input_has_same_line_height_as_title():
    """Панель не должна менять высоту при переходе в режим ввода."""
    category_input = main.create_category_input("Категория", lambda event: None)
    title = main.create_category_title("Работа")

    assert category_input.text_style == title.style
    assert category_input.hint_style.size == main.CATEGORY_TITLE_SIZE
    assert category_input.hint_style.height == main.CATEGORY_TITLE_LINE_HEIGHT
    assert category_input.dense is True


def media(*, bottom_padding=16.0, bottom_inset=0.0, pixel_ratio=3.5):
    return ft.PageMediaData(
        padding=ft.Padding.only(bottom=bottom_padding),
        view_padding=ft.Padding.only(bottom=bottom_padding),
        view_insets=ft.Padding.only(bottom=bottom_inset),
        device_pixel_ratio=pixel_ratio,
        orientation=ft.Orientation.PORTRAIT,
    )


def test_keyboard_visible_by_navigation_padding():
    # При adjustResize keyboard hidden = нижний padding навигации на месте,
    # open = он пропал.
    assert main.ChecklistApp._keyboard_visible(media(bottom_padding=16)) is False
    assert main.ChecklistApp._keyboard_visible(media(bottom_padding=0)) is True


def test_keyboard_visible_by_view_insets():
    assert main.ChecklistApp._keyboard_visible(media(bottom_inset=300)) is True


def test_keyboard_visible_without_client_media():
    assert main.ChecklistApp._keyboard_visible(media(pixel_ratio=0)) is False


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
    def __init__(self):
        self.saved = []
        self.moved = []
        self.moved_items = []
        self.deleted = []
        self.deleted_items = []
        self.categories = []
        self.created_items = []
        self.item_titles = []
        self.items = []
        self.fail_move = False
        self.fail_move_item = False
        self.fail_save = False
        self.fail_delete = False
        self.fail_delete_item = False
        self.fail_create_item = False
        self.fail_item_title = False
        self.recovered_backup = None
        self._next_item_id = 1

    def list_categories(self):
        return list(self.categories)

    def list_items(self):
        return list(self.items)

    def set_category_title(self, category_id, title):
        self.saved.append((category_id, title))
        if self.fail_save:
            raise storage.StorageError("нет места")
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
        """Повторяет правила настоящего хранилища: удаление и порядок без дыр."""
        self.deleted.append(category_id)
        if self.fail_delete:
            raise storage.StorageError("нет места")
        ids = [item.id for item in self.categories]
        self.categories.pop(ids.index(category_id))
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
            id=self._next_item_id,
            category_id=category_id,
            title=title,
            is_checked=False,
            position=sum(1 for item in self.items if item.category_id == category_id),
        )
        self._next_item_id += 1
        self.items.append(item)
        return item

    def set_item_title(self, item_id, title):
        self.item_titles.append((item_id, title))
        if self.fail_item_title:
            raise storage.StorageError("нет места")
        return title

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
    app = main.ChecklistApp(page, storage=storage, haptic=haptic)
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


def test_keyboard_close_commits_editing():
    page = FakePage()
    app = main.ChecklistApp(page, storage=None)
    view = object()
    app._editing_view = view

    app._on_media_change(media(bottom_padding=0))
    assert page.tasks == []

    app._on_media_change(media(bottom_padding=16))

    assert len(page.tasks) == 1
    handler, args = page.tasks[0]
    assert handler == app._finish_title_input
    assert args == (view,)


def test_keyboard_close_without_editing_does_nothing():
    page = FakePage()
    app = main.ChecklistApp(page, storage=None)

    app._on_media_change(media(bottom_padding=0))
    app._on_media_change(media(bottom_padding=16))

    assert page.tasks == []


def test_category_view_starts_with_title_text():
    view = main.CategoryView(category=domain.Category(id=1, title="Дом", position=0))

    assert view.title == "Дом"
    assert view.title_text.value == "Дом"
    assert view.title_slot.content is view.title_text
    assert view.is_editing is False
    # Панель: название сверху, под ним — контейнер пунктов. Жесты категории — на
    # обёртке панели: панель сворачивается при перетаскивании, и распознаватель
    # внутри неё пересоздался бы вместе с содержимым.
    title_slot, items_box = view.panel.content.controls
    assert title_slot is view.title_slot
    assert items_box is view.items_box
    assert view.item.content is view.gesture_area
    assert view.gesture_area.content is view.panel
    # Горизонтальный отступ названия — у слота, а не у панели.
    assert view.title_slot.padding == main.CATEGORY_TITLE_PADDING


def test_buttons_hide_while_editing_title():
    """Во время ввода кнопки button_area не показываются, после — возвращаются."""
    page = FakePage()
    storage = FakeStorage()
    app = main.ChecklistApp(page, storage=storage)
    view = main.CategoryView(domain.Category(id=1, title="Дом", position=0))

    field = app._begin_title_input(view)

    assert app.button_area.visible is False
    assert view.is_editing is True
    assert page.updates == 1

    field.value = "Работа"
    asyncio.run(app._finish_title_input(view))

    assert app.button_area.visible is True
    assert view.is_editing is False
    assert view.title == "Работа"
    assert storage.saved == [(1, "Работа")]


def test_buttons_stay_hidden_while_another_title_is_edited():
    page = FakePage()
    app = main.ChecklistApp(page, storage=FakeStorage())
    first = main.CategoryView(domain.Category(id=1, title="Дом", position=0))
    second = main.CategoryView(domain.Category(id=2, title="Работа", position=1))
    app._begin_title_input(first)
    app._begin_title_input(second)

    asyncio.run(app._finish_title_input(first))

    # Ввод ещё идёт у второй категории — кнопки остаются скрытыми.
    assert app.button_area.visible is False


def test_category_items_are_list_items_with_panels_inside():
    """Категории лежат в списке обёртками, панель внутри ловит жесты."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    assert app.category_list.controls == [home.item, work.item]
    assert home.item.content is home.gesture_area
    assert work.item.content is work.gesture_area
    assert home.gesture_area.content is home.panel
    assert home.panel.content.controls[0] is home.title_slot


def test_category_drag_is_led_by_the_app_not_the_list():
    """Список только прокручивается: перетаскивание категории ведёт приложение."""
    page, app, haptic, views = make_app("Дом")

    assert isinstance(app.category_list, ft.ListView)
    assert app.category_list.on_scroll == app._on_scroll
    # Штатного переупорядочивания у списка больше нет.
    assert not hasattr(app.category_list, "on_reorder")
    assert callable(views[0].gesture_area.on_long_press_start)


def test_drag_hides_button_area_and_returns_it():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    app._select_category(work)
    assert app.button_area.visible is True

    pick_up_category(app, home)

    # Пока категорию перетаскивают, кнопок не видно.
    assert app._dragging is True
    assert app.button_area.visible is False

    drop_category(app, home, main.LIST_PADDING)

    assert app._dragging is False
    assert app.button_area.visible is True
    # Выделение пережило drag: слоты показывают действия выделенной категории.
    assert app._selected_view is home
    assert app.plus_button.content.semantics_label == main.LABEL_ADD_ITEM
    assert app.pencil_button.visible is True
    assert app.trash_button.visible is True


def test_drag_with_new_order_restores_button_area():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    drop_category(app, home, 1000)

    assert app.button_area.visible is True
    assert [view.title for view in app.views] == ["Работа", "Дом"]


def test_tap_after_interrupted_drag_returns_button_area():
    """Если система прервала жест, отпускание не придёт — состояние снимет тап."""
    page, app, haptic, (home,) = make_app("Дом")
    measure(app)
    pick_up_category(app, home)

    app.category_area.content.on_tap(None)

    assert app._dragging is False
    assert app._category_drag is None
    assert home.panel.height is None
    assert home.item.margin is None
    assert app.button_area.visible is True


def test_list_tap_area_wraps_category_list():
    page, app, haptic, views = make_app()

    assert app.category_area.content.content is app.category_list
    assert app.category_area.content.on_tap == app._on_tap


def test_long_press_selects_category_with_haptic_and_color():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    asyncio.run(home.gesture_area.on_long_press(None))

    assert app._selected_view is home
    assert home.selected is True
    assert home.panel.bgcolor == main.CATEGORY_PANEL_SELECTED_COLOR
    assert work.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert haptic.calls == ["medium_impact"]
    assert page.updates == 1
    # Пока категория выделена, «назад» перехватывается.
    assert page.views[0].can_pop is False


def test_long_press_on_another_category_moves_selection():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    asyncio.run(home.gesture_area.on_long_press(None))
    asyncio.run(work.gesture_area.on_long_press(None))

    assert app._selected_view is work
    assert home.selected is False
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert work.panel.bgcolor == main.CATEGORY_PANEL_SELECTED_COLOR
    # Виброотклик даётся на каждый начатый drag.
    assert haptic.calls == ["medium_impact", "medium_impact"]


def test_repeated_long_press_keeps_single_selection_and_vibrates():
    """Повторное долгое нажатие — это новое перетаскивание, отклик нужен снова."""
    page, app, haptic, (home,) = make_app("Дом")

    asyncio.run(home.gesture_area.on_long_press(None))
    asyncio.run(home.gesture_area.on_long_press(None))

    assert app._selected_view is home
    assert haptic.calls == ["medium_impact", "medium_impact"]


def test_drag_does_not_start_without_panel_size():
    """Без размеров панели долгое нажатие только выделяет категорию."""
    page, app, haptic, (home,) = make_app("Дом")

    pick_up_category(app, home)

    assert app._category_drag is None
    assert app._selected_view is home
    assert home.panel.height is None
    assert app.stack.controls == [app.category_area, app.button_area]


def test_drag_start_waits_for_the_category_to_be_selected():
    """Подъём не начинается тем же нажатием, которое выделяет категорию.

    Событие `on_long_press_start` приходит раньше `on_long_press`, поэтому в
    момент подъёма выделения ещё нет — категория поднимается только вторым
    долгим нажатием, когда она уже выделена и палец отпущен.
    """
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)

    asyncio.run(
        home.gesture_area.on_long_press_start(category_start_event(home, global_y=300))
    )

    assert app._category_drag is None
    assert home.collapsed is False
    assert home.panel.height is None

    asyncio.run(home.gesture_area.on_long_press(None))

    assert app._selected_view is home
    assert app._category_drag is None

    asyncio.run(
        home.gesture_area.on_long_press_start(category_start_event(home, global_y=300))
    )

    assert app._category_drag is not None
    assert home.collapsed is True


def test_category_drag_start_ignores_another_selected_category():
    """Поднимается только выделенная категория: чужое выделение не помогает."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    app._select_category(work)

    asyncio.run(
        home.gesture_area.on_long_press_start(category_start_event(home, global_y=300))
    )

    assert app._category_drag is None
    assert home.collapsed is False

    asyncio.run(
        work.gesture_area.on_long_press_start(category_start_event(work, global_y=100))
    )

    assert app._category_drag is not None
    assert app._category_drag.view is work
    assert work.collapsed is True


def test_category_drag_is_ignored_while_a_title_is_edited():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    app._begin_title_input(home)

    pick_up_category(app, home)
    asyncio.run(
        home.gesture_area.on_long_press_start(category_start_event(home, global_y=300))
    )

    assert app._selected_view is None
    assert haptic.calls == []
    assert app._category_drag is None
    assert home.panel.height is None


def test_drag_moves_category_and_saves_order():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    measure(app)

    pick_up_category(app, home)
    drop_category(app, home, 1000)

    assert [view.title for view in app.views] == ["Работа", "Отдых", "Дом"]
    assert app.category_list.controls == [view.item for view in app.views]
    assert app.storage.moved == [(home.category.id, 2)]
    # Позиции обновляются по порядку из БД.
    assert [(view.category.title, view.category.position) for view in app.views] == [
        ("Работа", 0),
        ("Отдых", 1),
        ("Дом", 2),
    ]


def test_drag_updates_the_order_in_place_after_drop():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    measure(app)
    pick_up_category(app, work)

    drop_category(app, work, main.LIST_PADDING)

    # Выделение переживает перетаскивание.
    assert app._selected_view is work
    assert [view.title for view in app.views] == ["Работа", "Дом", "Отдых"]
    assert app.storage.moved == [(work.category.id, 0)]


def test_drag_to_the_same_position_does_not_touch_storage():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    drop_category(app, home, main.LIST_PADDING)

    assert app.storage.moved == []
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_drag_without_movement_does_not_touch_storage():
    """Жест без движения — это выделение, а не перетаскивание."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    asyncio.run(home.gesture_area.on_long_press_end(category_end_event(home, 300)))

    assert app.storage.moved == []
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_drag_write_error_keeps_order_and_reports():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    app.storage.fail_move = True

    pick_up_category(app, home)
    drop_category(app, home, 1000)

    # Порядок задаёт БД: без записи он прежний и в памяти, и на экране.
    assert [view.title for view in app.views] == ["Дом", "Работа"]
    assert page.messages == ["Не удалось сохранить порядок категорий"]
    assert app.button_area.visible is True


def test_selection_swaps_button_actions():
    """Слоты кнопок постоянные, а действие зависит от выделения."""
    page, app, haptic, (home,) = make_app("Дом")

    # Ничего не выделено: виден только плюс, он создаёт категорию.
    assert app.plus_button.visible is True
    assert app.plus_button.on_click == app.create_category
    assert app.plus_button.content.semantics_label == main.LABEL_CREATE_CATEGORY
    assert app.pencil_button.visible is False
    assert app.trash_button.visible is False

    app._select_category(home)

    # Выделена категория: плюс добавляет пункт, карандаш и корзина — категорию.
    assert app.plus_button.visible is True
    assert app.plus_button.content.semantics_label == main.LABEL_ADD_ITEM
    assert app.plus_button.on_click == app.add_item
    assert app.pencil_button.visible is True
    assert app.pencil_button.on_click == app.rename_category
    assert app.trash_button.visible is True
    assert app.trash_button.on_click == app.delete_category

    app._deselect()

    assert app.plus_button.on_click == app.create_category
    assert app.plus_button.content.semantics_label == main.LABEL_CREATE_CATEGORY
    assert app.pencil_button.visible is False
    assert app.trash_button.visible is False


def test_switching_selection_keeps_the_same_buttons():
    """Кнопки не пересоздаются: слоты и иконки остаются те же."""
    page, app, haptic, (home,) = make_app("Дом")
    buttons = list(app.button_area.content.controls)
    icons = [button.content.src for button in buttons]

    app._select_category(home)
    app._deselect()

    assert all(
        actual is expected
        for actual, expected in zip(app.button_area.content.controls, buttons)
    )
    assert [button.content.src for button in buttons] == icons
    assert app.plus_button.content.src == main.ICON_PLUS
    assert app.pencil_button.content.src == main.ICON_PENCIL
    assert app.trash_button.content.src == main.ICON_TRASH


def test_tap_on_list_deselects_category():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    page.updates = 0

    app.category_area.content.on_tap(None)

    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert page.views[0].can_pop is True
    assert page.updates == 1


def test_tap_without_selection_changes_nothing():
    page, app, haptic, views = make_app("Дом")
    page.updates = 0

    app.category_area.content.on_tap(None)

    assert app._selected_view is None
    assert page.updates == 0


def test_tap_that_closes_keyboard_keeps_selection():
    """Тап, закрывающий клавиатуру при вводе названия, выделение не снимает."""
    page, app, haptic, (home, editing) = make_app("Дом", "Работа")
    app._select_category(home)
    app._begin_title_input(editing)

    app.category_area.content.on_tap(None)

    assert app._selected_view is home
    assert home.selected is True


def test_back_with_selection_deselects_without_closing_app():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)

    asyncio.run(app._on_confirm_pop(None))

    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert page.views[0].can_pop is True
    # False — не выходить из приложения.
    assert page.views[0].pops == [False]


def test_back_without_selection_closes_app():
    page, app, haptic, views = make_app("Дом")

    asyncio.run(app._on_confirm_pop(None))

    # True — обычное поведение: «назад» закрывает приложение.
    assert page.views[0].pops == [True]


def test_mount_registers_haptic_and_back_interception():
    page = FakePage()
    app = main.ChecklistApp(page, storage=FakeStorage())

    asyncio.run(app.mount())

    assert isinstance(app.haptic, ft.HapticFeedback)
    assert page.services == [app.haptic]
    assert page.views[0].on_confirm_pop == app._on_confirm_pop


def test_category_input_for_rename_is_prefilled_and_taps_outside_separately():
    def on_commit(event):
        pass

    def on_tap_outside(event):
        pass

    category_input = main.create_category_input(
        "Категория", on_commit, "Работа", on_tap_outside
    )

    # Прежнее название — начальное значение поля, а не подсказка.
    assert category_input.value == "Работа"
    assert category_input.on_submit is on_commit
    assert category_input.on_blur is on_commit
    assert category_input.on_tap_outside is on_tap_outside


def test_pencil_button_runs_given_handler():
    events = []
    actions = default_actions()
    actions[1] = main.ButtonAction(
        main.LABEL_RENAME_CATEGORY, lambda event: events.append(event)
    )
    pencil_button = main.create_button_area(actions).content.controls[1]

    pencil_button.on_click(None)

    assert len(events) == 1


def test_pencil_button_renames_category_without_item_selection():
    page, app, haptic, views = make_app("Дом")

    assert app.pencil_button.on_click == app.rename_category


def test_trash_button_deletes_category_without_item_selection():
    page, app, haptic, views = make_app("Дом")

    assert app.trash_button.on_click == app.delete_category


def test_trash_button_runs_given_handler():
    events = []
    actions = default_actions()
    actions[2] = main.ButtonAction(
        main.LABEL_DELETE_CATEGORY, lambda event: events.append(event)
    )
    trash_button = main.create_button_area(actions).content.controls[2]

    trash_button.on_click(None)

    assert len(events) == 1


def test_list_tap_area_forwards_the_tap_cancel():
    page, app, haptic, views = make_app("Дом")

    assert app.category_area.content.on_tap_cancel == app._on_tap_cancel


def fake_focus(monkeypatch):
    """Заменяет focus() у поля: настоящий вызов требует живого клиента."""
    focused = []

    async def focus(field):
        focused.append(field)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return focused


def test_rename_opens_input_with_previous_title(monkeypatch):
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(work)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_category(None))

    # Название заменено полем ввода, в поле — прежнее название.
    assert app._editing_view is work
    assert work.input is work.title_slot.content
    assert work.input.value == "Работа"
    assert focused == [work.input]
    # Во время ввода кнопки скрыты, «назад» не закрывает приложение.
    assert app.button_area.visible is False
    assert page.views[0].can_pop is False
    assert page.updates >= 1


def test_rename_without_selection_does_nothing(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_category(None))

    assert app._editing_view is None
    assert home.title_slot.content is home.title_text
    assert focused == []


def test_rename_is_ignored_while_a_title_is_already_edited(monkeypatch):
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(work)
    field = app._begin_title_input(work, work.title)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_category(None))

    assert app._editing_view is work
    assert work.input is field
    assert focused == []


def test_rename_saves_title_and_keeps_selection():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)

    field.value = "Квартира"
    asyncio.run(app._finish_title_input(home))

    assert home.title == "Квартира"
    assert home.title_text.value == "Квартира"
    assert home.title_slot.content is home.title_text
    assert app.storage.saved == [(home.category.id, "Квартира")]
    # Выделение пережило переименование: слоты остались прежними.
    assert app._selected_view is home
    assert home.selected is True
    assert app.button_area.visible is True
    assert app.plus_button.content.semantics_label == main.LABEL_ADD_ITEM
    assert app.pencil_button.visible is True
    assert app.trash_button.visible is True
    assert page.views[0].can_pop is False


def test_rename_with_unchanged_title_does_not_write_to_storage():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)

    field.value = " Дом "
    asyncio.run(app._finish_title_input(home))

    assert app.storage.saved == []
    assert home.title == "Дом"


def test_rename_with_empty_title_uses_default_name():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)

    field.value = "   "
    asyncio.run(app._finish_title_input(home))

    assert home.title == "Категория"
    assert app.storage.saved == [(home.category.id, "Категория")]


def test_rename_write_error_keeps_previous_title_and_reports():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    app.storage.fail_save = True
    field = app._begin_title_input(home, home.title)

    field.value = "Квартира"
    asyncio.run(app._finish_title_input(home))

    # Коммит до UI: при ошибке панель показывает прежнее название.
    assert home.title == "Дом"
    assert home.title_text.value == "Дом"
    assert home.title_slot.content is home.title_text
    assert page.messages == ["Не удалось сохранить название"]
    assert app._selected_view is home


def test_back_while_renaming_saves_title_and_keeps_selection():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)
    field.value = "Квартира"

    asyncio.run(app._on_confirm_pop(None))

    assert home.title == "Квартира"
    assert app.storage.saved == [(home.category.id, "Квартира")]
    assert app._selected_view is home
    # False — не выходить из приложения.
    assert page.views[0].pops == [False]


def test_back_while_creating_category_saves_title_without_closing_app():
    page, app, haptic, views = make_app("Дом")
    new_view = main.CategoryView(
        domain.Category(id=2, title="Категория", position=1)
    )
    field = app._begin_title_input(new_view)
    field.value = "Отдых"
    assert page.views[0].can_pop is False

    asyncio.run(app._on_confirm_pop(None))

    assert new_view.title == "Отдых"
    assert app.storage.saved == [(2, "Отдых")]
    assert page.views[0].pops == [False]


def test_can_pop_is_off_while_title_is_edited():
    page, app, haptic, (home,) = make_app("Дом")
    assert page.views[0].can_pop is True

    field = app._begin_title_input(home)
    assert page.views[0].can_pop is False

    asyncio.run(app._finish_title_input(home))

    # Ввод завершён, выделения нет — «назад» снова закрывает приложение.
    assert page.views[0].can_pop is True


def test_tap_outside_ends_input_and_keeps_selection():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)
    field.value = "Квартира"

    # Нажатие вне поля: ввод завершается, введённое название сохраняется.
    asyncio.run(field.on_tap_outside(None))
    assert home.title == "Квартира"
    assert app._tap_ended_input is True

    # Отпускание того же тапа по списку выделение не снимает.
    app.category_area.content.on_tap(None)

    assert app._selected_view is home
    assert home.selected is True
    assert app._tap_ended_input is False


def test_tap_after_editing_ends_deselects_category():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)

    asyncio.run(field.on_tap_outside(None))
    app.category_area.content.on_tap(None)  # тап, закрывший клавиатуру

    app.category_area.content.on_tap(None)  # новый тап по списку

    assert app._selected_view is None
    assert home.selected is False


def test_tap_cancel_clears_the_keyboard_closing_tap_flag():
    """Тап вне поля стал прокруткой: флаг не должен съесть следующий тап."""
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)

    asyncio.run(field.on_tap_outside(None))
    app.category_area.content.on_tap_cancel(None)
    app.category_area.content.on_tap(None)

    assert app._selected_view is None
    assert app._tap_ended_input is False


def test_list_tap_while_editing_saves_title_without_deselecting():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)
    field.value = "Квартира"

    app.category_area.content.on_tap(None)

    # Тап лишь запускает завершение ввода, выделение остаётся.
    assert app._selected_view is home
    assert page.tasks == [(app._finish_title_input, (home,))]

    asyncio.run(app._finish_title_input(home))
    assert home.title == "Квартира"
    assert app._selected_view is home


def test_delete_removes_selected_category_from_list_and_storage():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    app._select_category(work)
    page.updates = 0

    asyncio.run(app.delete_category(None))

    # Категория удалена и из БД, и из списка на экране.
    assert app.storage.deleted == [work.category.id]
    assert app.views == [home, rest]
    assert app.category_list.controls == [home.item, rest.item]
    # Позиции оставшихся — из БД, без дыр в порядке.
    assert [view.category.position for view in app.views] == [0, 1]
    # Выделение снято: удалённой категории больше нет, слоты — исходные.
    assert app._selected_view is None
    assert app.plus_button.on_click == app.create_category
    assert app.plus_button.content.semantics_label == main.LABEL_CREATE_CATEGORY
    assert app.pencil_button.visible is False
    assert app.trash_button.visible is False
    assert app.button_area.visible is True
    assert page.views[0].can_pop is True
    assert page.updates == 1


def test_delete_only_the_selected_category():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    app._select_category(rest)

    asyncio.run(app.delete_category(None))

    assert app.storage.deleted == [rest.category.id]
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_delete_without_selection_does_nothing():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    page.updates = 0

    asyncio.run(app.delete_category(None))

    assert app.storage.deleted == []
    assert app.views == [home, work]
    assert page.updates == 0


def test_delete_write_error_keeps_category_and_reports():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    app.storage.fail_delete = True

    asyncio.run(app.delete_category(None))

    # Коммит до UI: при ошибке список и выделение остаются прежними.
    assert app.views == [home, work]
    assert app.category_list.controls == [home.item, work.item]
    assert app._selected_view is home
    assert home.selected is True
    assert home.panel.bgcolor == main.CATEGORY_PANEL_SELECTED_COLOR
    assert app.trash_button.visible is True
    assert page.messages == ["Не удалось удалить категорию"]


def test_delete_while_editing_title_drops_input_state():
    """Ввод и та же категория: поле уходит вместе с панелью, кнопки — назад."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    app._begin_title_input(home, home.title)

    asyncio.run(app.delete_category(None))

    assert app.storage.deleted == [home.category.id]
    assert app._editing_view is None
    assert home.input is None
    assert app.views == [work]
    assert app.button_area.visible is True
    assert page.views[0].can_pop is True


def test_delete_category_after_edit_does_not_write_deleted_title():
    """Завершение ввода после удаления не пишет название удалённой категории."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    field = app._begin_title_input(home, home.title)

    asyncio.run(app.delete_category(None))
    field.value = "Квартира"
    asyncio.run(app._finish_title_input(home))

    assert app.storage.saved == []
    assert app.views == [work]


def item(item_id, category_id, title, is_checked=False, position=0):
    return domain.Item(
        id=item_id,
        category_id=category_id,
        title=title,
        is_checked=is_checked,
        position=position,
    )


def test_item_panel_has_checkbox_on_the_left_and_transparent_background():
    checkbox = ft.Checkbox()
    title = main.create_item_title("Помыть посуду")

    panel = main.create_item_panel(checkbox, title)

    assert isinstance(panel, ft.Container)
    # Фон прозрачный: сквозь пункт видна панель категории.
    assert panel.bgcolor == main.ITEM_PANEL_COLOR == ft.Colors.TRANSPARENT
    # Горизонтальный отступ — у пункта, а не у панели: выделенная строка
    # закрашивает всю ширину панели.
    assert panel.padding == main.ITEM_PANEL_PADDING
    assert panel.padding.left == main.ITEM_PANEL_PADDING.right == 16
    assert panel.padding.top == panel.padding.bottom == 0
    assert panel.content.controls[0] is checkbox
    assert panel.content.controls[1] is title
    assert panel.content.vertical_alignment == ft.CrossAxisAlignment.CENTER


def test_item_text_is_smaller_than_category_title():
    item_title = main.create_item_title("Пункт")

    assert item_title.style == main.ITEM_TITLE_STYLE
    assert item_title.max_lines == 2
    assert main.ITEM_TITLE_SIZE < main.CATEGORY_TITLE_SIZE
    assert main.ITEM_TITLE_WEIGHT == ft.FontWeight.NORMAL


def test_empty_category_has_hidden_items_box():
    view = main.CategoryView(category(1, "Дом"))

    assert view.items == []
    assert view.items_box.visible is False
    assert view.items_box.content.controls == []


def test_category_view_keeps_items_inside_its_items_box():
    view = main.CategoryView(
        category(1, "Дом"),
        [item(1, 1, "Помыть посуду"), item(2, 1, "Пропылесосить", position=1)],
    )

    assert [item_view.title for item_view in view.items] == [
        "Помыть посуду",
        "Пропылесосить",
    ]
    assert view.items_box.visible is True
    assert view.items_box.content.controls == [
        item_view.cell for item_view in view.items
    ]
    first = view.items[0]
    assert first.checkbox.value is False
    assert first.row.content is first.panel
    assert first.panel.content.controls[0] is first.checkbox
    assert first.title_slot.content is first.title_text
    # Пункт знает свою категорию: по ней решается, выделяет ли тап пункт.
    assert first.category_view is view
    assert first.row.on_long_press is not None
    assert first.row.on_tap is not None


def test_item_spacing_lives_in_the_cell_not_in_the_box():
    """Промежуток между пунктами — отступ ячейки, а не `spacing` колонки.

    Иначе свёрнутая при перетаскивании строка (нулевой высоты) оставляла бы в
    колонке лишний промежуток, и панель категории после переноса пункта была бы
    выше на его величину.
    """
    view = main.CategoryView(
        category(1, "Дом"),
        [item(1, 1, "Помыть посуду"), item(2, 1, "Пропылесосить", position=1)],
    )
    first = view.items[0]

    assert view.items_box.content.spacing == 0
    assert first.cell.content is first.row
    assert first.cell.padding == main.ITEM_CELL_PADDING
    # Промежуток последней ячейки компенсируется нижним отступом панели.
    assert view.panel.padding == main.category_panel_padding(True)
    assert view.panel.padding.bottom == (
        main.CATEGORY_PANEL_VERTICAL_PADDING - main.ITEM_SPACING
    )
    # Категория без пунктов ничего не компенсирует.
    empty = main.CategoryView(category(2, "Работа"))
    assert empty.panel.padding == main.CATEGORY_PANEL_PADDING


def test_item_checkbox_shows_mark_saved_in_storage():
    view = main.CategoryView(
        category(1, "Дом"), [item(1, 1, "Отчёт", is_checked=True)]
    )

    assert view.items[0].checkbox.value is True


def test_add_item_appends_to_selected_category_and_opens_input(monkeypatch):
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.add_item(None))

    # Пункт создан в БД и добавлен в конец списка выделенной категории.
    assert app.storage.created_items == [
        (home.category.id, domain.DEFAULT_ITEM_TITLE)
    ]
    assert [view.title for view in home.items] == ["Пункт"]
    assert home.items_box.visible is True
    assert home.items_box.content.controls == [home.items[0].cell]
    assert work.items == []
    # На месте названия пункта — поле ввода с подсказкой «Пункт».
    item_view = home.items[0]
    assert app._editing_view is item_view
    assert item_view.input is item_view.title_slot.content
    assert item_view.input.value == ""
    assert item_view.input.hint_text == domain.DEFAULT_ITEM_TITLE
    assert item_view.input.autofocus is True
    assert focused == [item_view.input]
    # Пока идёт ввод, кнопки скрыты, «назад» не закрывает приложение.
    assert app.button_area.visible is False
    assert page.views[0].can_pop is False


def test_add_item_goes_to_the_end_of_the_category(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    home.append_item(item(1, 1, "Первый"))
    home.append_item(item(2, 1, "Второй", position=1))
    app.storage.items = [item(1, 1, "Первый"), item(2, 1, "Второй", position=1)]
    app._select_category(home)
    fake_focus(monkeypatch)

    asyncio.run(app.add_item(None))

    assert [view.title for view in home.items] == ["Первый", "Второй", "Пункт"]
    assert home.items_box.content.controls[-1] is home.items[-1].cell


def test_add_item_saves_entered_title_and_restores_buttons(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    fake_focus(monkeypatch)
    asyncio.run(app.add_item(None))
    item_view = home.items[0]

    item_view.input.value = "  Купить хлеб  "
    asyncio.run(app._finish_title_input(item_view))

    assert item_view.title == "Купить хлеб"
    assert item_view.title_text.value == "Купить хлеб"
    assert item_view.title_slot.content is item_view.title_text
    assert app.storage.item_titles == [(item_view.item.id, "Купить хлеб")]
    # Выделение категории пережило создание пункта: слоты остались прежними.
    assert app._selected_view is home
    assert app.button_area.visible is True
    assert app.plus_button.on_click == app.add_item
    assert app.pencil_button.visible is True
    assert app.trash_button.visible is True
    assert page.views[0].can_pop is False


def test_add_item_without_title_keeps_default_name(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    fake_focus(monkeypatch)
    asyncio.run(app.add_item(None))
    item_view = home.items[0]

    asyncio.run(app._finish_title_input(item_view))

    # Пункт уже создан с названием «Пункт»: пустой ввод ничего не меняет.
    assert app.storage.created_items == [(home.category.id, "Пункт")]
    assert app.storage.item_titles == []
    assert item_view.title == "Пункт"
    assert item_view.title_slot.content is item_view.title_text


def test_add_item_requires_selected_category(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    focused = fake_focus(monkeypatch)

    asyncio.run(app.add_item(None))

    assert app.storage.created_items == []
    assert home.items == []
    assert focused == []


def test_add_item_is_ignored_while_a_title_is_edited(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    app._begin_title_input(home, home.title)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.add_item(None))

    assert app.storage.created_items == []
    assert home.items == []
    assert focused == []


def test_add_item_write_error_adds_nothing_and_reports(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    app.storage.fail_create_item = True
    focused = fake_focus(monkeypatch)

    asyncio.run(app.add_item(None))

    # Коммит до UI: при ошибке нового пункта нет, поле не открывается.
    assert home.items == []
    assert home.items_box.visible is False
    assert app._editing_view is None
    assert app.button_area.visible is True
    assert page.messages == ["Не удалось добавить пункт"]
    assert focused == []


def test_item_title_write_error_keeps_default_and_reports(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    app.storage.fail_item_title = True
    fake_focus(monkeypatch)
    asyncio.run(app.add_item(None))
    item_view = home.items[0]
    item_view.input.value = "Купить хлеб"

    asyncio.run(app._finish_title_input(item_view))

    assert item_view.title == "Пункт"
    assert item_view.title_text.value == "Пункт"
    assert item_view.title_slot.content is item_view.title_text
    assert page.messages == ["Не удалось сохранить название"]
    assert app._selected_view is home


def test_tap_outside_item_input_saves_title_and_keeps_category_selection(
    monkeypatch,
):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    fake_focus(monkeypatch)
    asyncio.run(app.add_item(None))
    item_view = home.items[0]
    field = item_view.input
    field.value = "Купить хлеб"

    asyncio.run(field.on_tap_outside(None))

    assert item_view.title == "Купить хлеб"
    assert app._selected_view is home
    assert app._tap_ended_input is True


def test_back_while_item_input_saves_title_and_keeps_selection(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    fake_focus(monkeypatch)
    asyncio.run(app.add_item(None))
    item_view = home.items[0]
    item_view.input.value = "Купить хлеб"

    asyncio.run(app._on_confirm_pop(None))

    assert item_view.title == "Купить хлеб"
    assert app.storage.item_titles == [(item_view.item.id, "Купить хлеб")]
    assert app._selected_view is home
    assert page.views[0].pops == [False]


def test_item_input_uses_item_text_style():
    item_input = main.create_item_input("Пункт", lambda event: None)
    item_title = main.create_item_title("Пункт")

    assert item_input.text_style == item_title.style == main.ITEM_TITLE_STYLE
    assert item_input.hint_style.size == main.ITEM_TITLE_SIZE
    assert item_input.hint_style.height == main.ITEM_TITLE_LINE_HEIGHT
    assert item_input.dense is True
    assert item_input.autofocus is True


def test_items_are_restored_from_storage_on_mount():
    page = FakePage()
    storage = FakeStorage()
    storage.categories = [category(1, "Дом"), category(2, "Работа")]
    storage.items = [
        item(1, 1, "Помыть посуду"),
        item(2, 1, "Пропылесосить", position=1),
        item(3, 2, "Отчёт", is_checked=True),
    ]
    app = main.ChecklistApp(page, storage=storage, haptic=FakeHaptic())

    asyncio.run(app.mount())

    home, work = app.views
    assert [view.title for view in home.items] == ["Помыть посуду", "Пропылесосить"]
    assert [view.title for view in work.items] == ["Отчёт"]
    assert work.items[0].checkbox.value is True
    assert home.items_box.content.controls == [view.cell for view in home.items]
    assert home.items_box.visible is True


def test_delete_category_drops_item_input_state(monkeypatch):
    """Удаление категории убирает и ввод названия её пункта."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    fake_focus(monkeypatch)
    asyncio.run(app.add_item(None))

    asyncio.run(app.delete_category(None))

    assert app.storage.deleted == [home.category.id]
    assert app._editing_view is None
    assert app.views == [work]
    assert app.button_area.visible is True
    assert page.views[0].can_pop is True


# Выделение пунктов — задача 3 этапа 3.


def make_app_with_items():
    """Приложение «Дом»/«Работа» с двумя пунктами в «Доме»."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    first = home.append_item(item(1, home.category.id, "Молоко"))
    second = home.append_item(item(2, home.category.id, "Хлеб", position=1))
    app.storage.items = [first.item, second.item]
    return page, app, haptic, home, work, first, second


def test_item_selected_color_is_the_category_selected_color():
    """Выделенный пункт красится тем же розовым, что и выделенная категория."""
    assert main.ITEM_PANEL_SELECTED_COLOR == main.CATEGORY_PANEL_SELECTED_COLOR
    assert main.ITEM_PANEL_SELECTED_COLOR == ft.Colors.TERTIARY_CONTAINER


def test_item_row_is_a_gesture_area_around_the_panel():
    page, app, haptic, home, work, first, second = make_app_with_items()

    assert isinstance(first.row, ft.GestureDetector)
    assert first.row.content is first.panel
    assert callable(first.row.on_long_press)
    assert callable(first.row.on_tap)
    # Жесты принадлежат пункту, а не списку: иначе долгое нажатие по пункту
    # начинало бы перетаскивание категории.
    assert first.row is not first.panel


def test_item_set_selected_switches_background():
    page, app, haptic, home, work, first, second = make_app_with_items()

    first.set_selected(True)
    assert first.selected is True
    assert first.panel.bgcolor == main.ITEM_PANEL_SELECTED_COLOR

    first.set_selected(False)
    assert first.selected is False
    assert first.panel.bgcolor == main.ITEM_PANEL_COLOR == ft.Colors.TRANSPARENT


def test_long_press_on_item_selects_it_with_haptic_and_pink_row():
    page, app, haptic, home, work, first, second = make_app_with_items()
    page.updates = 0

    asyncio.run(first.row.on_long_press(None))

    # Выделен именно пункт, а не его категория.
    assert app._selected_item is first
    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert first.selected is True
    assert first.panel.bgcolor == main.ITEM_PANEL_SELECTED_COLOR
    assert second.panel.bgcolor == main.ITEM_PANEL_COLOR
    assert haptic.calls == ["medium_impact"]
    assert page.updates == 1
    # Пока пункт выделен, «назад» перехватывается.
    assert page.views[0].can_pop is False


def test_long_press_on_another_item_moves_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))

    asyncio.run(app._on_item_long_press(second))

    assert app._selected_item is second
    assert first.selected is False
    assert first.panel.bgcolor == main.ITEM_PANEL_COLOR
    assert second.panel.bgcolor == main.ITEM_PANEL_SELECTED_COLOR
    # Виброотклик даётся на каждое выделение, в том числе повторное.
    assert haptic.calls == ["medium_impact", "medium_impact"]


def test_long_press_on_item_clears_category_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)

    asyncio.run(app._on_item_long_press(first))

    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert app._selected_item is first
    assert first.panel.bgcolor == main.ITEM_PANEL_SELECTED_COLOR


def test_tap_on_item_inside_selected_category_selects_it():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)
    page.updates = 0
    haptic.calls.clear()

    asyncio.run(first.row.on_tap(None))

    # Выделение категории сброшено, пункт выделен.
    assert app._selected_view is None
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert app._selected_item is first
    assert first.panel.bgcolor == main.ITEM_PANEL_SELECTED_COLOR
    assert haptic.calls == ["medium_impact"]
    assert page.updates == 1


def test_tap_on_item_of_another_category_deselects_category():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(work)

    asyncio.run(app._on_item_tap(first))

    # Пункт «Дома» не в выделенной категории: тап только снимает выделение.
    assert app._selected_view is None
    assert app._selected_item is None
    assert work.panel.bgcolor == main.CATEGORY_PANEL_COLOR


def test_tap_on_item_without_selection_changes_nothing():
    page, app, haptic, home, work, first, second = make_app_with_items()
    page.updates = 0

    asyncio.run(first.row.on_tap(None))

    assert app._selected_item is None
    assert app._selected_view is None
    assert page.updates == 0


def test_tap_on_selected_item_deselects_it():
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))
    page.updates = 0

    asyncio.run(app._on_item_tap(first))

    assert app._selected_item is None
    assert first.selected is False
    assert first.panel.bgcolor == main.ITEM_PANEL_COLOR
    assert page.updates == 1


def test_tap_on_list_area_deselects_item():
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))
    page.updates = 0

    app.category_area.content.on_tap(None)

    assert app._selected_item is None
    assert first.selected is False
    assert first.panel.bgcolor == main.ITEM_PANEL_COLOR
    assert page.views[0].can_pop is True
    assert page.updates == 1


def test_back_with_item_selection_deselects_without_closing_app():
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))

    asyncio.run(app._on_confirm_pop(None))

    assert app._selected_item is None
    assert first.selected is False
    assert page.views[0].can_pop is True
    # False — не выходить из приложения.
    assert page.views[0].pops == [False]


def test_long_press_on_category_clears_item_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))

    asyncio.run(home.gesture_area.on_long_press(None))

    assert app._selected_item is None
    assert first.selected is False
    assert first.panel.bgcolor == main.ITEM_PANEL_COLOR
    assert app._selected_view is home
    assert home.panel.bgcolor == main.CATEGORY_PANEL_SELECTED_COLOR


def test_buttons_switch_between_category_and_item_selection():
    """При выделении пункта — rename_item/delete_item, и наоборот."""
    page, app, haptic, home, work, first, second = make_app_with_items()

    asyncio.run(app._on_item_long_press(first))

    # Выделен пункт: плюс создаёт категорию, карандаш и корзина — пункт.
    assert app.button_area.visible is True
    assert app.plus_button.visible is True
    assert app.plus_button.on_click == app.create_category
    assert app.plus_button.content.semantics_label == main.LABEL_CREATE_CATEGORY
    assert app.pencil_button.visible is True
    assert app.pencil_button.content.semantics_label == main.LABEL_RENAME_ITEM
    assert app.trash_button.visible is True
    assert app.trash_button.content.semantics_label == main.LABEL_DELETE_ITEM

    app._select_category(work)

    # Выделена категория: слоты снова показывают действия категории.
    assert app._selected_item is None
    assert app.plus_button.content.semantics_label == main.LABEL_ADD_ITEM
    assert app.plus_button.on_click == app.add_item
    assert app.pencil_button.content.semantics_label == main.LABEL_RENAME_CATEGORY
    assert app.trash_button.content.semantics_label == main.LABEL_DELETE_CATEGORY

    app._deselect()

    # Выделения нет: виден только плюс.
    assert app.plus_button.content.semantics_label == main.LABEL_CREATE_CATEGORY
    assert app.pencil_button.visible is False
    assert app.trash_button.visible is False


def test_item_tap_while_editing_title_keeps_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)
    app._begin_title_input(home, home.title)

    asyncio.run(app._on_item_tap(first))

    # Тап лишь запускает завершение ввода, выделение остаётся.
    assert app._selected_view is home
    assert page.tasks == [(app._finish_title_input, (home,))]

    asyncio.run(app._finish_title_input(home))
    assert app._selected_view is home


def test_tap_on_item_that_closes_keyboard_keeps_selection():
    """Тап, закрывший клавиатуру, не должен снимать выделение пункта."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))
    field = app._begin_title_input(home, home.title)

    asyncio.run(field.on_tap_outside(None))
    asyncio.run(app._on_item_tap(first))

    assert app._selected_item is first
    assert first.selected is True
    assert app._tap_ended_input is False


def test_item_long_press_is_ignored_while_title_is_edited():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)
    app._begin_title_input(home, home.title)
    haptic.calls.clear()

    asyncio.run(app._on_item_long_press(first))

    assert app._selected_item is None
    assert app._selected_view is home
    assert haptic.calls == []


def test_delete_category_clears_item_selection_of_its_items():
    """Защита от рассинхронизации: пункт выделен, и его категорию удаляют."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._selected_item = first
    first.set_selected(True)
    app._selected_view = home

    asyncio.run(app.delete_category(None))

    assert app.views == [work]
    assert app._selected_item is None
    assert app._selected_view is None
    assert app.pencil_button.visible is False
    assert page.views[0].can_pop is True


# Перетаскивание пунктов — задача 4 этапа 3.


def measure(app, *, title_height=30.0, item_height=50.0, width=300.0):
    """Проставляет размеры, которые клиент присылает событием size_change."""
    for category in app.views:
        category.title_height = title_height
        category.height = main.category_panel_height(
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


def test_long_press_move_event_is_built_from_client_data():
    """flet 1.1.2 присылает offset_from_origin как "ofo": событие всё равно собирается.

    Без обхода ошибки разбор события падает, и перетаскивание пункта одним
    жестом не работает (проверено на устройстве).
    """
    from flet.utils.from_dict import from_dict

    event = from_dict(
        ft.LongPressMoveUpdateEvent[ft.GestureDetector],
        {
            "control": ft.GestureDetector(),
            "name": "long_press_move_update",
            "l": {"x": 0.0, "y": 10.0},
            "g": {"x": 0.0, "y": 110.0},
            "ofo": {"x": 0.0, "y": 100.0},
            "lofo": {"x": 0.0, "y": 100.0},
        },
    )

    assert event.local_position.y == 10.0
    assert event.global_position.y == 110.0
    assert event.local_offset_from_origin.y == 100.0


def test_base_row_top_follows_the_template():
    metrics = [(30, [50, 60]), (24, [])]

    assert main.base_row_top(metrics, 0, 0) == 66.0
    assert main.base_row_top(metrics, 0, 1) == 120.0


def test_drag_layout_repeats_the_template_with_a_gap():
    spans = main.build_drag_spans(
        [(30, [50, 60])], source=(0, 0), height=50, target=(0, 0)
    )

    span = spans[0]
    assert span.top == main.LIST_PADDING
    assert span.items_top == (
        main.LIST_PADDING
        + main.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + main.CATEGORY_ITEMS_TOP
    )
    # Свёрнутая строка, зазор на её месте, вторая строка.
    assert [entry.row_index for entry in span.entries] == [None, None, 0]
    assert [entry.gap for entry in span.entries] == [False, True, False]
    dragged, gap, second = span.entries
    # Свёрнутая строка не занимает места: зазор встаёт вплотную и занимает целый
    # слот — строку с промежутком после неё (промежуток принадлежит ячейке).
    assert dragged.bottom == dragged.top
    assert gap.top == dragged.top
    assert gap.bottom - gap.top == main.item_slot_height(50)
    assert second.bottom - second.top == 60
    assert second.top == gap.bottom
    # После последней строки — промежуток её ячейки и отступ панели без него.
    assert span.bottom == (
        second.bottom
        + main.ITEM_SPACING
        + main.category_panel_padding(True).bottom
    )
    assert span.row_count == 1


def test_drag_start_does_not_change_the_category_height():
    """В первый миг перетаскивания панель категории не становится выше.

    Свёрнутая строка не занимает места, а зазор на её месте — целый слот пункта
    (`item_slot_height`), поэтому высота панели и места строк совпадают с
    состоянием до подъёма. Раньше промежуток оставался и до свёрнутой строки, и
    после неё: панель вырастала на `ITEM_SPACING`, а пункты под пальцем уезжали
    вниз (видно на устройстве).
    """
    metrics = [(30, [50, 60]), (24, [40])]
    spans = main.build_drag_spans(
        metrics, source=(0, 0), height=50, target=(0, 0)
    )
    items_top = (
        main.LIST_PADDING
        + main.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + main.CATEGORY_ITEMS_TOP
    )

    # Та же высота, что и до подъёма: слоты двух строк и отступ панели.
    assert spans[0].bottom == (
        items_top
        + main.item_slot_height(50)
        + main.item_slot_height(60)
        + main.category_panel_padding(True).bottom
    )
    assert spans[0].bottom == (
        items_top
        + 50
        + main.ITEM_SPACING
        + 60
        + main.CATEGORY_PANEL_VERTICAL_PADDING
    )
    # Следующая категория тоже осталась на своём месте.
    assert spans[1].top == spans[0].bottom + main.CATEGORY_SPACING


def test_moving_the_item_away_leaves_no_extra_height():
    """Перенос пункта не оставляет в исходной категории его высоты.

    Свёрнутая строка не оставляет ни промежутка, ни отступа, поэтому панель
    исходной категории сразу равна категории без этого пункта: после отпускания
    она не «сжимается» на остаток (видно на устройстве).
    """
    metrics = [(30, [50, 60]), (30, [40])]
    spans = main.build_drag_spans(
        metrics, source=(0, 0), height=50, target=(1, 0)
    )
    items_top = (
        main.LIST_PADDING
        + main.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + main.CATEGORY_ITEMS_TOP
    )

    # В исходной категории остался один пункт: ровно его слот и отступы панели.
    assert spans[0].bottom == (
        items_top
        + main.item_slot_height(60)
        + main.category_panel_padding(True).bottom
    )
    # Низ той же категории без перетаскивания — тот же.
    assert spans[0].bottom == (
        items_top + 60 + main.CATEGORY_PANEL_VERTICAL_PADDING
    )
    # Целевая категория выросла ровно на слот пункта.
    original = (
        spans[1].items_top
        + 40
        + main.CATEGORY_PANEL_VERTICAL_PADDING
    )
    assert spans[1].bottom == original + main.item_slot_height(50)


def test_gap_is_a_whole_item_slot():
    """Зазор равен слоту пункта в любой категории: его место занимает ячейка."""
    spans = main.build_drag_spans(
        [(30, [50]), (30, [30, 40])], source=(0, 0), height=50, target=(1, 1)
    )

    gap = next(entry for entry in spans[1].entries if entry.gap)
    assert gap.bottom - gap.top == main.item_slot_height(50)
    # В первой категории осталась только свёрнутая строка: она места не
    # занимает, и панель выглядит как у категории без пунктов.
    assert spans[0].bottom == (
        spans[0].items_top
        - main.CATEGORY_ITEMS_TOP
        + main.CATEGORY_PANEL_VERTICAL_PADDING
    )


def test_drag_layout_moves_the_gap_to_another_category():
    first, second = main.build_drag_spans(
        [(30, [50]), (30, [30, 40])],
        source=(0, 0),
        height=50,
        target=(1, 1),
    )

    # Исходная категория осталась без строк: в ней только свёрнутая строка.
    assert first.row_count == 0
    assert all(not entry.gap for entry in first.entries)
    assert second.row_count == 2
    assert [entry.gap for entry in second.entries] == [False, True, False]
    # Зазор стоит перед второй оставшейся строкой.
    assert second.entries[1].bottom - second.entries[1].top == (
        main.item_slot_height(50)
    )
    assert second.entries[2].row_index == 1


def test_drag_layout_has_no_gap_outside_the_target_category():
    home, work = main.build_drag_spans(
        [(30, [50, 60]), (20, [])],
        source=(0, 0),
        height=50,
        target=(1, 0),
    )

    assert [entry.gap for entry in home.entries] == [False, False]
    assert [entry.gap for entry in work.entries] == [True]
    assert work.row_count == 0


def test_drag_slot_uses_row_midpoints():
    spans = main.build_drag_spans(
        [(30, [50, 50])], source=(0, 0), height=50, target=(0, 0)
    )
    row = spans[0].entries[2]
    middle = (row.top + row.bottom) / 2

    assert row.row_index == 0
    assert main.drag_slot_at(spans, spans[0].items_top) == (0, 0)
    assert main.drag_slot_at(spans, middle - 1) == (0, 0)
    # Палец прошёл середину строки — место вставки за ней.
    assert main.drag_slot_at(spans, middle + 1) == (0, 1)


def test_drag_slot_goes_to_the_nearest_category():
    spans = main.build_drag_spans(
        [(30, [50]), (30, [50])], source=(0, 0), height=50, target=(1, 0)
    )

    assert main.drag_slot_at(spans, -100) == (0, 0)
    assert main.drag_slot_at(spans, 10_000) == (1, 1)


def test_drag_slot_does_not_oscillate_when_the_gap_moves():
    metrics = [(30, [50, 50, 50]), (30, [])]

    for y in (60, 100, 150, 200, 250, 300):
        target = (0, 0)
        for _ in range(5):
            spans = main.build_drag_spans(
                metrics, source=(0, 0), height=50, target=target
            )
            target = main.drag_slot_at(spans, y)
        # После того как зазор встал по этой координате, он там и остаётся.
        spans = main.build_drag_spans(
            metrics, source=(0, 0), height=50, target=target
        )
        assert main.drag_slot_at(spans, y) == target


def test_size_change_feeds_the_drag_model():
    page, app, haptic, home, work, first, second = make_app_with_items()

    first.row.on_size_change(
        ft.LayoutSizeChangeEvent(
            name="size_change", control=first.row, width=311.0, height=42.0
        )
    )
    home.title_slot.on_size_change(
        ft.LayoutSizeChangeEvent(
            name="size_change", control=home.title_slot, width=311.0, height=33.0
        )
    )

    assert (first.width, first.height) == (311.0, 42.0)
    assert home.title_height == 33.0


def test_collapsed_row_ignores_its_zero_size():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)

    first.row.on_size_change(
        ft.LayoutSizeChangeEvent(
            name="size_change", control=first.row, width=300.0, height=0.0
        )
    )

    # Высота 0 — это свёрнутый слот, а не настоящий размер строки.
    assert first.height == 50.0


def test_item_row_handles_drag_gestures():
    page, app, haptic, home, work, first, second = make_app_with_items()

    assert callable(first.row.on_long_press_start)
    assert callable(first.row.on_long_press_move_update)
    assert callable(first.row.on_long_press_end)
    assert callable(first.row.on_long_press_cancel)
    assert callable(first.row.on_size_change)
    assert first.row.content is first.panel


def test_second_long_press_lifts_the_item():
    """Drag начинается вторым нажатием: первое только выделяет пункт."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)

    press_item(first)

    # Первое долгое нажатие выделило пункт и ничего не подняло.
    assert app._item_drag is None
    assert app._selected_item is first
    assert first.panel.height is None
    assert app.stack.controls == [app.category_area, app.button_area]

    press_item(first)

    drag = app._item_drag
    assert drag is not None
    assert drag.view is first
    assert drag.source == (0, 0)
    assert drag.target == (0, 0)
    # Отклик — на оба нажатия: выделение и подъём.
    assert haptic.calls == ["medium_impact", "medium_impact"]
    # Пункт «поднят»: строка свёрнута, над списком её прокси, в списке зазор.
    assert first.panel.height == 0
    assert drag.proxy is not None
    assert app.stack.controls[-1] is drag.proxy
    assert home.gap_index == 0
    # Зазор стоит на месте строки, сама строка свёрнута в тот же слот.
    assert home.items_box.content.controls == [drag.gap, first.cell, second.cell]
    # Выделение категории не начиналось, пункт выделен.
    assert app._selected_item is first
    assert app._selected_view is None


def test_item_drag_needs_the_item_selected_not_the_category():
    """Выделенная категория не заменяет выделение пункта: он не поднимается."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    app._select_category(home)

    press_item(first)

    # Нажатие сняло выделение с категории и выделило пункт, но не подняло его.
    assert app._item_drag is None
    assert app._selected_item is first
    assert app._selected_view is None
    assert first.panel.height is None

    press_item(second)

    # Другой пункт: выделение переехало, подъёма снова нет.
    assert app._item_drag is None
    assert app._selected_item is second
    assert first.panel.height is None
    assert second.panel.height is None


def test_drag_proxy_looks_like_the_dragged_row():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)

    proxy = app._item_drag.proxy
    assert proxy.bgcolor == main.ITEM_PANEL_SELECTED_COLOR
    assert proxy.padding == main.ITEM_PANEL_PADDING
    assert (proxy.width, proxy.height) == (300.0, 50.0)
    assert isinstance(proxy.content, ft.Row)
    # Копия показывает то же название и ту же отметку, что и строка.
    assert proxy.content.controls[0].value is False
    assert proxy.content.controls[1].value == "Молоко"
    # Прокси держится за точку нажатия: его верх — верх строки в модели.
    assert proxy.left == main.LIST_PADDING
    assert proxy.top == 66.0


def test_drag_gap_is_a_whole_item_slot_in_any_category():
    """Зазор — целый слот пункта и в своей категории, и в чужой.

    Свёрнутая строка сворачивает и свою ячейку, поэтому остатка на месте пункта
    нет: зазор занимает ровно то место, которое занимала строка.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    gap = app._item_drag.gap

    assert gap.height == main.item_slot_height(first.height)
    # В своей категории: строка свёрнута вместе с ячейкой.
    assert first.cell.padding is None
    assert home.items_box.padding == main.ITEMS_BOX_PADDING
    drag_item_to(app, first, 200)
    assert work.gap_index == 0
    assert gap.height == main.item_slot_height(first.height)
    drag_item_to(app, first, 80)
    assert home.gap_index == 0
    assert gap.height == main.item_slot_height(first.height)


def test_moving_the_last_item_out_does_not_change_the_category_height():
    """Категория без пунктов не меняет высоту, когда из неё уносят последний пункт.

    Пока пункт «в руке» и зазор уже в чужой категории, в контейнере остаётся
    только свёрнутая строка: она не несёт ни промежутка, ни отступа от названия,
    поэтому панель уже выглядит пустой и после отпускания не сжимается.
    """
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    only = home.append_item(item(1, home.category.id, "Молоко"))
    app.storage.items = [item(1, home.category.id, "Молоко")]
    measure(app)
    pick_up_item(only)

    drag_item_to(app, only, 200)

    assert work.gap_index == 0
    assert home.panel.padding == main.CATEGORY_PANEL_PADDING
    assert home.items_box.visible is True
    assert home.items_box.padding is None

    drop_item(app, only, 200)

    # Высота панели та же: отступы не поменялись.
    assert home.items == []
    assert home.panel.padding == main.CATEGORY_PANEL_PADDING
    assert home.items_box.visible is False
    assert home.items_box.padding is None


def test_drag_proxy_follows_the_finger():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    proxy = app._item_drag.proxy

    drag_to_global(app, first, 400)

    # Палец ушёл на 100 px вниз, прокси — вместе с ним.
    assert proxy.top == 166.0


def test_drag_proxy_keeps_its_column_when_the_finger_moves_sideways():
    """Пункт едет только по вертикали, как панель категории."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    proxy = app._item_drag.proxy

    drag_to_global(app, first, 400, global_x=120)

    # Палец ушёл вбок и вниз: прокси поехал вниз, но остался в своём столбце.
    assert (proxy.left, proxy.top) == (main.LIST_PADDING, 166.0)


def test_sideways_movement_does_not_start_the_drag():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    page.updates = 0
    proxy = app._item_drag.proxy

    drag_to_global(app, first, 300, global_x=200)
    drag_to_global(app, first, 300 + main.ITEM_DRAG_THRESHOLD - 1, global_x=200)

    # Порог считается по вертикальному сдвигу: палец, ушедший вбок, ничего не
    # переставляет и прокси не двигает.
    assert app._item_drag.moved is False
    assert app._item_drag.target == (0, 0)
    assert proxy.top == 66.0
    assert page.updates == 0


def test_long_press_without_sizes_only_selects_the_item():
    """Пока клиент не прислал размеры строк, drag начать нельзя."""
    page, app, haptic, home, work, first, second = make_app_with_items()

    pick_up_item(first)

    assert app._item_drag is None
    assert app._selected_item is first
    assert app.stack.controls == [app.category_area, app.button_area]


def test_drag_is_ignored_while_a_title_is_edited():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    app._select_category(home)
    app._begin_title_input(home, home.title)
    haptic.calls.clear()

    pick_up_item(first)

    assert app._item_drag is None
    assert app._selected_view is home
    assert app._selected_item is None
    assert haptic.calls == []


def test_drag_moves_the_gap_between_rows():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    page.updates = 0

    # Ниже середины второй строки, но ещё внутри панели «Дома».
    drag_item_to(app, first, 170)

    # Вставка в конец категории: зазор стоит последним.
    assert app._item_drag.target == (0, 1)
    assert home.gap_index == 1
    assert home.items_box.content.controls == [
        first.cell,
        second.cell,
        app._item_drag.gap,
    ]
    assert page.updates == 1
    # Движение внутри той же позиции не переставляет зазор.
    drag_item_to(app, first, 175)
    assert app._item_drag.target == (0, 1)
    assert home.gap_index == 1
    assert home.items_box.content.controls == [
        first.cell,
        second.cell,
        app._item_drag.gap,
    ]


def test_drag_moves_the_gap_to_another_category():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(second)

    drag_item_to(app, second, 200)

    assert app._item_drag.target == (1, 0)
    assert work.gap_index == 0
    assert work.items_box.visible is True
    assert work.items_box.content.controls == [app._item_drag.gap]
    # В своей категории зазора больше нет, строки на месте.
    assert home.gap_index is None
    assert home.items_box.content.controls == [first.cell, second.cell]


def test_drag_requires_movement_above_the_threshold():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    page.updates = 0

    drag_item_to(app, first, 66 + main.ITEM_DRAG_THRESHOLD - 1)

    # Дрожание пальца на месте перетаскиванием не считается.
    assert app._item_drag.moved is False
    assert app._item_drag.target == (0, 0)
    assert page.updates == 0


def test_drag_hides_button_area_until_release():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)

    pick_up_item(first)

    assert app.button_area.visible is False
    assert page.views[0].can_pop is False

    drop_item(app, first, 100)

    assert app.button_area.visible is True
    assert app._item_drag is None


def test_drag_within_category_reorders_and_saves():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app.storage.items = [
        item(1, home.category.id, "Молоко", position=0),
        item(2, home.category.id, "Хлеб", position=1),
    ]
    measure(app)
    pick_up_item(first)

    drag_item_to(app, first, 170)
    drop_item(app, first, 170)

    # Первый пункт встал за вторым — и в БД, и на экране.
    assert app.storage.moved_items == [(first.item.id, home.category.id, 1)]
    assert [view.title for view in home.items] == ["Хлеб", "Молоко"]
    assert home.items_box.content.controls == [second.cell, first.cell]
    assert (first.item.position, second.item.position) == (1, 0)
    assert home.gap_index is None
    assert first.panel.height is None
    assert app._selected_item is first
    assert app.button_area.visible is True
    assert app.stack.controls == [app.category_area, app.button_area]


def test_drag_to_the_same_position_does_not_touch_storage():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)

    drag_item_to(app, first, 100)
    drop_item(app, first, 100)

    assert app.storage.moved_items == []
    assert [view.title for view in home.items] == ["Молоко", "Хлеб"]
    assert home.items_box.content.controls == [first.cell, second.cell]
    assert first.panel.height is None


def test_drag_without_movement_does_not_touch_storage():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)

    drop_at_global(app, first, 300)

    assert app.storage.moved_items == []
    assert [view.title for view in home.items] == ["Молоко", "Хлеб"]
    assert app._item_drag is None
    assert first.panel.height is None
    assert app.stack.controls == [app.category_area, app.button_area]


def test_drag_to_another_category_moves_the_item():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app.storage.items = [
        item(1, home.category.id, "Молоко", position=0),
        item(2, home.category.id, "Хлеб", position=1),
    ]
    measure(app)
    pick_up_item(second)

    drag_item_to(app, second, 200)
    drop_item(app, second, 200)

    assert app.storage.moved_items == [(second.item.id, work.category.id, 0)]
    # Пункт сменил категорию: панель «Дома» осталась с одним пунктом.
    assert [view.title for view in home.items] == ["Молоко"]
    assert home.items_box.content.controls == [first.cell]
    assert home.items_box.visible is True
    assert [view.title for view in work.items] == ["Хлеб"]
    assert work.items_box.content.controls == [second.cell]
    assert work.items_box.visible is True
    assert second.category_view is work
    assert (second.item.category_id, second.item.position) == (work.category.id, 0)
    # Выделение пережило перетаскивание: кнопки показывают действия пункта.
    assert app._selected_item is second
    assert app.pencil_button.content.semantics_label == main.LABEL_RENAME_ITEM
    assert app.button_area.visible is True


def test_drag_out_of_the_last_item_hides_the_items_box():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    only = home.append_item(item(1, home.category.id, "Молоко"))
    app.storage.items = [item(1, home.category.id, "Молоко")]
    measure(app)
    pick_up_item(only)

    drag_item_to(app, only, 200)
    drop_item(app, only, 200)

    assert home.items == []
    assert home.items_box.visible is False
    assert home.items_box.content.controls == []
    assert [view.title for view in work.items] == ["Молоко"]
    assert work.items_box.content.controls == [only.cell]


def test_drag_write_error_keeps_order_and_reports():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    app.storage.fail_move_item = True
    pick_up_item(second)

    drag_item_to(app, second, 200)
    drop_item(app, second, 200)

    # Коммит до UI: при ошибке порядок и состав категорий остаются прежними.
    assert app.storage.moved_items == [(second.item.id, work.category.id, 0)]
    assert [view.title for view in home.items] == ["Молоко", "Хлеб"]
    assert work.items == []
    assert second.category_view is home
    assert page.messages == ["Не удалось переместить пункт"]
    assert home.gap_index is None
    assert second.panel.height is None
    assert home.items_box.content.controls == [first.cell, second.cell]
    assert app._selected_item is second
    assert app.button_area.visible is True


def test_drag_cancel_removes_the_proxy_without_saving():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag_item_to(app, first, 200)

    asyncio.run(first.row.on_long_press_cancel(None))

    assert app._item_drag is None
    assert home.gap_index is None
    assert home.items_box.content.controls == [first.cell, second.cell]
    assert first.panel.height is None
    assert app.stack.controls == [app.category_area, app.button_area]
    assert app.storage.moved_items == []
    assert app.button_area.visible is True


def test_tap_after_interrupted_item_drag_clears_it():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag_item_to(app, first, 200)

    app.category_area.content.on_tap(None)

    assert app._item_drag is None
    assert home.gap_index is None
    assert first.panel.height is None
    assert app.button_area.visible is True


def test_gap_is_placed_before_the_given_row():
    page, app, haptic, home, work, first, second = make_app_with_items()
    gap = main.create_item_gap(50)

    home.place_gap(gap, 1)

    assert home.items_box.content.controls == [first.cell, gap, second.cell]
    assert home.gap_index == 1

    # С перетаскиваемой строкой её слот из подсчёта выпадает.
    home.place_gap(gap, 1, first)
    assert home.items_box.content.controls == [first.cell, second.cell, gap]

    home.remove_gap()

    assert home.items_box.content.controls == [first.cell, second.cell]
    assert home.gap_index is None
    assert home.items_box.visible is True


def test_gap_shows_items_box_of_empty_category():
    page, app, haptic, home, work, first, second = make_app_with_items()
    gap = main.create_item_gap(50)
    assert work.items_box.visible is False

    work.place_gap(gap, 0)

    assert work.items_box.visible is True
    assert work.items_box.content.controls == [gap]

    work.remove_gap()

    assert work.items_box.visible is False
    assert work.items_box.content.controls == []


# Перетаскивание категорий: свой жест, прокси, зазор и автопрокрутка по названию.


def test_category_panel_height_follows_the_template():
    """Пустая категория — только название, с пунктами — ещё и их слоты."""
    assert main.category_panel_height(30, []) == (
        30 + 2 * main.CATEGORY_PANEL_VERTICAL_PADDING
    )
    assert main.category_panel_height(30, [50, 50]) == (
        main.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + main.CATEGORY_ITEMS_TOP
        + 2 * main.item_slot_height(50)
        + main.category_panel_padding(True).bottom
    )


def test_category_spans_keep_the_list_height_during_the_drag():
    """Свёрнутый слот и зазор вместе занимают столько же, сколько категория."""
    slots = [60.0, 120.0, 90.0]

    for target in range(3):
        spans = main.build_category_spans(slots, dragged=1, target=target)

        heights = [span.bottom - span.top for span in spans]
        assert sum(heights) == sum(slots)
        gap = next(span for span in spans if span.is_gap)
        assert gap.bottom - gap.top == slots[1]
        assert [span.index for span in spans if not span.is_gap] == [0, 1]
        assert spans[-1].bottom == main.LIST_PADDING + sum(slots)


def test_category_span_uses_panel_midpoints():
    """Категория переставляется, когда палец проходит середину панели."""
    spans = main.build_category_spans([100.0, 100.0, 100.0], dragged=2, target=2)

    assert main.category_span_at(spans, main.LIST_PADDING) == 0
    assert main.category_span_at(spans, main.LIST_PADDING + 49) == 0
    assert main.category_span_at(spans, main.LIST_PADDING + 51) == 1
    assert main.category_span_at(spans, 10_000) == 2


def test_category_span_does_not_oscillate_when_the_gap_moves():
    """Палец, стоящий в зазоре, не переставляет его туда-обратно."""
    slots = [100.0, 100.0, 100.0]

    for target in range(3):
        spans = main.build_category_spans(slots, dragged=1, target=target)
        gap = next(span for span in spans if span.is_gap)

        assert main.category_span_at(spans, (gap.top + gap.bottom) / 2) == target


def test_category_proxy_looks_like_the_panel():
    """Прокси — та же панель в цвете выделения, с названием и пунктами."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)

    proxy = main.create_category_proxy(home, home.width)

    assert proxy.bgcolor == main.CATEGORY_PANEL_SELECTED_COLOR
    assert proxy.width == home.width
    assert proxy.border_radius == main.CATEGORY_PANEL_RADIUS
    assert proxy.padding == home.panel.padding
    gesture_area, items_box = proxy.content.controls
    assert gesture_area.content.value == "Дом"
    assert items_box.visible is True
    assert len(items_box.content.controls) == 2


def test_category_proxy_of_empty_category_has_no_items_box():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)

    proxy = main.create_category_proxy(home, home.width)

    _, items_box = proxy.content.controls
    assert items_box.visible is False
    assert proxy.padding == main.category_panel_padding(False)


def test_drag_start_collapses_the_panel_and_shows_the_proxy():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)

    pick_up_category(app, home)

    drag = app._category_drag
    assert drag is not None
    assert drag.view is home
    assert drag.source == 0
    assert drag.target == 0
    assert home.collapsed is True
    assert home.panel.height == 0
    assert home.item.padding is None
    # Зазор — целый слот категории и стоит на её собственном месте: список не
    # сдвинулся ни на пиксель.
    assert drag.slot_height == home.height + main.CATEGORY_SPACING
    assert home.item.margin is None
    assert work.item.margin == ft.Margin.only(top=drag.slot_height)
    # Прокси выше списка; панель стоит там, где её взял палец (300 - 12).
    assert drag.proxy in app.stack.controls
    assert drag.panel_top == 300.0
    assert drag.proxy.top == 300.0 - drag.origin_y
    assert app._dragging is True
    # Пока категория «в руке», список держит в дереве всё содержимое.
    assert app.category_list.cache_extent is not None


def test_category_proxy_follows_the_finger_vertically():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag

    drag_category_to_screen(app, home, 420)

    assert drag.panel_top == 420.0
    assert drag.proxy.top == drag.panel_top - drag.origin_y
    # По горизонтали категория не едет: прокси в столбце списка.
    assert drag.proxy.left == main.LIST_PADDING


def test_category_drag_moves_the_gap_between_categories():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag

    # Палец прошёл середину «Работы»: зазор встаёт перед «Отдыхом».
    drag_category_to(app, home, 120)

    assert drag.target == 1
    assert home.item.margin is None
    assert work.item.margin is None
    assert rest.item.margin == ft.Margin.only(top=drag.slot_height)


def test_category_drag_puts_the_gap_at_the_end_of_the_list():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag

    drag_category_to(app, home, 10_000)

    assert drag.target == 2
    # Место — конец списка: зазор становится нижним отступом последней панели.
    assert rest.item.margin == ft.Margin.only(bottom=drag.slot_height)


def test_category_drag_restores_everything_after_drop():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    drop_category(app, home, 1000)

    assert app._category_drag is None
    assert home.collapsed is False
    assert home.panel.height is None
    assert home.item.padding == main.CATEGORY_ITEM_PADDING
    assert all(view.item.margin is None for view in app.views)
    assert app.stack.controls == [app.category_area, app.button_area]
    assert app.category_list.cache_extent is None
    # Выделение переживает перетаскивание.
    assert app._selected_view is home


def test_category_drag_cancel_removes_the_proxy_without_saving():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)
    drag_category_to(app, home, 1000)

    asyncio.run(home.gesture_area.on_long_press_cancel(None))

    assert app._category_drag is None
    assert app.stack.controls == [app.category_area, app.button_area]
    assert all(view.item.margin is None for view in app.views)
    assert home.panel.height is None
    assert app.storage.moved == []
    assert app.button_area.visible is True


def test_item_drag_and_category_drag_do_not_start_together():
    """Пока категория «в руке», её пункты не поднимаются, и наоборот."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_category(app, home)

    asyncio.run(
        first.row.on_long_press_start(long_press_start_event(first, global_y=200))
    )

    assert app._item_drag is None
    assert first.collapsed is False

    app._finish_category_drag()
    pick_up_item(first)
    asyncio.run(
        home.gesture_area.on_long_press_start(category_start_event(home, global_y=100))
    )

    assert app._category_drag is None
    assert home.collapsed is False
    assert app._item_drag is not None


class FakeScrollList:
    """Список, который запоминает заказы прокрутки вместо обращения к клиенту."""

    def __init__(self, on_scroll=None):
        self.calls = []
        self._on_scroll = on_scroll

    async def scroll_to(self, **kwargs):
        self.calls.append(kwargs)
        if self._on_scroll is not None:
            self._on_scroll(kwargs)


def scroll_spy(app, on_scroll=None):
    """Подменяет список «шпионом»: в тестах клиента нет, `scroll_to` некуда идти."""
    fake = FakeScrollList(on_scroll)
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


def test_category_autoscroll_ignores_the_long_panel():
    """Автопрокрутку включает название, а не весь прямоугольник категории.

    У длинной категории низ панели уходит за экран, и штатный drag начинал
    прокрутку сразу после подъёма. Здесь панель длиной 700 px стоит так, что её
    низ далеко за нижней границей, а название — в середине экрана: прокрутки нет.
    """
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    home.height = 700.0
    pick_up_category(app, home)
    drag = app._category_drag
    assert drag.origin_y == 284.0

    # Панель начинается на 600: низ (1300) за экраном, название (612..642) —
    # выше нижней зоны (736).
    drag_category_to_screen(app, home, 612)

    assert drag.panel_top == 612.0
    assert drag.autoscroll == 0


def test_category_autoscroll_starts_when_the_title_reaches_the_edge():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    home.height = 700.0
    pick_up_category(app, home)
    drag = app._category_drag

    # Название (748..778) зашло в нижнюю зону: начинается прокрутка вниз.
    drag_category_to_screen(app, home, 748)

    assert drag.autoscroll == 1
    assert page.tasks[-1] == (app._scroll_to_edge, (drag, drag.epoch))

    # Название вернулось в середину экрана — прокрутка встала на месте.
    drag_category_to_screen(app, home, 400)

    assert drag.autoscroll == 0
    assert page.tasks[-1] == (app._cancel_scroll, ())


def test_category_autoscroll_starts_at_the_top_edge_by_the_title():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag
    # Верх названия (100) выше верхней границы зоны (272 + 48).
    drag_category_to_screen(app, home, 100)

    assert drag.autoscroll == -1


def test_category_drag_is_finished_by_a_user_scroll():
    """Список поехал от пальца — жест потерян: перетаскивание снимается."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    app._on_scroll(scroll_event(pixels=50.0, event_type=ft.ScrollType.USER))

    assert app._category_drag is None
    assert app.stack.controls == [app.category_area, app.button_area]
    assert home.panel.height is None
    assert app.storage.moved == []
    assert app.button_area.visible is True


def test_category_autoscroll_pass_is_dropped_when_the_drag_is_over():
    """Проход, заказанный до отпускания, не должен начаться после него."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag
    drag.autoscroll = 1
    spy = scroll_spy(app)
    app._finish_category_drag()

    asyncio.run(app._scroll_to_edge(drag, drag.epoch))

    assert spy.calls == []


def test_autoscroll_starts_near_the_screen_edges():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    # Верх списка на экране — начало координат содержимого (300 - 66).
    assert drag.origin_y == 234.0

    drag_to_global(app, first, 234 + main.AUTOSCROLL_EDGE - 1)

    assert drag.autoscroll == -1
    # Прокрутку заказывает клиент: задача заказывает ей проход до края.
    assert page.tasks[-1] == (app._scroll_to_edge, (drag, drag.epoch))

    # Зона выхода шире зоны входа (AUTOSCROLL_HYSTERESIS): дрожание пальца на
    # самой границе не выключает и не включает прокрутку заново.
    drag_to_global(app, first, 234 + main.AUTOSCROLL_EDGE + main.AUTOSCROLL_HYSTERESIS - 1)
    assert drag.autoscroll == -1

    drag_to_global(app, first, 400)

    assert drag.autoscroll == 0
    # Остановка отменяет анимацию в клиенте: иначе список ехал бы дальше сам.
    assert page.tasks[-1] == (app._cancel_scroll, ())

    # Низ области списка: 800 - 16 (системная навигация) = 784.
    drag_to_global(app, first, 780)

    assert drag.autoscroll == 1


def test_autoscroll_scrolls_and_keeps_the_target_in_sync():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    # Палец чуть ниже строки, но ещё в своей категории.
    drag_item_to(app, first, 140)
    assert app._item_drag.target == (0, 0)

    app._on_scroll(
        ft.OnScrollEvent(
            name="scroll",
            control=app.category_list,
            event_type=ft.ScrollType.UPDATE,
            pixels=100.0,
            min_scroll_extent=0.0,
            max_scroll_extent=500.0,
            viewport_dimension=550.0,
        )
    )

    # Содержимое уехало на 100 px: палец теперь над следующей категорией.
    assert app._scroll_pixels == 100.0
    assert app._viewport == 550.0
    assert app._item_drag.target == (1, 0)
    assert work.gap_index == 0


def test_autoscroll_pass_animates_to_the_list_edge():
    """Клиент едет до самого края списка: цель берётся в момент прокрутки.

    Абсолютная цель (`offset=-1`) не даёт уехать за край, поэтому пружины
    обратно — а именно они дёргали прокрутку у границы — не появляются.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    app._on_scroll(scroll_event(pixels=100.0, max_scroll_extent=700.0))
    drag.autoscroll = 1
    distance = app._autoscroll_distance(drag)
    spy = scroll_spy(app)

    asyncio.run(app._scroll_to_edge(drag, drag.epoch))

    assert len(spy.calls) == 1
    assert spy.calls[0]["offset"] == -1.0
    assert spy.calls[0]["curve"] == ft.AnimationCurve.EASE
    # Длительность — по скорости: медленной связи и «рывкам» тут взяться неоткуда.
    assert spy.calls[0]["duration"] == round(
        distance / main.AUTOSCROLL_SPEED * 1000
    )


def test_autoscroll_pass_goes_up_to_the_list_start():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    app._on_scroll(scroll_event(pixels=300.0, max_scroll_extent=700.0))
    drag.autoscroll = -1
    spy = scroll_spy(app)

    asyncio.run(app._scroll_to_edge(drag, drag.epoch))

    assert spy.calls[0]["offset"] == 0.0
    assert spy.calls[0]["duration"] == round(300 / main.AUTOSCROLL_SPEED * 1000)


def test_autoscroll_does_not_scroll_when_the_list_is_already_at_the_edge():
    """У края списка заказов нет: лишние шаги за край и давали дёрганье."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    # Список уже внизу: и измеренный, и оценённый остаток нулевые.
    app._on_scroll(scroll_event(pixels=5000.0, max_scroll_extent=5000.0))
    drag.autoscroll = 1
    spy = scroll_spy(app)

    asyncio.run(app._scroll_to_edge(drag, drag.epoch))

    assert spy.calls == []


def test_autoscroll_pass_is_dropped_when_the_drag_is_over():
    """Проход, заказанный до остановки, не должен начаться после неё."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    drag.autoscroll = 1
    drag.epoch = 5
    spy = scroll_spy(app)

    asyncio.run(app._scroll_to_edge(drag, 4))

    assert spy.calls == []


def test_autoscroll_animation_stops_on_cancel():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    spy = scroll_spy(app)

    asyncio.run(app._cancel_scroll())

    # Прокрутка на месте: клиент бросает анимацию и остаётся, где стоял.
    assert spy.calls == [{"delta": 0}]


def test_autoscroll_continues_after_a_pass_if_the_list_got_longer():
    """За проход зазор переезжал, конец списка уехал вниз: едем дальше."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    drag.autoscroll = 1
    # Проход начался, когда снизу оставалось 800 px.
    app._on_scroll(
        scroll_event(
            pixels=0.0,
            max_scroll_extent=800.0,
            event_type=ft.ScrollType.START,
        )
    )

    # ...а кончился, когда список стал выше на 100 px.
    app._on_scroll(
        scroll_event(
            pixels=800.0,
            max_scroll_extent=900.0,
            event_type=ft.ScrollType.END,
        )
    )

    assert page.tasks[-1] == (app._scroll_to_edge, (drag, drag.epoch))


def test_autoscroll_does_not_continue_after_a_pass_at_the_edge():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    drag.autoscroll = 1
    app._on_scroll(
        scroll_event(
            pixels=0.0,
            max_scroll_extent=900.0,
            event_type=ft.ScrollType.START,
        )
    )
    tasks_before = len(page.tasks)

    app._on_scroll(
        scroll_event(
            pixels=900.0,
            max_scroll_extent=900.0,
            event_type=ft.ScrollType.END,
        )
    )

    assert len(page.tasks) == tasks_before


def test_autoscroll_does_not_chase_the_list_after_a_lost_gesture():
    """Список отъехал сам, а не вырос: продолжать проход нельзя.

    Иначе после потерянного жеста любой свайп по списку возвращался бы к краю:
    остаток «до края» положителен и тогда, когда список просто увели от края.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    drag.autoscroll = 1
    app._on_scroll(
        scroll_event(
            pixels=0.0,
            max_scroll_extent=900.0,
            event_type=ft.ScrollType.START,
        )
    )
    tasks_before = len(page.tasks)

    # Палец пользователя увёл список на 300 px вверх от края.
    app._on_scroll(
        scroll_event(
            pixels=600.0,
            max_scroll_extent=900.0,
            event_type=ft.ScrollType.END,
        )
    )

    assert len(page.tasks) == tasks_before


def test_user_scroll_finishes_a_lost_item_drag():
    """Жест потерян: пользователь прокручивает список — перетаскивание снимается.

    Пока список двигает пользователь, перетаскивания быть не может: его жест
    ушёл бы в проход автопрокрутки. Без этого прокси висел бы поверх списка до
    первого тапа, а список возвращался бы к краю.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag

    app._on_scroll(
        scroll_event(
            pixels=400.0,
            max_scroll_extent=900.0,
            event_type=ft.ScrollType.USER,
        )
    )

    assert app._item_drag is None
    assert drag.proxy not in app.stack.controls
    assert drag.gap not in work.items_box.content.controls
    assert first.panel.height is None
    # Отменять нечего: список ведёт палец, а не оставшаяся анимация.
    assert not any(handler is app._cancel_scroll for handler, _ in page.tasks)


def test_item_drag_keeps_all_list_rows_built():
    """Пока пункт перетаскивается, список держит в дереве все строки.

    Прокрутка уводит строку за край видимой области, и ленивый список
    уничтожил бы её виджет вместе с распознавателем жеста: движение и отпускание
    пальца перестали бы приходить (проверено на устройстве).
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    assert app.category_list.cache_extent is None

    pick_up_item(first)

    drag = app._item_drag
    assert app.category_list.cache_extent == 2 * (
        app._content_height(drag) + app._list_viewport(drag)
    )
    assert app.category_list.cache_extent > app._content_height(drag)

    drop_item(app, first, 0)

    assert app.category_list.cache_extent is None


def test_autoscroll_distance_is_estimated_before_the_first_scroll():
    """Размеров прокрутки ещё нет: остаток оценивается по раскладке."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    home.title_height = work.title_height = 30.0
    for index in range(20):
        item_view = home.append_item(item(index + 1, home.category.id, f"Пункт {index}"))
        item_view.height, item_view.width = 50.0, 300.0
    pick_up_item(home.items[0])
    drag = app._item_drag
    drag.autoscroll = 1

    assert app._max_scroll_extent is None
    distance = app._autoscroll_distance(drag)

    assert distance > 0
    assert distance == pytest.approx(
        app._content_height(drag) - app._list_viewport(drag)
    )


def test_item_metrics_estimate_unmeasured_sizes():
    """Строки за пределами экрана размеров не шлют: их высота оценивается."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    home.title_height = 40.0
    first = home.append_item(item(1, home.category.id, "Молоко"))
    home.append_item(item(2, home.category.id, "Хлеб", position=1))
    first.height = 60.0

    metrics = app._item_metrics()

    # Вторая строка и название второй категории не измерены — взято среднее.
    assert metrics[0] == (40.0, [60.0, 60.0])
    assert metrics[1] == (40.0, [])


def test_drag_starts_when_only_visible_rows_are_measured():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    first = home.append_item(item(1, home.category.id, "Молоко"))
    home.title_height = 30.0
    first.height, first.width = 50.0, 300.0

    pick_up_item(first)

    # Оценка высот невидимых строк не мешает начать перетаскивание.
    assert app._item_drag is not None
    assert app._item_drag.target == (0, 0)
    assert first.panel.height == 0


# Переименование пункта — задача 5 этапа 3.


def select_item(app, view):
    """Выделяет пункт так же, как пользователь: долгим нажатием."""
    asyncio.run(app._on_item_long_press(view))


def test_pencil_button_renames_item_with_item_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)

    assert app.pencil_button.on_click == app.rename_item
    assert app.pencil_button.content.semantics_label == main.LABEL_RENAME_ITEM


def test_rename_item_opens_input_with_previous_title(monkeypatch):
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_item(None))

    # Текст пункта заменён полем ввода, в поле — прежнее название пункта.
    assert app._editing_view is first
    assert first.input is first.title_slot.content
    assert first.input.value == "Молоко"
    assert first.input.hint_text == domain.DEFAULT_ITEM_TITLE
    assert first.input.text_style == main.ITEM_TITLE_STYLE
    assert focused == [first.input]
    # Пока идёт ввод, кнопки скрыты, «назад» не закрывает приложение.
    assert app.button_area.visible is False
    assert page.views[0].can_pop is False
    assert page.updates >= 1


def test_rename_item_without_item_selection_does_nothing(monkeypatch):
    page, app, haptic, home, work, first, second = make_app_with_items()
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_item(None))

    assert app._editing_view is None
    assert first.title_slot.content is first.title_text
    assert focused == []


def test_rename_item_is_ignored_while_the_category_title_is_edited(monkeypatch):
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(home, home.title)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_item(None))

    assert app._editing_view is home
    assert home.input is field
    assert focused == []


def test_rename_item_saves_title_and_keeps_item_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(first, first.title)

    field.value = "  Молоко и хлеб  "
    asyncio.run(app._finish_title_input(first))

    assert first.title == "Молоко и хлеб"
    assert first.title_text.value == "Молоко и хлеб"
    assert first.title_slot.content is first.title_text
    assert app.storage.item_titles == [(first.item.id, "Молоко и хлеб")]
    # Выделение пункта пережило переименование: слоты остались прежними.
    assert app._selected_item is first
    assert first.selected is True
    assert app._selected_view is None
    assert app.button_area.visible is True
    assert app.pencil_button.on_click == app.rename_item
    assert app.pencil_button.visible is True
    assert app.trash_button.visible is True
    assert page.views[0].can_pop is False


def test_rename_item_with_unchanged_title_does_not_write_to_storage():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(first, first.title)

    field.value = " Молоко "
    asyncio.run(app._finish_title_input(first))

    assert app.storage.item_titles == []
    assert first.title == "Молоко"


def test_rename_item_with_empty_title_uses_default_name():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(first, first.title)

    field.value = "   "
    asyncio.run(app._finish_title_input(first))

    assert first.title == "Пункт"
    assert app.storage.item_titles == [(first.item.id, "Пункт")]


def test_rename_item_write_error_keeps_previous_title_and_reports():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    app.storage.fail_item_title = True
    field = app._begin_title_input(first, first.title)

    field.value = "Хлеб"
    asyncio.run(app._finish_title_input(first))

    # Коммит до UI: при ошибке строка показывает прежнее название.
    assert first.title == "Молоко"
    assert first.title_text.value == "Молоко"
    assert first.title_slot.content is first.title_text
    assert page.messages == ["Не удалось сохранить название"]
    assert app._selected_item is first


def test_back_while_renaming_item_saves_title_and_keeps_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(first, first.title)
    field.value = "Хлеб"

    asyncio.run(app._on_confirm_pop(None))

    assert first.title == "Хлеб"
    assert app.storage.item_titles == [(first.item.id, "Хлеб")]
    assert app._selected_item is first
    # False — не выходить из приложения.
    assert page.views[0].pops == [False]


def test_tap_outside_item_rename_saves_and_keeps_item_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(first, first.title)
    field.value = "Хлеб"

    # Нажатие вне поля: ввод завершается, введённое название сохраняется.
    asyncio.run(field.on_tap_outside(None))
    assert first.title == "Хлеб"
    assert app._tap_ended_input is True

    # Отпускание того же тапа по списку выделение пункта не снимает.
    app.category_area.content.on_tap(None)

    assert app._selected_item is first
    assert first.selected is True
    assert home.selected is False
    assert app._tap_ended_input is False


# Удаление пункта — задача 6 этапа 3.


def test_trash_button_deletes_item_with_item_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)

    assert app.trash_button.on_click == app.delete_item
    assert app.trash_button.content.semantics_label == main.LABEL_DELETE_ITEM


def test_delete_item_removes_selected_item_from_list_and_storage():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)

    asyncio.run(app.delete_item(None))

    # Пункт удалён из БД и из строк категории, порядок взят из хранилища.
    assert app.storage.deleted_items == [first.item.id]
    assert [view.title for view in home.items] == ["Хлеб"]
    assert home.items_box.content.controls == [second.cell]
    assert home.items_box.visible is True
    # Выделение снято: кнопки вернулись к исходному составу.
    assert app._selected_item is None
    assert first.selected is False
    assert app._selected_view is None
    assert app.button_area.visible is True
    assert app.plus_button.on_click == app.create_category
    assert app.pencil_button.visible is False
    assert app.trash_button.visible is False
    assert app.trash_button.on_click == app.delete_category
    assert page.views[0].can_pop is True


def test_delete_item_keeps_items_of_other_categories():
    page, app, haptic, home, work, first, second = make_app_with_items()
    report = work.append_item(item(3, work.category.id, "Отчёт"))
    select_item(app, first)

    asyncio.run(app.delete_item(None))

    assert [view.title for view in home.items] == ["Хлеб"]
    assert [view.title for view in work.items] == ["Отчёт"]
    assert work.items_box.content.controls == [report.cell]


def test_delete_item_without_item_selection_does_nothing():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)

    asyncio.run(app.delete_item(None))

    assert app.storage.deleted_items == []
    assert [view.title for view in home.items] == ["Молоко", "Хлеб"]
    assert home.items_box.visible is True


def test_delete_item_write_error_keeps_item_and_reports():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    app.storage.fail_delete_item = True

    asyncio.run(app.delete_item(None))

    # Коммит до UI: при ошибке строка и выделение остаются прежними.
    assert [view.title for view in home.items] == ["Молоко", "Хлеб"]
    assert home.items_box.content.controls == [first.cell, second.cell]
    assert app._selected_item is first
    assert first.selected is True
    assert page.messages == ["Не удалось удалить пункт"]
    assert app.trash_button.on_click == app.delete_item


def test_delete_last_item_hides_the_items_box():
    page, app, haptic, (home,) = make_app("Дом")
    only = home.append_item(item(1, home.category.id, "Молоко"))
    app.storage.items = [only.item]
    select_item(app, only)

    asyncio.run(app.delete_item(None))

    assert home.items == []
    assert home.items_box.content.controls == []
    assert home.items_box.visible is False
    # Панель снова выглядит как категория без пунктов.
    assert home.panel.padding == main.CATEGORY_PANEL_PADDING


def test_delete_item_drops_its_input_state():
    """Удаление пункта убирает и ввод его названия (страховка от рассинхронизации)."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)
    field = app._begin_title_input(first, first.title)

    asyncio.run(app.delete_item(None))

    assert field.value == "Молоко"
    assert app._editing_view is None
    assert app._selected_item is None
    assert [view.title for view in home.items] == ["Хлеб"]
    assert app.button_area.visible is True
    assert page.views[0].can_pop is True

