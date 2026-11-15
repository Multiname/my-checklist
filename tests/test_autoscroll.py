"""Автопрокрутка списка при перетаскивании: зона у краёв экрана, один проход
до края, продолжение после прохода и кеш списка."""

import asyncio

import flet as ft
import pytest

from support import (
    drag_category_to_screen,
    drag_item_to,
    drag_to_global,
    drop_item,
    item,
    make_app,
    make_app_with_items,
    measure,
    pick_up_category,
    pick_up_item,
    scroll_event,
    scroll_spy,
)
from ui import theme


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

    drag_to_global(app, first, 234 + theme.AUTOSCROLL_EDGE - 1)

    assert drag.autoscroll == -1
    # Прокрутку заказывает клиент: задача заказывает ей проход до края.
    assert page.tasks[-1] == (app._scroll_to_edge, (drag, drag.epoch))

    # Зона выхода шире зоны входа (AUTOSCROLL_HYSTERESIS): дрожание пальца на
    # самой границе не выключает и не включает прокрутку заново.
    drag_to_global(app, first, 234 + theme.AUTOSCROLL_EDGE + theme.AUTOSCROLL_HYSTERESIS - 1)
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
        distance / theme.AUTOSCROLL_SPEED * 1000
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
    assert spy.calls[0]["duration"] == round(300 / theme.AUTOSCROLL_SPEED * 1000)


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


def test_scroll_without_a_drag_only_updates_the_position():
    """Обычная прокрутка списка — не перетаскивание: место вставки не считается."""
    page, app, haptic, (home, work) = make_app("Дом", "Работа")

    app._on_scroll(scroll_event(pixels=120.0))

    assert app._scroll_pixels == 120.0
    assert app._viewport == 550.0
    assert app._max_scroll_extent == 1000.0
    # Ничего не заказывалось: список двигает палец пользователя.
    assert page.tasks == []


def test_item_metrics_uses_fallbacks_until_sizes_arrive():
    """Пока клиент не прислал размеры, раскладка берётся из шаблона."""
    page, app, haptic, home, work, first, second = make_app_with_items()

    metrics = app._item_metrics()

    assert metrics == [
        (
            theme.CATEGORY_TITLE_HEIGHT_FALLBACK,
            [theme.ITEM_ROW_HEIGHT_FALLBACK, theme.ITEM_ROW_HEIGHT_FALLBACK],
        ),
        (theme.CATEGORY_TITLE_HEIGHT_FALLBACK, []),
    ]


def test_autoscroll_keeps_the_category_target_in_sync():
    """Прокрутка при перетаскивании категории пересчитывает место вставки.

    Палец стоит на месте, а содержимое уезжает под ним: зазор должен переехать
    на новую цель, иначе отпускание встанет не туда, где виден зазор.
    """
    page, app, haptic, (home, work, rest) = make_app("Дом", "Работа", "Отдых")
    measure(app)
    pick_up_category(app, home)
    drag = app._category_drag

    app._on_scroll(scroll_event(pixels=300.0, max_scroll_extent=700.0))

    # Содержимое уехало на 300 px: палец теперь над концом списка.
    assert app._scroll_pixels == 300.0
    assert drag.target == 2
    assert rest.item.margin == ft.Margin.only(bottom=drag.slot_height)


def test_item_drag_finish_cancels_the_running_autoscroll():
    """Отпускание пункта останавливает проход: иначе список ехал бы без жеста."""
    page, app, haptic, home, work, first, second = make_app_with_items()
    measure(app)
    pick_up_item(first)
    drag = app._item_drag
    drag.autoscroll = 1
    spy = scroll_spy(app)

    app._finish_item_drag()

    assert drag.autoscroll == 0
    handler, args = page.tasks[-1]
    assert handler == app._cancel_scroll

    asyncio.run(handler(*args))
    assert spy.calls == [{"delta": 0}]
