"""Перетаскивание категорий: прокси, зазор на месте вставки и сохранение порядка."""

import asyncio

import flet as ft

from support import (
    category_start_event,
    drag_category_to,
    drag_category_to_screen,
    drop_category,
    item,
    long_press_start_event,
    make_app,
    make_app_with_items,
    measure,
    pick_up_category,
    pick_up_item,
)
from ui import theme
from ui.controls import (
    category_panel_padding,
    create_category_proxy,
    item_slot_height,
)
from ui.geometry import (
    build_category_spans,
    category_panel_height,
    category_span_at,
)


def test_category_panel_height_follows_the_template():
    """Пустая категория — только название, с пунктами — ещё и их слоты."""
    assert category_panel_height(30, []) == (
        30 + 2 * theme.CATEGORY_PANEL_VERTICAL_PADDING
    )
    assert category_panel_height(30, [50, 50]) == (
        theme.CATEGORY_PANEL_VERTICAL_PADDING
        + 30
        + theme.CATEGORY_ITEMS_TOP
        + 2 * item_slot_height(50)
        + category_panel_padding(True).bottom
    )


def test_category_spans_keep_the_list_height_during_the_drag():
    """Свёрнутый слот и зазор вместе занимают столько же, сколько категория."""
    slots = [60.0, 120.0, 90.0]

    for target in range(3):
        spans = build_category_spans(slots, dragged=1, target=target)

        heights = [span.bottom - span.top for span in spans]
        assert sum(heights) == sum(slots)
        gap = next(span for span in spans if span.is_gap)
        assert gap.bottom - gap.top == slots[1]
        assert [span.index for span in spans if not span.is_gap] == [0, 1]
        assert spans[-1].bottom == theme.LIST_PADDING + sum(slots)


def test_category_span_uses_panel_midpoints():
    """Категория переставляется, когда палец проходит середину панели."""
    spans = build_category_spans([100.0, 100.0, 100.0], dragged=2, target=2)

    assert category_span_at(spans, theme.LIST_PADDING) == 0
    assert category_span_at(spans, theme.LIST_PADDING + 49) == 0
    assert category_span_at(spans, theme.LIST_PADDING + 51) == 1
    assert category_span_at(spans, 10_000) == 2


def test_category_span_does_not_oscillate_when_the_gap_moves():
    """Палец, стоящий в зазоре, не переставляет его туда-обратно."""
    slots = [100.0, 100.0, 100.0]

    for target in range(3):
        spans = build_category_spans(slots, dragged=1, target=target)
        gap = next(span for span in spans if span.is_gap)

        assert category_span_at(spans, (gap.top + gap.bottom) / 2) == target


def test_category_proxy_looks_like_the_panel():
    """Прокси — та же панель в цвете выделения, с названием и пунктами."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)

    proxy = create_category_proxy(home, home.width)

    assert proxy.bgcolor == theme.CATEGORY_PANEL_SELECTED_COLOR
    assert proxy.width == home.width
    assert proxy.border_radius == theme.CATEGORY_PANEL_RADIUS
    assert proxy.padding == home.panel.padding
    gesture_area, items_box = proxy.content.controls
    assert gesture_area.content.value == "Дом"
    assert items_box.visible is True
    assert len(items_box.content.controls) == 2


def test_category_proxy_of_empty_category_has_no_items_box():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)

    proxy = create_category_proxy(home, home.width)

    _, items_box = proxy.content.controls
    assert items_box.visible is False
    assert proxy.padding == category_panel_padding(False)


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
    assert drag.slot_height == home.height + theme.CATEGORY_SPACING
    assert home.item.margin is None
    assert work.item.margin == ft.Margin.only(top=drag.slot_height)
    # Прокси выше списка; панель стоит там, где её взял палец (300 - 12).
    assert drag.proxy in app.stack.controls
    assert drag.panel_top == 300.0
    assert drag.proxy.top == 300.0 - drag.origin_y
    assert app._dragging is True


def test_category_proxy_follows_the_finger_vertically():
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag

    drag_category_to_screen(app, home, 420)

    assert drag.panel_top == 420.0
    assert drag.proxy.top == drag.panel_top - drag.origin_y
    # По горизонтали категория не едет: прокси в столбце списка.
    assert drag.proxy.left == theme.LIST_PADDING


def test_drag_move_patches_only_the_proxy_and_the_gap():
    """Движение пальца патчит прокси и зазор, а не всю страницу.

    `page.update()` без контролов — патч всей страницы: сервер сравнивает с
    прошлым показом всё дерево контролов, а список собран целиком
    (`build_controls_on_demand=False`). На 40 категориях по 5 пунктов такой
    патч занимает на телефоне десятки миллисекунд, и палец (120 событий в
    секунду) за ним не успевал.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_category(app, home)
    patches: list[tuple] = []
    page.update = lambda *controls: patches.append(controls)

    drag_category_to(app, home, 500)

    assert patches
    assert all(controls for controls in patches), "патч всей страницы"
    controls = [control for patch in patches for control in patch]
    assert app._category_drag.proxy in controls
    # Прокси и элементы списка, которым достался зазор.
    assert len(controls) <= 5


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

    drag_category_to(app, home, 120)
    assert rest.item.margin == ft.Margin.only(top=drag.slot_height)

    drag_category_to(app, home, 500)

    assert drag.target == 2
    # Место — конец списка: зазор становится нижним отступом последней панели.
    assert rest.item.margin == ft.Margin.only(bottom=drag.slot_height)


def test_last_category_drag_moves_the_gap_before_the_previous_panel():
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    measure(app)
    pick_up_category(app, rest)
    drag = app._category_drag
    assert work.item.margin == ft.Margin.only(bottom=drag.slot_height)

    # Первое движение выше середины «Работы» переносит зазор перед ней.
    drag_category_to(app, rest, 100)

    assert drag.target == 1
    assert work.item.margin == ft.Margin.only(top=drag.slot_height)


def test_dragged_category_never_gets_a_margin():
    """Поднятая категория не получает отступ ни на одном месте вставки.

    `margin` клиент применяет к контейнеру, пересоздавая поддерево элемента
    вместе с распознавателем жеста: перетаскивание обрывалось бы на первом же
    обновлении экрана (на устройстве панель замирала, а отпускание пальца не
    доходило до приложения). Поэтому зазор всегда достаётся соседней категории.
    """
    for index in range(3):
        # Свежий список на каждую категорию: после отпускания порядок меняется, и
        # проверяемая категория перестала бы быть последней.
        page, app, haptic, views = make_app("Дом", "Работа", "Отдых")
        measure(app)
        dragged = views[index]
        pick_up_category(app, dragged)

        for model_y in (-1000, 20, 120, 500, 10_000):
            drag_category_to(app, dragged, model_y)

            assert dragged.item.margin is None


def test_last_category_gap_goes_to_the_previous_one():
    """Зазор последней категории — нижний отступ предыдущей, а не её самой.

    Место в конце списка раньше отдавалось `self.views[-1]`, то есть самой
    поднятой панели, если она последняя: жест перетаскивания обрывался, и
    категория не двигалась. Раскладка от такой замены та же — свёрнутая панель
    места не занимает.
    """
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, work)
    drag = app._category_drag

    assert drag.source == 1
    assert work.item.margin is None
    assert home.item.margin == ft.Margin.only(bottom=drag.slot_height)


def test_last_category_drag_reorders_it_to_the_top():
    """Вторая категория перетаскивается наверх и сохраняется в БД.

    Ровно этот сценарий не работал на устройстве: две категории по два пункта,
    вторая не двигалась.
    """
    page, app, haptic, home, work, first, second = make_app_with_items()
    work.append_item(item(3, work.category.id, "Отчёт"))
    work.append_item(item(4, work.category.id, "План", position=1))
    measure(app)
    pick_up_category(app, work)
    drag = app._category_drag

    # Середина «Дома» — 103: палец выше неё ставит категорию перед ним.
    drag_category_to(app, work, 20)
    assert drag.target == 0
    drop_category(app, work, 20)

    assert app.storage.moved == [(work.category.id, 0)]
    assert [view.title for view in app.views] == ["Работа", "Дом"]
    assert all(view.item.margin is None for view in app.views)


def test_category_drag_restores_everything_after_drop():
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    pick_up_category(app, home)

    drop_category(app, home, 1000)

    assert app._category_drag is None
    assert home.collapsed is False
    assert home.panel.height is None
    assert home.item.padding == theme.CATEGORY_ITEM_PADDING
    assert all(view.item.margin is None for view in app.views)
    assert app.stack.controls == [app.category_area, app.button_area]
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


def test_panel_size_change_feeds_the_drag_model():
    """Клиент сообщил размер панели — по нему строятся прокси и зазор."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    home.panel.on_size_change(
        ft.LayoutSizeChangeEvent(
            name="size_change", control=home.panel, width=311.0, height=170.0
        )
    )

    assert (home.width, home.height) == (311.0, 170.0)


def test_unmeasured_category_uses_the_template_slot_height():
    """Категория за пределами экрана размеров не шлёт: её слот считается по шаблону.

    Без оценки зазор на месте такой категории занял бы ноль: соседние панели
    прыгнули бы при подъёме.
    """
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    measured = work.height
    home.height = None

    heights = app._category_slot_heights()

    assert heights[0] == category_panel_height(30.0, []) + theme.CATEGORY_SPACING
    assert heights[1] == measured + theme.CATEGORY_SPACING


def test_drag_start_restores_sizes_after_the_panel_was_collapsed():
    """Свёрнутая панель не запоминает собственную нулевую высоту.

    Клиент присылает `size_change` и на свёрнутую панель: её высота 0 — это не
    размер панели, и запоминать его нельзя, иначе прокси и зазор следующего
    перетаскивания схлопнутся.
    """
    page, app, haptic, (home, work) = make_app("Дом", "Работа")
    measure(app)
    collapsed_height = home.height
    pick_up_category(app, home)

    home.panel.on_size_change(
        ft.LayoutSizeChangeEvent(
            name="size_change", control=home.panel, width=300.0, height=0.0
        )
    )

    assert home.height == collapsed_height


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
