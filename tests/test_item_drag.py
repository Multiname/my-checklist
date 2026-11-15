"""Перетаскивание пунктов: раскладка списка, зазор, прокси и запись
нового порядка в хранилище."""

import asyncio

import flet as ft

from support import (
    drag_item_to,
    drag_to_global,
    drop_at_global,
    drop_item,
    item,
    make_app,
    make_app_with_items,
    measure,
    pick_up_item,
    press_item,
)
from ui import theme
from ui.compat import patch_long_press_move_event
from ui.controls import (
    category_panel_padding,
    create_item_gap,
    item_slot_height,
)
from ui.geometry import (
    base_row_top,
    build_drag_spans,
    drag_slot_at,
)


# Перетаскивание пунктов — задача 4 этапа 3.


def test_long_press_move_event_is_built_from_client_data():
    """flet 1.1.2 присылает offset_from_origin как "ofo": событие всё равно собирается.

    Без обхода ошибки разбор события падает, и перетаскивание пункта одним
    жестом не работает (проверено на устройстве).
    """
    patch_long_press_move_event()
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

    assert base_row_top(metrics, 0, 0) == 66.0
    assert base_row_top(metrics, 0, 1) == 120.0


def test_drag_layout_repeats_the_template_with_a_gap():
    spans = build_drag_spans(
        [(30, [50, 60])], source=(0, 0), height=50, target=(0, 0)
    )

    span = spans[0]
    assert span.top == theme.LIST_PADDING
    assert span.items_top == (
        theme.LIST_PADDING
        + theme.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + theme.CATEGORY_ITEMS_TOP
    )
    # Свёрнутая строка, зазор на её месте, вторая строка.
    assert [entry.row_index for entry in span.entries] == [None, None, 0]
    assert [entry.gap for entry in span.entries] == [False, True, False]
    dragged, gap, second = span.entries
    # Свёрнутая строка не занимает места: зазор встаёт вплотную и занимает целый
    # слот — строку с промежутком после неё (промежуток принадлежит ячейке).
    assert dragged.bottom == dragged.top
    assert gap.top == dragged.top
    assert gap.bottom - gap.top == item_slot_height(50)
    assert second.bottom - second.top == 60
    assert second.top == gap.bottom
    # После последней строки — промежуток её ячейки и отступ панели без него.
    assert span.bottom == (
        second.bottom
        + theme.ITEM_SPACING
        + category_panel_padding(True).bottom
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
    spans = build_drag_spans(
        metrics, source=(0, 0), height=50, target=(0, 0)
    )
    items_top = (
        theme.LIST_PADDING
        + theme.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + theme.CATEGORY_ITEMS_TOP
    )

    # Та же высота, что и до подъёма: слоты двух строк и отступ панели.
    assert spans[0].bottom == (
        items_top
        + item_slot_height(50)
        + item_slot_height(60)
        + category_panel_padding(True).bottom
    )
    assert spans[0].bottom == (
        items_top
        + 50
        + theme.ITEM_SPACING
        + 60
        + theme.CATEGORY_PANEL_VERTICAL_PADDING
    )
    # Следующая категория тоже осталась на своём месте.
    assert spans[1].top == spans[0].bottom + theme.CATEGORY_SPACING


def test_moving_the_item_away_leaves_no_extra_height():
    """Перенос пункта не оставляет в исходной категории его высоты.

    Свёрнутая строка не оставляет ни промежутка, ни отступа, поэтому панель
    исходной категории сразу равна категории без этого пункта: после отпускания
    она не «сжимается» на остаток (видно на устройстве).
    """
    metrics = [(30, [50, 60]), (30, [40])]
    spans = build_drag_spans(
        metrics, source=(0, 0), height=50, target=(1, 0)
    )
    items_top = (
        theme.LIST_PADDING
        + theme.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + theme.CATEGORY_ITEMS_TOP
    )

    # В исходной категории остался один пункт: ровно его слот и отступы панели.
    assert spans[0].bottom == (
        items_top
        + item_slot_height(60)
        + category_panel_padding(True).bottom
    )
    # Низ той же категории без перетаскивания — тот же.
    assert spans[0].bottom == (
        items_top + 60 + theme.CATEGORY_PANEL_VERTICAL_PADDING
    )
    # Целевая категория выросла ровно на слот пункта.
    original = (
        spans[1].items_top
        + 40
        + theme.CATEGORY_PANEL_VERTICAL_PADDING
    )
    assert spans[1].bottom == original + item_slot_height(50)


def test_gap_is_a_whole_item_slot():
    """Зазор равен слоту пункта в любой категории: его место занимает ячейка."""
    spans = build_drag_spans(
        [(30, [50]), (30, [30, 40])], source=(0, 0), height=50, target=(1, 1)
    )

    gap = next(entry for entry in spans[1].entries if entry.gap)
    assert gap.bottom - gap.top == item_slot_height(50)
    # В первой категории осталась только свёрнутая строка: она места не
    # занимает, и панель выглядит как у категории без пунктов.
    assert spans[0].bottom == (
        spans[0].items_top
        - theme.CATEGORY_ITEMS_TOP
        + theme.CATEGORY_PANEL_VERTICAL_PADDING
    )


def test_drag_layout_moves_the_gap_to_another_category():
    first, second = build_drag_spans(
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
        item_slot_height(50)
    )
    assert second.entries[2].row_index == 1


def test_drag_layout_has_no_gap_outside_the_target_category():
    home, work = build_drag_spans(
        [(30, [50, 60]), (20, [])],
        source=(0, 0),
        height=50,
        target=(1, 0),
    )

    assert [entry.gap for entry in home.entries] == [False, False]
    assert [entry.gap for entry in work.entries] == [True]
    assert work.row_count == 0


def test_drag_slot_uses_row_midpoints():
    spans = build_drag_spans(
        [(30, [50, 50])], source=(0, 0), height=50, target=(0, 0)
    )
    row = spans[0].entries[2]
    middle = (row.top + row.bottom) / 2

    assert row.row_index == 0
    assert drag_slot_at(spans, spans[0].items_top) == (0, 0)
    assert drag_slot_at(spans, middle - 1) == (0, 0)
    # Палец прошёл середину строки — место вставки за ней.
    assert drag_slot_at(spans, middle + 1) == (0, 1)


def test_drag_slot_goes_to_the_nearest_category():
    spans = build_drag_spans(
        [(30, [50]), (30, [50])], source=(0, 0), height=50, target=(1, 0)
    )

    assert drag_slot_at(spans, -100) == (0, 0)
    assert drag_slot_at(spans, 10_000) == (1, 1)


def test_drag_slot_does_not_oscillate_when_the_gap_moves():
    metrics = [(30, [50, 50, 50]), (30, [])]

    for y in (60, 100, 150, 200, 250, 300):
        target = (0, 0)
        for _ in range(5):
            spans = build_drag_spans(
                metrics, source=(0, 0), height=50, target=target
            )
            target = drag_slot_at(spans, y)
        # После того как зазор встал по этой координате, он там и остаётся.
        spans = build_drag_spans(
            metrics, source=(0, 0), height=50, target=target
        )
        assert drag_slot_at(spans, y) == target


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
    assert proxy.bgcolor == theme.ITEM_PANEL_SELECTED_COLOR
    assert proxy.padding == theme.ITEM_PANEL_PADDING
    assert (proxy.width, proxy.height) == (300.0, 50.0)
    assert isinstance(proxy.content, ft.Row)
    # Копия показывает то же название и ту же отметку, что и строка.
    assert proxy.content.controls[0].value is False
    assert proxy.content.controls[1].value == "Молоко"
    # Прокси держится за точку нажатия: его верх — верх строки в модели.
    assert proxy.left == theme.LIST_PADDING
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

    assert gap.height == item_slot_height(first.height)
    # В своей категории: строка свёрнута вместе с ячейкой.
    assert first.cell.padding is None
    assert home.items_box.padding == theme.ITEMS_BOX_PADDING
    drag_item_to(app, first, 200)
    assert work.gap_index == 0
    assert gap.height == item_slot_height(first.height)
    drag_item_to(app, first, 80)
    assert home.gap_index == 0
    assert gap.height == item_slot_height(first.height)


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
    assert home.panel.padding == theme.CATEGORY_PANEL_PADDING
    assert home.items_box.visible is True
    assert home.items_box.padding is None

    drop_item(app, only, 200)

    # Высота панели та же: отступы не поменялись.
    assert home.items == []
    assert home.panel.padding == theme.CATEGORY_PANEL_PADDING
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
    assert (proxy.left, proxy.top) == (theme.LIST_PADDING, 166.0)


def test_sideways_movement_does_not_start_the_drag():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    page.updates = 0
    proxy = app._item_drag.proxy

    drag_to_global(app, first, 300, global_x=200)
    drag_to_global(app, first, 300 + theme.ITEM_DRAG_THRESHOLD - 1, global_x=200)

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

    drag_item_to(app, first, 66 + theme.ITEM_DRAG_THRESHOLD - 1)

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
    assert app.pencil_button.content.semantics_label == theme.LABEL_RENAME_ITEM
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
    gap = create_item_gap(50)

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
    gap = create_item_gap(50)
    assert work.items_box.visible is False

    work.place_gap(gap, 0)

    assert work.items_box.visible is True
    assert work.items_box.content.controls == [gap]

    work.remove_gap()

    assert work.items_box.visible is False
    assert work.items_box.content.controls == []
