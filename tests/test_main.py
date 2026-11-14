import asyncio
from pathlib import Path

import flet as ft

import domain
import main
import storage


def test_app_module_is_importable():
    assert callable(main.main)


def test_button_area_is_pinned_to_bottom_right():
    button_area = main.create_button_area()

    assert button_area.right == main.BUTTON_AREA_MARGIN
    assert button_area.bottom == main.BUTTON_AREA_MARGIN


def test_button_area_has_category_buttons():
    buttons = main.create_button_area().content.controls

    assert [button.content.src for button in buttons] == [
        main.ICON_PLUS,
        main.ICON_PENCIL,
        main.ICON_TRASH,
    ]
    for button in buttons:
        assert button.width == main.BUTTON_SIZE
        assert button.height == main.BUTTON_SIZE
        assert button.border_radius == main.BUTTON_SIZE / 2


def test_buttons_are_clickable_with_ink_ripple():
    for button in main.create_button_area().content.controls:
        assert button.ink is True
        assert callable(button.on_click)


def test_create_button_runs_given_handler():
    events = []
    button_area = main.create_button_area(lambda event: events.append(event))
    create_category = button_area.content.controls[0]

    create_category.on_click(None)

    assert len(events) == 1


def test_button_icons_exist_in_assets():
    assets_dir = Path(__file__).parent.parent / "src" / "assets"

    for icon in (main.ICON_PLUS, main.ICON_PENCIL, main.ICON_TRASH):
        assert (assets_dir / icon).is_file()


def test_category_panel_is_rectangular_with_title_on_top():
    panel = main.create_category_panel("Работа")

    assert isinstance(panel, ft.Container)
    assert panel.content.value == "Работа"
    assert panel.content.style == main.CATEGORY_TITLE_STYLE
    assert panel.bgcolor == main.CATEGORY_PANEL_COLOR
    assert panel.border_radius == main.CATEGORY_PANEL_RADIUS
    assert panel.padding == main.CATEGORY_PANEL_PADDING


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
        self.categories = []
        self.fail_move = False
        self.recovered_backup = None

    def list_categories(self):
        return list(self.categories)

    def set_category_title(self, category_id, title):
        self.saved.append((category_id, title))
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
    assert view.panel.content is view.title_text
    assert view.is_editing is False


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


def test_selection_swaps_button_area_buttons():
    page, app, haptic, (home,) = make_app("Дом")

    # Ничего не выделено: видна только кнопка создания.
    assert app.create_button.visible is True
    assert app.rename_button.visible is False
    assert app.delete_button.visible is False

    app._select_category(home)

    assert app.create_button.visible is False
    assert app.rename_button.visible is True
    assert app.delete_button.visible is True

    app._deselect()

    assert app.create_button.visible is True
    assert app.rename_button.visible is False
    assert app.delete_button.visible is False


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

