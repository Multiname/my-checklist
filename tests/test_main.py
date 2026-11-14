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
    assert item.padding == ft.Padding.only(bottom=main.CATEGORY_SPACING)
    assert item.bgcolor is None


def test_category_area_makes_the_drag_proxy_invisible():
    """Прокси ReorderableListView — Material: у него не должно быть фона и тени.

    Иначе при перетаскивании вокруг панели виден светлый прямоугольник и белые
    углы за скруглениями. Тема вложена в область списка, поэтому прокси,
    смонтированный в overlay, наследует её у элемента.
    """
    category_list = main.create_category_list()

    category_area = main.create_category_area(category_list, lambda event: None)

    assert category_area.theme is main.LIST_THEME
    assert main.LIST_THEME.canvas_color == ft.Colors.TRANSPARENT
    assert main.LIST_THEME.color_scheme.shadow == ft.Colors.TRANSPARENT
    assert main.LIST_THEME.color_scheme.surface_tint == ft.Colors.TRANSPARENT
    # Роли цветовой схемы не переопределяются: панель остаётся прежнего цвета.
    assert main.LIST_THEME.color_scheme.surface_container_high is None


def test_category_list_scrolls_full_screen_above_button_area():
    category_list = main.create_category_list()

    assert isinstance(category_list, ft.ReorderableListView)
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
        self.deleted = []
        self.categories = []
        self.created_items = []
        self.item_titles = []
        self.items = []
        self.fail_move = False
        self.fail_save = False
        self.fail_delete = False
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


def reorder_start(app, index):
    """Событие ReorderableListView: долгое нажатие начало перетаскивание."""
    return ft.OnReorderEvent(
        name="reorder_start", control=app.category_list, old_index=index
    )


def reorder(app, old_index, new_index):
    """Событие ReorderableListView: категорию отпустили на новом месте."""
    return ft.OnReorderEvent(
        name="reorder",
        control=app.category_list,
        old_index=old_index,
        new_index=new_index,
    )


def reorder_end(app, new_index=0):
    """Событие ReorderableListView: палец отпущен, drag закончен."""
    return ft.OnReorderEvent(
        name="reorder_end", control=app.category_list, new_index=new_index
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
    # Панель: название сверху, под ним — контейнер пунктов.
    title_slot, items_box = view.panel.content.controls
    assert title_slot is view.title_slot
    assert items_box is view.items_box
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
    """Перетаскивание выполняет сам список: элементами служат обёртки категорий."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    assert app.category_list.controls == [home.item, work.item]
    assert home.item.content is home.panel
    assert work.item.content is work.panel


def test_reorder_events_are_handled_by_the_list():
    page, app, haptic, views = make_app()

    assert app.category_list.on_reorder_start == app._on_reorder_start
    assert app.category_list.on_reorder == app._on_reorder
    assert app.category_list.on_reorder_end == app._on_reorder_end


def test_drag_hides_button_area_and_returns_it():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(work)
    assert app.button_area.visible is True

    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

    # Пока категорию перетаскивают, кнопок не видно.
    assert app._dragging is True
    assert app.button_area.visible is False

    app._on_reorder_end(reorder_end(app))

    assert app._dragging is False
    assert app.button_area.visible is True
    # Выделение пережило drag: слоты показывают действия выделенной категории.
    assert app._selected_view is home
    assert app.plus_button.content.semantics_label == main.LABEL_ADD_ITEM
    assert app.pencil_button.visible is True
    assert app.trash_button.visible is True


def test_drag_with_new_order_restores_button_area():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

    app._on_reorder_end(reorder_end(app))
    asyncio.run(app._on_reorder(reorder(app, 0, 1)))

    assert app.button_area.visible is True
    assert [view.title for view in app.views] == ["Работа", "Дом"]


def test_tap_after_interrupted_drag_returns_button_area():
    """Если система прервала жест, on_reorder_end не придёт — кнопки вернёт тап."""
    page, app, haptic, (home,) = make_app("Дом")
    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

    app.category_area.content.on_tap(None)

    assert app._dragging is False
    assert app.button_area.visible is True


def test_list_tap_area_wraps_category_list():
    page, app, haptic, views = make_app()

    assert app.category_area.content.content is app.category_list
    assert app.category_area.content.on_tap == app._on_tap


def test_long_press_selects_category_with_haptic_and_color():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    # Долгое нажатие сразу начинает drag: выделение приходит от списка.
    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

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
    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

    asyncio.run(app._on_reorder_start(reorder_start(app, 1)))

    assert app._selected_view is work
    assert home.selected is False
    assert home.panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert work.panel.bgcolor == main.CATEGORY_PANEL_SELECTED_COLOR
    # Виброотклик даётся на каждый начатый drag.
    assert haptic.calls == ["medium_impact", "medium_impact"]


def test_repeated_long_press_keeps_single_selection_and_vibrates():
    """Повторное долгое нажатие — это новое перетаскивание, отклик нужен снова."""
    page, app, haptic, (home,) = make_app("Дом")

    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))
    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

    assert app._selected_view is home
    assert haptic.calls == ["medium_impact", "medium_impact"]


def test_reorder_start_with_unknown_index_changes_nothing():
    page, app, haptic, (home,) = make_app("Дом")

    asyncio.run(app._on_reorder_start(reorder_start(app, 5)))

    assert app._selected_view is None
    assert haptic.calls == []


def test_reorder_moves_category_and_saves_order():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")

    asyncio.run(app._on_reorder(reorder(app, 0, 2)))

    assert [view.title for view in app.views] == ["Работа", "Отдых", "Дом"]
    assert app.category_list.controls == [view.item for view in app.views]
    assert app.storage.moved == [(home.category.id, 2)]
    # Позиции обновляются по порядку из БД.
    assert [(view.category.title, view.category.position) for view in app.views] == [
        ("Работа", 0),
        ("Отдых", 1),
        ("Дом", 2),
    ]


def test_reorder_updates_the_order_in_place_after_drop():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    asyncio.run(app._on_reorder_start(reorder_start(app, 1)))

    asyncio.run(app._on_reorder(reorder(app, 1, 0)))

    # Выделение переживает перетаскивание.
    assert app._selected_view is work
    assert [view.title for view in app.views] == ["Работа", "Дом", "Отдых"]
    assert app.storage.moved == [(work.category.id, 0)]


def test_reorder_to_the_same_position_does_not_touch_storage():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    asyncio.run(app._on_reorder(reorder(app, 0, 0)))

    assert app.storage.moved == []
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_reorder_with_unknown_index_does_not_touch_storage():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    asyncio.run(app._on_reorder(reorder(app, 5, 0)))

    assert app.storage.moved == []
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_reorder_write_error_keeps_list_and_reports():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app.storage.fail_move = True

    asyncio.run(app._on_reorder(reorder(app, 0, 1)))

    # Экран уже показывает новый порядок — список в памяти повторяет его.
    assert [view.title for view in app.views] == ["Работа", "Дом"]
    assert page.messages == ["Не удалось сохранить порядок категорий"]


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
        item_view.row for item_view in view.items
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
    assert home.items_box.content.controls == [home.items[0].row]
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
    assert home.items_box.content.controls[-1] is home.items[-1].row


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
    assert home.items_box.content.controls == [view.row for view in home.items]
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

    asyncio.run(app._on_reorder_start(reorder_start(app, 0)))

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


