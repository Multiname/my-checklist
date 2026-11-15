"""Пункты: шаблон строки, добавление, выделение, переименование и
удаление."""

import asyncio

import flet as ft

import domain
import storage
from support import (
    FakeHaptic,
    FakePage,
    FakeStorage,
    category,
    fake_focus,
    item,
    make_app,
    make_app_with_items,
    select_item,
)
from ui import theme
from ui.app import ChecklistApp
from ui.controls import (
    category_panel_padding,
    create_item_input,
    create_item_panel,
    create_item_title,
)
from ui.views import CategoryView


def test_item_panel_has_checkbox_on_the_left_and_transparent_background():
    checkbox = ft.Checkbox()
    title = create_item_title("Помыть посуду")

    panel = create_item_panel(checkbox, title)

    assert isinstance(panel, ft.Container)
    # Фон прозрачный: сквозь пункт видна панель категории.
    assert panel.bgcolor == theme.ITEM_PANEL_COLOR == ft.Colors.TRANSPARENT
    # Горизонтальный отступ — у пункта, а не у панели: выделенная строка
    # закрашивает всю ширину панели.
    assert panel.padding == theme.ITEM_PANEL_PADDING
    assert panel.padding.left == theme.ITEM_PANEL_PADDING.right == 16
    assert panel.padding.top == panel.padding.bottom == 0
    assert panel.content.controls[0] is checkbox
    assert panel.content.controls[1] is title
    assert panel.content.vertical_alignment == ft.CrossAxisAlignment.CENTER


def test_item_text_is_smaller_than_category_title():
    item_title = create_item_title("Пункт")

    assert item_title.style == theme.ITEM_TITLE_STYLE
    assert item_title.max_lines == 2
    assert theme.ITEM_TITLE_SIZE < theme.CATEGORY_TITLE_SIZE
    assert theme.ITEM_TITLE_WEIGHT == ft.FontWeight.NORMAL


def test_empty_category_has_hidden_items_box():
    view = CategoryView(category(1, "Дом"))

    assert view.items == []
    assert view.items_box.visible is False
    assert view.items_box.content.controls == []


def test_category_view_keeps_items_inside_its_items_box():
    view = CategoryView(
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
    # Чекбокс закрыт прозрачным слоем-перехватчиком: до него тап не доходит,
    # пока что-то выделено (см. «Отметка пункта»).
    assert first.panel.content.controls[0] is first.checkbox_area
    assert first.checkbox_area.controls == [first.checkbox, first.checkbox_blocker]
    assert first.checkbox_blocker.visible is False
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
    view = CategoryView(
        category(1, "Дом"),
        [item(1, 1, "Помыть посуду"), item(2, 1, "Пропылесосить", position=1)],
    )
    first = view.items[0]

    assert view.items_box.content.spacing == 0
    assert first.cell.content is first.row
    assert first.cell.padding == theme.ITEM_CELL_PADDING
    # Промежуток последней ячейки компенсируется нижним отступом панели.
    assert view.panel.padding == category_panel_padding(True)
    assert view.panel.padding.bottom == (
        theme.CATEGORY_PANEL_VERTICAL_PADDING - theme.ITEM_SPACING
    )
    # Категория без пунктов ничего не компенсирует.
    empty = CategoryView(category(2, "Работа"))
    assert empty.panel.padding == theme.CATEGORY_PANEL_PADDING


def test_item_checkbox_shows_mark_saved_in_storage():
    view = CategoryView(
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
    item_input = create_item_input("Пункт", lambda event: None)
    item_title = create_item_title("Пункт")

    assert item_input.text_style == item_title.style == theme.ITEM_TITLE_STYLE
    assert item_input.hint_style.size == theme.ITEM_TITLE_SIZE
    assert item_input.hint_style.height == theme.ITEM_TITLE_LINE_HEIGHT
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
    app = ChecklistApp(page, storage=storage, haptic=FakeHaptic())

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


def test_item_selected_color_is_the_category_selected_color():
    """Выделенный пункт красится тем же розовым, что и выделенная категория."""
    assert theme.ITEM_PANEL_SELECTED_COLOR == theme.CATEGORY_PANEL_SELECTED_COLOR
    assert theme.ITEM_PANEL_SELECTED_COLOR == ft.Colors.TERTIARY_CONTAINER


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
    assert first.panel.bgcolor == theme.ITEM_PANEL_SELECTED_COLOR

    first.set_selected(False)
    assert first.selected is False
    assert first.panel.bgcolor == theme.ITEM_PANEL_COLOR == ft.Colors.TRANSPARENT


def test_long_press_on_item_selects_it_with_haptic_and_pink_row():
    page, app, haptic, home, work, first, second = make_app_with_items()
    page.updates = 0

    asyncio.run(first.row.on_long_press(None))

    # Выделен именно пункт, а не его категория.
    assert app._selected_item is first
    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
    assert first.selected is True
    assert first.panel.bgcolor == theme.ITEM_PANEL_SELECTED_COLOR
    assert second.panel.bgcolor == theme.ITEM_PANEL_COLOR
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
    assert first.panel.bgcolor == theme.ITEM_PANEL_COLOR
    assert second.panel.bgcolor == theme.ITEM_PANEL_SELECTED_COLOR
    # Виброотклик даётся на каждое выделение, в том числе повторное.
    assert haptic.calls == ["medium_impact", "medium_impact"]


def test_long_press_on_item_clears_category_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)

    asyncio.run(app._on_item_long_press(first))

    assert app._selected_view is None
    assert home.selected is False
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
    assert app._selected_item is first
    assert first.panel.bgcolor == theme.ITEM_PANEL_SELECTED_COLOR


def test_tap_on_item_inside_selected_category_selects_it():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(home)
    page.updates = 0
    haptic.calls.clear()

    asyncio.run(first.row.on_tap(None))

    # Выделение категории сброшено, пункт выделен.
    assert app._selected_view is None
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_COLOR
    assert app._selected_item is first
    assert first.panel.bgcolor == theme.ITEM_PANEL_SELECTED_COLOR
    assert haptic.calls == ["medium_impact"]
    assert page.updates == 1


def test_tap_on_item_of_another_category_deselects_category():
    page, app, haptic, home, work, first, second = make_app_with_items()
    app._select_category(work)

    asyncio.run(app._on_item_tap(first))

    # Пункт «Дома» не в выделенной категории: тап только снимает выделение.
    assert app._selected_view is None
    assert app._selected_item is None
    assert work.panel.bgcolor == theme.CATEGORY_PANEL_COLOR


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
    assert first.panel.bgcolor == theme.ITEM_PANEL_COLOR
    assert page.updates == 1


def test_tap_on_list_area_deselects_item():
    page, app, haptic, home, work, first, second = make_app_with_items()
    asyncio.run(app._on_item_long_press(first))
    page.updates = 0

    app.category_area.content.on_tap(None)

    assert app._selected_item is None
    assert first.selected is False
    assert first.panel.bgcolor == theme.ITEM_PANEL_COLOR
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
    assert first.panel.bgcolor == theme.ITEM_PANEL_COLOR
    assert app._selected_view is home
    assert home.panel.bgcolor == theme.CATEGORY_PANEL_SELECTED_COLOR


def test_buttons_switch_between_category_and_item_selection():
    """При выделении пункта — rename_item/delete_item, и наоборот."""
    page, app, haptic, home, work, first, second = make_app_with_items()

    asyncio.run(app._on_item_long_press(first))

    # Выделен пункт: плюс создаёт категорию, карандаш и корзина — пункт.
    assert app.button_area.visible is True
    assert app.plus_button.visible is True
    assert app.plus_button.on_click == app.create_category
    assert app.plus_button.content.semantics_label == theme.LABEL_CREATE_CATEGORY
    assert app.pencil_button.visible is True
    assert app.pencil_button.content.semantics_label == theme.LABEL_RENAME_ITEM
    assert app.trash_button.visible is True
    assert app.trash_button.content.semantics_label == theme.LABEL_DELETE_ITEM

    app._select_category(work)

    # Выделена категория: слоты снова показывают действия категории.
    assert app._selected_item is None
    assert app.plus_button.content.semantics_label == theme.LABEL_ADD_ITEM
    assert app.plus_button.on_click == app.add_item
    assert app.pencil_button.content.semantics_label == theme.LABEL_RENAME_CATEGORY
    assert app.trash_button.content.semantics_label == theme.LABEL_DELETE_CATEGORY

    app._deselect()

    # Выделения нет: виден только плюс.
    assert app.plus_button.content.semantics_label == theme.LABEL_CREATE_CATEGORY
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


# Переименование пункта — задача 5 этапа 3.


def test_pencil_button_renames_item_with_item_selection():
    page, app, haptic, home, work, first, second = make_app_with_items()
    select_item(app, first)

    assert app.pencil_button.on_click == app.rename_item
    assert app.pencil_button.content.semantics_label == theme.LABEL_RENAME_ITEM


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
    assert first.input.text_style == theme.ITEM_TITLE_STYLE
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
    assert app.trash_button.content.semantics_label == theme.LABEL_DELETE_ITEM


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
    assert home.panel.padding == theme.CATEGORY_PANEL_PADDING


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
