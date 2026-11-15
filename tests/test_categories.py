"""Категории: выделение, ввод названия, переименование, удаление и
перетаскивание, а также пункты внутри панели."""

import asyncio

import flet as ft

import domain
import storage
from support import (
    FakePage,
    FakeStorage,
    category_end_event,
    category_start_event,
    commit_title,
    drop_category,
    fake_focus,
    make_app,
    measure,
    pick_up_category,
    scroll_spy,
    slot_actions,
    start_rename,
)
from ui import theme
from ui.app import ChecklistApp
from ui.controls import create_category_input
from ui.views import CategoryView


def test_category_view_starts_with_title_text():
    view = CategoryView(category=domain.Category(id=1, title="Дом", position=0))

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
    assert view.title_slot.padding == theme.CATEGORY_TITLE_PADDING


def test_category_view_without_handlers_ignores_gestures():
    """Вид можно собрать отдельно от приложения: без обработчиков жесты молчат."""
    view = CategoryView(category=domain.Category(id=1, title="Дом", position=0))

    asyncio.run(view.gesture_area.on_long_press(None))
    asyncio.run(view.gesture_area.on_long_press_start(category_start_event(view)))

    assert view.selected is False
    assert view.collapsed is False


def test_buttons_hide_while_editing_title():
    """Во время ввода кнопки button_area не показываются, после — возвращаются."""
    page = FakePage()
    storage = FakeStorage()
    app = ChecklistApp(page, storage=storage)
    view = CategoryView(domain.Category(id=1, title="Дом", position=0))

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
    app = ChecklistApp(page, storage=FakeStorage())
    first = CategoryView(domain.Category(id=1, title="Дом", position=0))
    second = CategoryView(domain.Category(id=2, title="Работа", position=1))
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

    drop_category(app, home, theme.LIST_PADDING)

    assert app._dragging is False
    assert app.button_area.visible is True
    # Выделение пережило drag: слоты показывают действия выделенной категории.
    assert app._selected_view is home
    assert app.plus_button.content.semantics_label == theme.LABEL_ADD_ITEM
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
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_SELECTED_COLOR
    assert work.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
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
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
    assert work.panel.bgcolor == theme.CATEGORY_PANEL_SELECTED_COLOR
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

    drop_category(app, work, theme.LIST_PADDING)

    # Выделение переживает перетаскивание.
    assert app._selected_view is work
    assert [view.title for view in app.views] == ["Работа", "Дом", "Отдых"]
    assert app.storage.moved == [(work.category.id, 0)]


def test_category_drag_to_the_same_position_does_not_touch_storage():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    drop_category(app, home, theme.LIST_PADDING)

    assert app.storage.moved == []
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_category_drag_without_movement_does_not_touch_storage():
    """Жест без движения — это выделение, а не перетаскивание."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    asyncio.run(home.gesture_area.on_long_press_end(category_end_event(home, 300)))

    assert app.storage.moved == []
    assert [view.title for view in app.views] == ["Дом", "Работа"]


def test_category_drag_write_error_keeps_order_and_reports():
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
    assert slot_actions(app) == [
        (theme.LABEL_CREATE_CATEGORY, app.create_category, True),
        (theme.LABEL_RENAME_CATEGORY, app.rename_category, False),
        (theme.LABEL_DELETE_CATEGORY, app.delete_category, False),
    ]

    app._select_category(home)

    # Выделена категория: плюс добавляет пункт, карандаш и корзина — категорию.
    assert slot_actions(app) == [
        (theme.LABEL_ADD_ITEM, app.add_item, True),
        (theme.LABEL_RENAME_CATEGORY, app.rename_category, True),
        (theme.LABEL_DELETE_CATEGORY, app.delete_category, True),
    ]

    app._deselect()

    assert slot_actions(app) == [
        (theme.LABEL_CREATE_CATEGORY, app.create_category, True),
        (theme.LABEL_RENAME_CATEGORY, app.rename_category, False),
        (theme.LABEL_DELETE_CATEGORY, app.delete_category, False),
    ]


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
    assert app.plus_button.content.src == theme.ICON_PLUS
    assert app.pencil_button.content.src == theme.ICON_PENCIL
    assert app.trash_button.content.src == theme.ICON_TRASH


def test_tap_on_list_deselects_category():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    page.updates = 0

    app.category_area.content.on_tap(None)

    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
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
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
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
    app = ChecklistApp(page, storage=FakeStorage())

    asyncio.run(app.mount())

    assert isinstance(app.haptic, ft.HapticFeedback)
    assert page.services == [app.haptic]
    assert page.views[0].on_confirm_pop == app._on_confirm_pop


def test_category_input_for_rename_is_prefilled_and_taps_outside_separately():
    def on_commit(event):
        pass

    def on_tap_outside(event):
        pass

    category_input = create_category_input(
        "Категория", on_commit, "Работа", on_tap_outside
    )

    # Прежнее название — начальное значение поля, а не подсказка.
    assert category_input.value == "Работа"
    assert category_input.on_submit is on_commit
    assert category_input.on_blur is on_commit
    assert category_input.on_tap_outside is on_tap_outside


def test_list_tap_area_forwards_the_tap_cancel():
    page, app, haptic, views = make_app("Дом")

    assert app.category_area.content.on_tap_cancel == app._on_tap_cancel


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
    field = start_rename(app, work)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.rename_category(None))

    assert app._editing_view is work
    assert work.input is field
    assert focused == []


def test_rename_saves_title_and_keeps_selection():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)

    commit_title(app, home, "Квартира")

    assert home.title == "Квартира"
    assert home.title_text.value == "Квартира"
    assert home.title_slot.content is home.title_text
    assert app.storage.saved == [(home.category.id, "Квартира")]
    # Выделение пережило переименование: слоты остались прежними.
    assert app._selected_view is home
    assert home.selected is True
    assert app.button_area.visible is True
    assert slot_actions(app) == [
        (theme.LABEL_ADD_ITEM, app.add_item, True),
        (theme.LABEL_RENAME_CATEGORY, app.rename_category, True),
        (theme.LABEL_DELETE_CATEGORY, app.delete_category, True),
    ]
    assert page.views[0].can_pop is False


def test_keyboard_action_commits_the_title():
    """Кнопка действия клавиатуры и потеря фокуса сохраняют название один раз."""
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = start_rename(app, home)
    field.value = "Квартира"

    asyncio.run(field.on_submit(None))

    assert home.title == "Квартира"
    assert app.storage.saved == [(home.category.id, "Квартира")]
    assert home.title_slot.content is home.title_text

    # on_blur приходит после on_submit — второй записи нет.
    asyncio.run(field.on_blur(None))
    assert app.storage.saved == [(home.category.id, "Квартира")]

    # Тап вне поля после закрытия ввода — уже не «тот же тап»: флага нет.
    asyncio.run(field.on_tap_outside(None))
    assert app._tap_ended_input is False


def test_rename_with_unchanged_title_does_not_write_to_storage():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)

    commit_title(app, home, " Дом ")

    assert app.storage.saved == []
    assert home.title == "Дом"


def test_rename_with_empty_title_uses_default_name():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)

    commit_title(app, home, "   ")

    assert home.title == "Категория"
    assert app.storage.saved == [(home.category.id, "Категория")]


def test_rename_write_error_keeps_previous_title_and_reports():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    app.storage.fail_save = True

    commit_title(app, home, "Квартира")

    # Коммит до UI: при ошибке панель показывает прежнее название.
    assert home.title == "Дом"
    assert home.title_text.value == "Дом"
    assert home.title_slot.content is home.title_text
    assert page.messages == ["Не удалось сохранить название"]
    assert app._selected_view is home


def test_back_while_renaming_saves_title_and_keeps_selection():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = start_rename(app, home)
    field.value = "Квартира"

    asyncio.run(app._on_confirm_pop(None))

    assert home.title == "Квартира"
    assert app.storage.saved == [(home.category.id, "Квартира")]
    assert app._selected_view is home
    # False — не выходить из приложения.
    assert page.views[0].pops == [False]


def test_back_while_creating_category_saves_title_without_closing_app():
    page, app, haptic, views = make_app("Дом")
    new_view = CategoryView(
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
    field = start_rename(app, home)
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
    field = start_rename(app, home)

    asyncio.run(field.on_tap_outside(None))
    app.category_area.content.on_tap(None)  # тап, закрывший клавиатуру

    app.category_area.content.on_tap(None)  # новый тап по списку

    assert app._selected_view is None
    assert home.selected is False


def test_tap_cancel_clears_the_keyboard_closing_tap_flag():
    """Тап вне поля стал прокруткой: флаг не должен съесть следующий тап."""
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = start_rename(app, home)

    asyncio.run(field.on_tap_outside(None))
    app.category_area.content.on_tap_cancel(None)
    app.category_area.content.on_tap(None)

    assert app._selected_view is None
    assert app._tap_ended_input is False


def test_list_tap_while_editing_saves_title_without_deselecting():
    page, app, haptic, (home,) = make_app("Дом")
    app._select_category(home)
    field = start_rename(app, home)
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
    assert slot_actions(app) == [
        (theme.LABEL_CREATE_CATEGORY, app.create_category, True),
        (theme.LABEL_RENAME_CATEGORY, app.rename_category, False),
        (theme.LABEL_DELETE_CATEGORY, app.delete_category, False),
    ]
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
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_SELECTED_COLOR
    assert app.trash_button.visible is True
    assert page.messages == ["Не удалось удалить категорию"]


def test_delete_while_editing_title_drops_input_state():
    """Ввод и та же категория: поле уходит вместе с панелью, кнопки — назад."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    app._select_category(home)
    start_rename(app, home)

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
    field = start_rename(app, home)

    asyncio.run(app.delete_category(None))
    field.value = "Квартира"
    asyncio.run(app._finish_title_input(home))

    assert app.storage.saved == []
    assert app.views == [work]


# Создание категории — кнопка «плюс», когда ничего не выделено.


def test_create_category_appends_panel_and_opens_input(monkeypatch):
    page, app, haptic, (home,) = make_app("Дом")
    # Новую категорию надо доскроллить: список остаётся на прежнем месте.
    category_list = scroll_spy(app)
    focused = fake_focus(monkeypatch)

    asyncio.run(app.create_category(None))

    # Категория создана в БД и добавлена в конец списка на экране.
    assert [item.title for item in app.storage.categories] == ["Дом", "Категория"]
    assert [view.title for view in app.views] == ["Дом", "Категория"]
    created = app.views[-1]
    assert category_list.controls == [home.item, created.item]
    assert category_list.calls == [{"offset": -1}]
    # На месте названия — пустое поле с подсказкой «Категория».
    assert app._editing_view is created
    assert created.input is created.title_slot.content
    assert created.input.value == ""
    assert created.input.hint_text == domain.DEFAULT_CATEGORY_TITLE
    assert focused == [created.input]
    # Пока идёт ввод, кнопки скрыты, «назад» не закрывает приложение.
    assert app.button_area.visible is False
    assert page.views[0].can_pop is False


def test_create_category_saves_entered_title(monkeypatch):
    page, app, haptic, views = make_app("Дом")
    scroll_spy(app)
    fake_focus(monkeypatch)
    asyncio.run(app.create_category(None))
    created = app.views[-1]

    commit_title(app, created, "  Отдых  ")

    assert created.title == "Отдых"
    assert created.title_text.value == "Отдых"
    assert created.title_slot.content is created.title_text
    assert app.storage.saved == [(created.category.id, "Отдых")]
    assert app.button_area.visible is True
    assert page.views[0].can_pop is True


def test_create_category_write_error_adds_nothing_and_reports():
    page, app, haptic, (home,) = make_app("Дом")
    app.storage.fail_create_category = True

    asyncio.run(app.create_category(None))

    # Коммит до UI: при ошибке новой панели нет, поле не открывается.
    assert app.views == [home]
    assert app._editing_view is None
    assert app.button_area.visible is True
    assert page.messages == ["Не удалось создать категорию"]
