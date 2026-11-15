"""Шаблоны контролов: всё, что рисуется на экране, кроме самих видов.

Функции `create_*` собирают контролы из параметров `ui.theme` и не
хранят состояния: состоянием одного элемента владеют `ui.views`, а
всем экраном — `ui.app`. Прокси перетаскивания собираются теми же
шаблонами, поэтому выглядят как исходные панели."""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

import domain
from ui.gestures import no_op
from ui.theme import (
    CATEGORY_HINT_STYLE,
    CATEGORY_ITEM_PADDING,
    CATEGORY_PANEL_COLOR,
    CATEGORY_PANEL_PADDING,
    CATEGORY_PANEL_RADIUS,
    CATEGORY_PANEL_SELECTED_COLOR,
    CATEGORY_PANEL_VERTICAL_PADDING,
    CATEGORY_TITLE_PADDING,
    CATEGORY_TITLE_STYLE,
    ITEM_CELL_PADDING,
    ITEM_CHECKED_COLOR,
    ITEM_CHECKED_TITLE_STYLE,
    ITEM_HINT_STYLE,
    ITEM_PANEL_COLOR,
    ITEM_PANEL_PADDING,
    ITEM_PANEL_SELECTED_COLOR,
    ITEM_SPACING,
    ITEM_TITLE_STYLE,
    ITEMS_BOX_PADDING,
    LIST_BOTTOM_PADDING,
    LIST_PADDING,
    SCROLL_CACHE_EXTENT,
    SCROLL_INTERVAL_IDLE,
)

if TYPE_CHECKING:
    from ui.views import CategoryView, ItemView


def create_category_title(title: str) -> ft.Text:
    """Название категории: крупнее пунктов, переносится на вторую строку."""
    return ft.Text(
        value=title,
        style=CATEGORY_TITLE_STYLE,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )


def create_item_title(title: str, *, checked: bool = False) -> ft.Text:
    """Название пункта: мельче названия категории, у отмеченного — серое.

    Цвет отмеченного пункта задан явным стилем: размер, начертание и
    межстрочная высота те же, поэтому переключение отметки не сдвигает строку.
    """
    return ft.Text(
        value=title,
        style=ITEM_CHECKED_TITLE_STYLE if checked else ITEM_TITLE_STYLE,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )


def item_title_style(checked: bool) -> ft.TextStyle:
    """Стиль названия пункта: серый у отмеченного, обычный у остальных."""
    return ITEM_CHECKED_TITLE_STYLE if checked else ITEM_TITLE_STYLE


def create_item_checkbox(item: domain.Item) -> ft.Checkbox:
    """Чекбокс пункта: отмечает состояние из БД, у отмеченного — серый.

    Отметка приходит из модели (``item.is_checked``), поэтому после
    перезапуска чекбоксы восстанавливаются из БД вместе с пунктами. Цвет
    галочки отмеченного пункта — тот же серый, что и его название.
    """
    return ft.Checkbox(
        value=item.is_checked,
        active_color=ITEM_CHECKED_COLOR if item.is_checked else None,
    )


def create_checkbox_blocker() -> ft.GestureDetector:
    """Прозрачный слой над чекбоксом: делает его некликабельным без смены вида.

    Пока что-то выделено (или идёт ввод названия), тап по чекбоксу не должен
    ничего менять. Просто проигнорировать событие на сервере нельзя: клиент
    успевает нарисовать переключение до ответа Python, и чекбокс на мгновение
    «мигает». Поэтому над чекбоксом лежит прозрачный слой-перехватчик: он
    ловит тап (распознаватель лежит выше в `Stack` и выигрывает арену), а
    чекбокс его не получает вовсе. Сам слой ничего не рисует (прозрачный
    контейнер, без `ink`), поэтому внешний вид чекбокса не меняется — в отличие
    от `disabled`, который красит его в бледный цвет.

    Слой скрыт, пока ничего не выделено: тогда тап снова доходит до чекбокса.
    Скрытый контрол остаётся в дереве, поэтому его `visible` меняется без
    пересоздания виджетов; размер стека задаёт сам чекбокс, и слой не влияет
    на высоту строки.
    """
    return ft.GestureDetector(
        # Слой занимает весь `Stack` — ровно площадь чекбокса.
        left=0,
        top=0,
        right=0,
        bottom=0,
        # Прозрачный контейнер нужен только чтобы у GestureDetector был
        # потомок, по которому считается попадание.
        content=ft.Container(bgcolor=ft.Colors.TRANSPARENT),
        on_tap=no_op,
        # Слой не должен появляться в TalkBack: действие остаётся у чекбокса.
        exclude_from_semantics=True,
        visible=False,
    )


def create_item_checkbox_area(
    checkbox: ft.Checkbox,
) -> tuple[ft.Stack, ft.GestureDetector]:
    """Чекбокс вместе с запирающим слоем; возвращает стек и сам слой."""
    blocker = create_checkbox_blocker()
    return ft.Stack(controls=[checkbox, blocker]), blocker


def create_items_box() -> ft.Container:
    """Контейнер пунктов внутри панели категории.

    Пока пунктов нет, контейнер скрыт и не занимает места: панель категории
    выглядит и измеряется как до появления пунктов. Отступ от названия задан
    внутренним padding контейнера, а не `spacing` колонки панели: скрытый
    контейнер не добавляет высоты, а `spacing` колонки добавил бы её и для
    пустого контейнера. Промежутка между пунктами у колонки нет: он принадлежит
    ячейке строки (см. `create_item_cell`).
    """
    return ft.Container(
        visible=False,
        padding=ITEMS_BOX_PADDING,
        content=ft.Column(spacing=0, tight=True),
    )


def create_item_cell(row: ft.Control) -> ft.Container:
    """Ячейка пункта в контейнере: строка и промежуток до следующей строки.

    Промежуток задан внутренним отступом ячейки, а не `spacing` колонки: когда
    строка сворачивается (пункт «поднят»), её ячейка перестаёт занимать место
    целиком, и в контейнере не остаётся пустого промежутка. Со `spacing` колонки
    свёрнутая строка нулевой высоты оставляла два промежутка вместо одного —
    остаток дополнительной высоты на месте пункта, который пропадал только после
    отпускания (проверено на устройстве).
    """
    return ft.Container(content=row, padding=ITEM_CELL_PADDING)


def item_slot_height(row_height: float) -> float:
    """Высота слота пункта: строка вместе с промежутком после неё.

    Слот занимают и ячейка строки, и зазор на месте вставки: пункт встаёт на
    место зазора без сдвига остальных строк.
    """
    return row_height + ITEM_SPACING


def create_item_panel(checkbox: ft.Checkbox, title: ft.Control) -> ft.Container:
    """Шаблон пункта: чекбокс слева, название справа, фон прозрачный.

    Горизонтальный отступ задан самому пункту, а не панели категории: так
    выделенный пункт закрашивает строку во всю ширину панели, как на макете, а
    текст и чекбокс остаются на прежнем месте.

    Обрезка включена всегда: при перетаскивании панель сворачивается до нулевой
    высоты, и без неё содержимое строки нарисовалось бы поверх соседних пунктов.
    """
    return ft.Container(
        bgcolor=ITEM_PANEL_COLOR,
        padding=ITEM_PANEL_PADDING,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Row(
            controls=[checkbox, title],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def create_item_row(panel: ft.Control) -> ft.GestureDetector:
    """Область пункта: ловит тап, долгое нажатие и перетаскивание пункта.

    Жесты принадлежат пункту, а не категории: долгое нажатие по пункту выделяет
    и поднимает пункт, а по остальной панели — перетаскивает саму категорию
    (`CategoryView.gesture_area`). Распознаватель пункта лежит глубже в дереве,
    поэтому попадает в арену жестов раньше и выигрывает: проверено на устройстве.

    Обработчики назначает `ItemView`: они замыкаются на сам пункт, которого
    в момент создания строки ещё нет.
    """
    return ft.GestureDetector(content=panel)


def create_item_gap(height: float) -> ft.Container:
    """Зазор на месте вставки: пустое место на целый слот пункта.

    Ширины у него нет — видно только панель категории, как будто пункт уже
    уехал. Высота задана явно и равна слоту пункта (`item_slot_height`): столько
    занимает ячейка строки, поэтому пункт встаёт на место зазора без сдвига
    остальных строк — и в своей категории, и в чужой.
    """
    return ft.Container(height=height)


def create_item_proxy(view: ItemView) -> ft.Container:
    """Поднятая копия строки пункта: розовый фон, те же чекбокс и название.

    Прокси лежит в `Stack` выше списка и двигается за пальцем — только по
    вертикали, как панель категории (см. `_move_proxy`). Как и у
    перетаскиваемой категории, тени и подложки нет: видно только строку в цвете
    выделения, а размеры строки не меняются.
    """
    panel = create_item_panel(
        create_item_checkbox(view.item),
        create_item_title(view.title, checked=view.item.is_checked),
    )
    panel.bgcolor = ITEM_PANEL_SELECTED_COLOR
    panel.width = view.width
    panel.height = view.height
    return panel


def create_category_proxy(view: CategoryView, width: float) -> ft.Container:
    """Поднятая копия панели категории: розовый фон, название и её пункты.

    Прокси лежит в `Stack` выше списка и двигается за пальцем по вертикали.
    Собирается из данных категории теми же шаблонами, что и панель в списке, и
    той же ширины, поэтому выглядит и измеряется как исходная панель. Тени и
    подложки нет — только панель в цвете выделения, как было у категории,
    которую перетаскивал клиент.
    """
    title = ft.Container(
        content=create_category_title(view.title),
        padding=CATEGORY_TITLE_PADDING,
    )
    cells = [
        ft.Container(
            content=create_item_panel(
                create_item_checkbox(item.item),
                create_item_title(item.title, checked=item.item.is_checked),
            ),
            padding=ITEM_CELL_PADDING,
        )
        for item in view.items
    ]
    items_box = create_items_box()
    items_box.content.controls = cells
    items_box.visible = bool(cells)
    items_box.padding = ITEMS_BOX_PADDING if cells else None
    panel = create_category_panel(create_category_content(title, items_box))
    panel.padding = category_panel_padding(bool(cells))
    panel.bgcolor = CATEGORY_PANEL_SELECTED_COLOR
    panel.width = width
    return panel


def create_category_content(title: ft.Control, items: ft.Control) -> ft.Column:
    """Содержимое панели категории: название, под ним — контейнер пунктов."""
    return ft.Column(controls=[title, items], spacing=0, tight=True)


def category_panel_padding(has_content: bool) -> ft.Padding:
    """Вертикальные отступы панели категории.

    Промежуток между пунктами принадлежит ячейке строки, поэтому последняя строка
    тоже несёт его; чтобы панель не была выше на этот промежуток, её нижний
    отступ на него меньше — но только пока в контейнере есть что показывать.
    Пустой контейнер (категория без пунктов или в нём осталась одна свёрнутая
    строка) отступов не несёт, и отступ панели обычный: иначе панель меняла бы
    высоту после переноса последнего пункта.
    """
    bottom = CATEGORY_PANEL_VERTICAL_PADDING - (ITEM_SPACING if has_content else 0)
    if bottom == CATEGORY_PANEL_VERTICAL_PADDING:
        return CATEGORY_PANEL_PADDING
    return ft.Padding.only(top=CATEGORY_PANEL_VERTICAL_PADDING, bottom=bottom)


def create_category_panel(content: ft.Control) -> ft.Container:
    """Шаблон категории: прямоугольная панель вокруг названия и пунктов.

    У панели только вертикальные отступы: горизонтальные несут название и
    пункты, поэтому фон выделенного пункта доходит до краёв панели. Нижний отступ
    подгоняется под содержимое (`category_panel_padding`).

    Обрезка включена всегда: при перетаскивании панель сворачивается до нулевой
    высоты, и без неё название и пункты рисовались бы поверх соседних панелей.
    """
    return ft.Container(
        bgcolor=CATEGORY_PANEL_COLOR,
        border_radius=CATEGORY_PANEL_RADIUS,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        padding=category_panel_padding(False),
        content=content,
    )


def create_category_item(panel: ft.Control) -> ft.Container:
    """Элемент списка: панель категории вместе с промежутком до следующей.

    Промежуток — внутренний отступ обёртки, а не `margin` панели, и не `spacing`
    списка: `spacing` давал бы промежуток и после последней категории. При
    перетаскивании обёртка сворачивается вместе с панелью (отступ снимается), а
    `margin` соседней обёртки занимает зазор на месте будущей вставки: самой
    поднятой категории отступ не назначается никогда — клиент пересоздал бы её
    поддерево вместе с распознавателем жеста (см. `_place_category_gap`).
    """
    return ft.Container(
        content=panel,
        padding=CATEGORY_ITEM_PADDING,
    )


def create_category_list() -> ft.ListView:
    """Список категорий на весь экран: прокручивается, не переставляет сам.

    Перетаскивание категорий ведёт `ChecklistApp`, как и перетаскивание пунктов
    (см. docs/Project.md): штатный `ReorderableListView` прокручивает список,
    когда край экрана касается **любая** часть перетаскиваемой категории, а
    длинная категория касается его сразу. Свой drag считает зону автопрокрутки
    по названию — см. `_autoscroll_span()`.
    """
    return ft.ListView(
        expand=True,
        padding=ft.Padding.only(
            left=LIST_PADDING,
            right=LIST_PADDING,
            top=LIST_PADDING,
            bottom=LIST_BOTTOM_PADDING,
        ),
        # Список строится целиком: иначе scroll_to() не работает, а без него
        # после запуска список открывался бы не сверху, а с конца
        # (auto_scroll прокручивает к концу при каждой смене содержимого).
        build_controls_on_demand=False,
        auto_scroll=False,
        # Кеш растянут на всё содержимое: иначе клиент строит панель заново
        # каждый раз, когда она въезжает на экран, и инерционная прокрутка
        # подтормаживает на каждой новой строке (см. `SCROLL_CACHE_EXTENT`).
        cache_extent=SCROLL_CACHE_EXTENT,
        # В покое позиция прокрутки нужна только к началу перетаскивания,
        # поэтому события прокрутки приходят редко и не нагружают канал.
        # Во время drag частоту поднимает `ChecklistApp._set_scroll_interval`.
        scroll_interval=SCROLL_INTERVAL_IDLE,
    )


def create_category_area(
    category_list: ft.ListView, on_tap, on_tap_cancel=None
) -> ft.Container:
    """Область списка: тап по ней снимает выделение категории.

    Тап ловит обёртка списка, а не экран целиком: `button_area` лежит выше
    в `Stack`, поэтому тапы по кнопкам сюда не доходят. Прокрутка выделение
    не снимает — жест переходит к списку (drag побеждает в арене жестов);
    `on_tap_cancel` сообщает, что жест перестал быть тапом.
    """
    return ft.Container(
        content=ft.GestureDetector(
            content=category_list,
            on_tap=on_tap,
            on_tap_cancel=on_tap_cancel,
        ),
    )


def create_title_input(
    *,
    hint_text: str,
    text_style: ft.TextStyle,
    hint_style: ft.TextStyle,
    on_commit,
    value: str = "",
    on_tap_outside=None,
) -> ft.TextField:
    """Поле ввода названия на месте названия категории или пункта.

    Клавиатура появляется за счёт autofocus; ввод завершается кнопкой действия
    клавиатуры, тапом вне поля, потерей фокуса и скрытием клавиатуры
    (жест «назад» обрабатывается через page.on_media_change и PopScope).
    ``value`` — прежнее название: при переименовании поле сразу заполнено им.
    ``on_tap_outside`` — отдельный обработчик тапа вне поля: он ещё и помечает,
    что клавиатуру закрыл именно тап (см. ChecklistApp._on_tap).
    """
    return ft.TextField(
        value=value,
        hint_text=hint_text,
        hint_style=hint_style,
        text_style=text_style,
        # Поле выглядит как название, а не как форма. dense убирает
        # минимальную высоту Material-поля, чтобы строка не становилась выше.
        border=ft.NoInputBorder(),
        content_padding=0,
        dense=True,
        min_lines=1,
        max_lines=2,
        autofocus=True,
        on_submit=on_commit,
        on_blur=on_commit,
        on_tap_outside=on_tap_outside or on_commit,
    )


def create_category_input(
    hint_text: str, on_commit, value: str = "", on_tap_outside=None
) -> ft.TextField:
    """Поле ввода названия категории: стиль названия категории."""
    return create_title_input(
        hint_text=hint_text,
        text_style=CATEGORY_TITLE_STYLE,
        hint_style=CATEGORY_HINT_STYLE,
        on_commit=on_commit,
        value=value,
        on_tap_outside=on_tap_outside,
    )


def create_item_input(
    hint_text: str, on_commit, value: str = "", on_tap_outside=None
) -> ft.TextField:
    """Поле ввода названия пункта: стиль названия пункта."""
    return create_title_input(
        hint_text=hint_text,
        text_style=ITEM_TITLE_STYLE,
        hint_style=ITEM_HINT_STYLE,
        on_commit=on_commit,
        value=value,
        on_tap_outside=on_tap_outside,
    )
