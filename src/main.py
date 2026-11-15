"""Точка входа приложения «Чеклист»."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

import flet as ft

import domain
from storage import Storage, StorageError, open_storage

logger = logging.getLogger(__name__)


def _patch_long_press_move_event() -> None:
    """Обход ошибки flet 1.1.2 в событии движения после долгого нажатия.

    Клиент присылает координаты в полях ``l``, ``g``, ``ofo``, ``lofo``, а класс
    `LongPressMoveUpdateEvent` объявляет ``offset_from_origin`` с
    ``data_field="of"`` (опечатка в библиотеке). Из-за неё разбор события падает
    с ``TypeError: missing 1 required keyword-only argument:
    'offset_from_origin'`` — проверено на устройстве. Без этого события нельзя
    вести перетаскивание пункта одним жестом: `on_long_press_start` даёт только
    точку нажатия, а движение пальца — лишь оно.

    Патч подставляет нулевое смещение, если его не передали: обработчику нужны
    только ``local_position`` и ``global_position``, а остальные поля события
    заполняются клиентом как обычно. Ошибка исправлена в flet после 1.1.2 —
    тогда патч можно убрать.
    """
    original_init = ft.LongPressMoveUpdateEvent.__init__

    def patched_init(self, *args, **kwargs):
        kwargs.setdefault("offset_from_origin", ft.Offset(0, 0))
        original_init(self, *args, **kwargs)

    ft.LongPressMoveUpdateEvent.__init__ = patched_init


_patch_long_press_move_event()

# Параметры button_area — см. docs/Design.md
BUTTON_SIZE = 56
BUTTON_ICON_SIZE = 24
BUTTON_SPACING = 12
BUTTON_AREA_MARGIN = 16
BUTTON_AREA_HEIGHT = BUTTON_SIZE * 3 + BUTTON_SPACING * 2

# Параметры списка категорий и шаблона категории — см. docs/Design.md
LIST_PADDING = 16
CATEGORY_SPACING = 8
CATEGORY_PANEL_COLOR = ft.Colors.SURFACE_CONTAINER_HIGH
# Выделенная категория отличается от остальных цветом панели:
# фоновый SURFACE_CONTAINER_HIGH слишком близок к SECONDARY_CONTAINER,
# поэтому берётся розовый TERTIARY_CONTAINER — его видно сразу.
CATEGORY_PANEL_SELECTED_COLOR = ft.Colors.TERTIARY_CONTAINER
CATEGORY_PANEL_RADIUS = 12
# Горизонтальный отступ панели задан не у панели, а у названия и у пунктов:
# фон выделенного пункта должен закрашивать всю ширину панели, до её краёв
# (см. docs/Design.md). По вертикали панель по-прежнему отступает 12.
PANEL_HORIZONTAL_PADDING = 16
CATEGORY_PANEL_VERTICAL_PADDING = 12
CATEGORY_PANEL_PADDING = ft.Padding.symmetric(
    vertical=CATEGORY_PANEL_VERTICAL_PADDING
)
CATEGORY_TITLE_PADDING = ft.Padding.symmetric(horizontal=PANEL_HORIZONTAL_PADDING)
CATEGORY_TITLE_SIZE = 20
CATEGORY_TITLE_WEIGHT = ft.FontWeight.BOLD
# Явная межстрочная высота нужна, чтобы Text и TextField занимали одинаковую
# высоту (без неё текстовое поле выше). 1.45 совпадает с высотой строки
# названия по умолчанию, поэтому обычная панель не меняет размер.
CATEGORY_TITLE_LINE_HEIGHT = 1.45
CATEGORY_TITLE_STYLE = ft.TextStyle(
    size=CATEGORY_TITLE_SIZE,
    weight=CATEGORY_TITLE_WEIGHT,
    height=CATEGORY_TITLE_LINE_HEIGHT,
)
CATEGORY_HINT_STYLE = ft.TextStyle(
    size=CATEGORY_TITLE_SIZE,
    weight=CATEGORY_TITLE_WEIGHT,
    height=CATEGORY_TITLE_LINE_HEIGHT,
    color=ft.Colors.ON_SURFACE_VARIANT,
)

# Параметры пункта — см. docs/Design.md. Текст пункта мельче текста категории,
# а межстрочная высота задана явно по той же причине, что и у категории:
# Text и TextField должны занимать одинаковую высоту, иначе строка «прыгает».
ITEM_TITLE_SIZE = 16
ITEM_TITLE_WEIGHT = ft.FontWeight.NORMAL
ITEM_TITLE_LINE_HEIGHT = 1.45
ITEM_TITLE_STYLE = ft.TextStyle(
    size=ITEM_TITLE_SIZE,
    weight=ITEM_TITLE_WEIGHT,
    height=ITEM_TITLE_LINE_HEIGHT,
)
ITEM_HINT_STYLE = ft.TextStyle(
    size=ITEM_TITLE_SIZE,
    weight=ITEM_TITLE_WEIGHT,
    height=ITEM_TITLE_LINE_HEIGHT,
    color=ft.Colors.ON_SURFACE_VARIANT,
)
# Отмеченный пункт — «выполненный»: его название и сама отметка рисуются серым
# (ON_SURFACE_VARIANT — тот же серый, что и подсказка в поле ввода), а не
# цветом акцента. Размеры и положение строки не меняются: меняется только цвет
# текста и галочки (см. docs/Design.md).
ITEM_CHECKED_COLOR = ft.Colors.ON_SURFACE_VARIANT
ITEM_CHECKED_TITLE_STYLE = ft.TextStyle(
    size=ITEM_TITLE_SIZE,
    weight=ITEM_TITLE_WEIGHT,
    height=ITEM_TITLE_LINE_HEIGHT,
    color=ITEM_CHECKED_COLOR,
)
# Фон пункта прозрачный: пункт лежит внутри панели категории, и сквозь него
# видна панель, в том числе когда категория выделена.
ITEM_PANEL_COLOR = ft.Colors.TRANSPARENT
# Выделенный пункт красится тем же цветом, что и выделенная категория: выделение
# читается одинаково на обоих уровнях (см. docs/Design.md).
ITEM_PANEL_SELECTED_COLOR = CATEGORY_PANEL_SELECTED_COLOR
# Горизонтальный отступ пункта: он переехал с панели категории, поэтому
# выделенная строка тянется от края до края панели, а текст стоит на прежнем
# месте.
ITEM_PANEL_PADDING = ft.Padding.symmetric(horizontal=PANEL_HORIZONTAL_PADDING)
# Отступ от названия категории до первого пункта и промежуток между пунктами.
CATEGORY_ITEMS_TOP = 8
ITEM_SPACING = 4
# Промежуток между пунктами — внутренний отступ ячейки строки, а не `spacing`
# колонки: свёрнутая при перетаскивании строка остаётся в контейнере нулевой
# высоты, и `spacing` вокруг неё давал бы панели категории лишнюю высоту —
# остаток на месте пункта. Ячейка же сворачивается вместе со строкой.
ITEM_CELL_PADDING = ft.Padding.only(bottom=ITEM_SPACING)
# Отступ контейнера пунктов от названия категории.
ITEMS_BOX_PADDING = ft.Padding.only(top=CATEGORY_ITEMS_TOP)
# Перетаскивание пункта: порог движения пальца, после которого долгое
# нажатие считается перетаскиванием, и автопрокрутка у краёв списка
# (см. docs/Design.md).
ITEM_DRAG_THRESHOLD = 8
# Зона у верхней/нижней границы экрана, где список прокручивается сам. Выход из
# зоны — на AUTOSCROLL_HYSTERESIS дальше, чем вход: палец, дрожащий на границе,
# иначе включал бы и выключал прокрутку на каждом событии движения.
AUTOSCROLL_EDGE = 48
AUTOSCROLL_HYSTERESIS = 16
# Скорость автопрокрутки (px/с) и остаток до края списка (px), при котором
# прокрутка считается законченной и новых проходов не заказывается.
AUTOSCROLL_SPEED = 700.0
AUTOSCROLL_REST = 0.5
# Насколько должен вырасти список за проход, чтобы прокрутку стоило продолжить.
# Меньше — это округление при раскладке, а не уехавший вниз конец списка.
AUTOSCROLL_EXTENT_EPS = 1.0
# Нижний отступ списка: последняя категория не прячется под button_area.
LIST_BOTTOM_PADDING = BUTTON_AREA_HEIGHT + BUTTON_AREA_MARGIN + LIST_PADDING
# Оценка высот, пока клиент не разложил строку: за пределами видимой области
# `size_change` не приходит. Одна строка пункта на устройстве — 48 px (высоту
# задаёт чекбокс), название категории — 29 px (20 px × 1.45). Оценка нужна
# только строкам, которых не видно; рядом с пальцем всё измерено.
ITEM_ROW_HEIGHT_FALLBACK = 48.0
CATEGORY_TITLE_HEIGHT_FALLBACK = CATEGORY_TITLE_SIZE * CATEGORY_TITLE_LINE_HEIGHT

# Иконки лежат в src/assets/icons (assets_dir по умолчанию — "assets"
# относительно main.py), поэтому пути указываются от каталога assets.
ICON_PLUS = "icons/plus-sign.webp"
ICON_PENCIL = "icons/pencil.webp"
ICON_TRASH = "icons/trash-bin.webp"

# Слоты button_area по порядку сверху вниз. Иконка у слота постоянная: у
# категорий и пунктов они совпадают (см. docs/Design.md), поэтому при смене
# выделения меняется действие слота, а не картинка.
BUTTON_ICONS = (ICON_PLUS, ICON_PENCIL, ICON_TRASH)

# Подписи кнопок для TalkBack: иконки у категорий и пунктов одинаковые, так
# что текущее действие пользователь узнаёт по контексту, а озвучка — отсюда.
LABEL_CREATE_CATEGORY = "Создать категорию"
LABEL_RENAME_CATEGORY = "Переименовать категорию"
LABEL_DELETE_CATEGORY = "Удалить категорию"
LABEL_ADD_ITEM = "Добавить пункт"
LABEL_RENAME_ITEM = "Переименовать пункт"
LABEL_DELETE_ITEM = "Удалить пункт"


def _no_op(event: ft.ControlEvent):
    """Заглушка обработчика: тап по кнопке даёт ripple, но ничего не делает."""


@dataclass(frozen=True)
class ButtonAction:
    """Действие одного слота button_area.

    Кнопки постоянные (плюс, карандаш, корзина), а действие зависит от
    выделения: у категорий и пунктов иконки одни и те же, поэтому слот хранит
    только подпись (её читает TalkBack), обработчик и видимость.
    """

    label: str
    handler: Callable[..., object] = _no_op
    visible: bool = True


def bind_button(button: ft.Container, action: ButtonAction) -> None:
    """Назначает кнопке button_area действие для текущего выделения.

    Виджет не пересоздаётся: меняются подпись, обработчик и видимость, поэтому
    кнопка не мигает и не сдвигается. Обработчик Flet ищет на сервере в момент
    события (`Control._trigger_event`), так что новое действие работает сразу,
    а подпись уходит клиенту со следующим `page.update()`.
    """
    button.content.semantics_label = action.label
    button.on_click = action.handler
    button.visible = action.visible


def icon_button(icon_src: str, action: ButtonAction) -> ft.Container:
    """Круглая кнопка с иконкой для button_area.

    Подсказка задана только через semantics_label: виджет tooltip перехватывает
    долгое нажатие и задерживает эффект тапа (проверено на устройстве).
    """
    button = ft.Container(
        width=BUTTON_SIZE,
        height=BUTTON_SIZE,
        # Радиус 28 (= половина стороны) вместо shape=CIRCLE: Flet передаёт
        # в InkWell только border_radius, и splash тапа обрезается по кругу.
        border_radius=BUTTON_SIZE / 2,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        shadow=ft.BoxShadow(
            blur_radius=6,
            offset=ft.Offset(0, 2),
            color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
        ),
        alignment=ft.Alignment.CENTER,
        ink=True,
        content=ft.Image(
            src=icon_src,
            width=BUTTON_ICON_SIZE,
            height=BUTTON_ICON_SIZE,
            fit=ft.BoxFit.CONTAIN,
        ),
    )
    bind_button(button, action)
    return button


def create_button_area(actions: Sequence[ButtonAction]) -> ft.Container:
    """button_area: контейнер из трёх кнопок управления справа снизу.

    Слоты постоянные — плюс, карандаш, корзина (`BUTTON_ICONS`), — а действия
    для текущего выделения задаёт ``actions``: ровно по одному на слот.
    Какое действие попадает в какой слот, решает `ChecklistApp._actions()`.
    """
    if len(actions) != len(BUTTON_ICONS):
        raise ValueError(
            f"button_area: нужно {len(BUTTON_ICONS)} действия, "
            f"передано {len(actions)}"
        )
    return ft.Container(
        right=BUTTON_AREA_MARGIN,
        bottom=BUTTON_AREA_MARGIN,
        content=ft.Column(
            spacing=BUTTON_SPACING,
            tight=True,
            controls=[
                icon_button(icon_src, action)
                for icon_src, action in zip(BUTTON_ICONS, actions, strict=True)
            ],
        ),
    )


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
        on_tap=_no_op,
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


def item_event_handler(
    handler: Callable[[ItemView | CategoryView], object] | None,
    view: ItemView | CategoryView,
):
    """Обработчик жеста пункта или категории: передаёт приложению сам вид.

    Flet ждёт от асинхронного обработчика корутину, а `lambda`, возвращающая
    корутину, — обычная функция: её результат никто не ждёт. Поэтому обёртка —
    `async def`, а результат вызывается, только если это корутина: выделение и
    тап асинхронные (виброотклик), отмена перетаскивания — синхронная.
    """

    async def handle(event: ft.ControlEvent | None) -> None:
        if handler is None:
            return
        result = handler(view)
        if isinstance(result, Awaitable):
            await result

    return handle


def view_event_handler(
    handler: Callable[[ItemView | CategoryView, ft.Event], object] | None,
    view: ItemView | CategoryView,
):
    """Обработчик события с видом и самим событием: жесты и отметка пункта.

    Flet передаёт событие первым аргументом, а обработчику приложения нужен ещё
    и вид, к которому событие относится (пункт или категория), поэтому
    обработчики замыкаются на вид. Из события берутся координаты пальца (жесты
    перетаскивания) либо новое значение чекбокса; сам вид известен заранее.
    Обработчик может быть синхронным (движение) и асинхронным (отпускание
    сохраняет порядок, переключение отметки пишет в БД), поэтому результат
    ожидается только если это корутина.
    """

    async def handle(event: ft.Event) -> None:
        if handler is None:
            return
        result = handler(view, event)
        if isinstance(result, Awaitable):
            await result

    return handle


# Геометрия списка для перетаскивания пунктов.
#
# Сервер не знает координат контролов, поэтому раскладка собирается из высот,
# которые клиент присылает событием `size_change` (`ItemView.height`,
# `CategoryView.title_height`), и констант шаблона. Координаты — в логических
# пикселях, как и позиции пальца в событиях жестов; начало координат — верх
# списка (отступ `LIST_PADDING`). Абсолютное смещение не важно: в начале
# перетаскивания раскладка привязывается к реальному положению нажатой строки
# (см. `ChecklistApp._on_item_drag_start`).


@dataclass(frozen=True)
class DragEntry:
    """Строка пункта или зазор на месте вставки в раскладке перетаскивания.

    ``row_index`` — номер строки среди оставшихся в категории (без
    перетаскиваемой); у зазора и у самой перетаскиваемой строки его нет.
    """

    top: float
    bottom: float
    row_index: int | None = None
    gap: bool = False

    @property
    def is_row(self) -> bool:
        return self.row_index is not None


@dataclass(frozen=True)
class DragSpan:
    """Панель категории в раскладке перетаскивания пункта."""

    top: float
    bottom: float
    items_top: float
    entries: tuple[DragEntry, ...]

    @property
    def row_count(self) -> int:
        """Сколько строк категории остаётся, не считая перетаскиваемой."""
        return sum(1 for entry in self.entries if entry.is_row)


def base_row_top(
    metrics: Sequence[tuple[float, Sequence[float]]],
    category_index: int,
    row_index: int,
) -> float:
    """Верх строки в исходной раскладке списка (до сворачивания строки).

    Нужен, чтобы привязать раскладку к пальцу: точка нажатия внутри строки
    минус её верх в модели — это экранное начало координат списка.
    """
    top = LIST_PADDING
    for index, (title_height, heights) in enumerate(metrics):
        items_top = (
            top
            + CATEGORY_PANEL_VERTICAL_PADDING
            + title_height
            + CATEGORY_ITEMS_TOP
        )
        if index == category_index:
            return items_top + sum(
                height + ITEM_SPACING for height in heights[:row_index]
            )
        top = _panel_bottom(items_top, heights) + CATEGORY_SPACING
    raise IndexError(category_index)


def build_drag_spans(
    metrics: Sequence[tuple[float, Sequence[float]]],
    *,
    source: tuple[int, int],
    height: float,
    target: tuple[int, int],
) -> list[DragSpan]:
    """Раскладка списка во время перетаскивания пункта.

    ``metrics`` — пары «высота названия категории, высоты её пунктов» в порядке
    списка. Строка перетаскиваемого пункта свёрнута и места не занимает, а на
    месте будущей вставки ``target`` стоит зазор высотой в целый слот пункта
    (`item_slot_height`): панели категорий расходятся так же, как при
    перетаскивании категории, и место вставки видно до отпускания. Слоты
    остальных пунктов — тоже целые: промежуток принадлежит ячейке строки, поэтому
    у панели нижний отступ на промежуток меньше, пока в ней есть что показывать
    (см. `category_panel_padding`). ``source`` — (категория, строка)
    перетаскиваемого пункта, ``target`` — (категория, номер строки среди
    оставшихся), куда он встанет.
    """
    spans: list[DragSpan] = []
    top = LIST_PADDING
    for category_index, (title_height, heights) in enumerate(metrics):
        items_top = (
            top
            + CATEGORY_PANEL_VERTICAL_PADDING
            + title_height
            + CATEGORY_ITEMS_TOP
        )
        # Слоты категории по порядку: высота, номер оставшейся строки (None —
        # свёрнутая строка или зазор), признак зазора.
        slots: list[tuple[float, int | None, bool]] = []
        remaining = 0
        for row_index, row_height in enumerate(heights):
            if (category_index, row_index) == source:
                slots.append((0.0, None, False))
                continue
            slots.append((row_height, remaining, False))
            remaining += 1
        if target[0] == category_index:
            position = len(slots)
            seen = 0
            for slot_index, (_, row_index, _) in enumerate(slots):
                if row_index is None:
                    continue
                if seen == target[1]:
                    position = slot_index
                    break
                seen += 1
            slots.insert(position, (item_slot_height(height), None, True))
        entries: list[DragEntry] = []
        # Низ содержимого контейнера и признак того, что показывать есть что:
        # зазор или хотя бы одна несвёрнутая строка.
        content_bottom = items_top
        has_content = False
        for slot_height, row_index, is_gap in slots:
            entries.append(
                DragEntry(
                    top=content_bottom,
                    bottom=content_bottom + slot_height,
                    row_index=row_index,
                    gap=is_gap,
                )
            )
            if is_gap:
                content_bottom += slot_height
                has_content = True
            elif row_index is not None:
                content_bottom += item_slot_height(slot_height)
                has_content = True
        if has_content:
            panel_bottom = content_bottom + category_panel_padding(True).bottom
        else:
            # Контейнер пунктов ничего не показывает и отступов не несёт: в
            # панели только название.
            panel_bottom = (
                items_top - CATEGORY_ITEMS_TOP + CATEGORY_PANEL_VERTICAL_PADDING
            )
        spans.append(
            DragSpan(
                top=top,
                bottom=panel_bottom,
                items_top=items_top,
                entries=tuple(entries),
            )
        )
        top = panel_bottom + CATEGORY_SPACING
    return spans


def _panel_bottom(items_top: float, heights: Sequence[float]) -> float:
    """Низ панели категории по её строкам (без зазоров перетаскивания)."""
    if heights:
        return (
            items_top
            + sum(heights)
            + ITEM_SPACING * (len(heights) - 1)
            + CATEGORY_PANEL_VERTICAL_PADDING
        )
    return items_top - CATEGORY_ITEMS_TOP + CATEGORY_PANEL_VERTICAL_PADDING


def category_panel_height(
    title_height: float, heights: Sequence[float]
) -> float:
    """Высота панели категории по шаблону: название, пункты и отступы.

    Нужна, когда клиент ещё не прислал размер самой панели (она за пределами
    видимой области). Считается по тем же правилам, что и `build_drag_spans`:
    промежуток принадлежит ячейке строки, поэтому нижний отступ панели меньше
    на него, пока в ней есть что показывать (`category_panel_padding`).
    """
    if heights:
        return (
            CATEGORY_PANEL_VERTICAL_PADDING
            + title_height
            + CATEGORY_ITEMS_TOP
            + sum(item_slot_height(height) for height in heights)
            + category_panel_padding(True).bottom
        )
    return CATEGORY_PANEL_VERTICAL_PADDING * 2 + title_height


def category_base_top(slots: Sequence[float], index: int) -> float:
    """Верх панели категории в модели списка (до её перетаскивания).

    Нужен, чтобы привязать раскладку к пальцу: экранная точка нажатия минус
    верх названия в модели — это экранное начало координат списка.
    """
    return LIST_PADDING + sum(slots[:index])


@dataclass(frozen=True)
class CategorySpan:
    """Категория или зазор на месте вставки в раскладке перетаскивания.

    ``index`` — номер категории среди оставшихся (без перетаскиваемой); у
    зазора его нет.
    """

    top: float
    bottom: float
    index: int | None = None

    @property
    def is_gap(self) -> bool:
        return self.index is None


def build_category_spans(
    slots: Sequence[float], *, dragged: int, target: int
) -> list[CategorySpan]:
    """Раскладка списка во время перетаскивания категории.

    ``slots`` — высоты слотов (панель вместе с промежутком до следующей) в
    порядке списка, ``dragged`` — индекс перетаскиваемой категории, ``target`` —
    место зазора среди оставшихся категорий (``0..n``). Слот перетаскиваемой
    свёрнут и места не занимает: на её месте стоит зазор той же высоты, поэтому
    остальные категории не сдвигаются ни в первый миг перетаскивания, ни после
    отпускания.
    """
    spans: list[CategorySpan] = []
    top = LIST_PADDING
    remaining = [index for index in range(len(slots)) if index != dragged]
    gap_height = slots[dragged] if dragged < len(slots) else 0.0
    for position in range(len(remaining) + 1):
        if position == target:
            spans.append(CategorySpan(top=top, bottom=top + gap_height))
            top += gap_height
        if position < len(remaining):
            index = remaining[position]
            spans.append(
                CategorySpan(top=top, bottom=top + slots[index], index=position)
            )
            top += slots[index]
    return spans


def category_span_at(spans: Sequence[CategorySpan], y: float) -> int:
    """Место вставки (номер среди оставшихся категорий) под координатой ``y``.

    Категория встаёт перед той, чья середина ниже пальца: перестановка
    начинается, когда палец проходит половину панели, а не на её границе.
    Зазор в подсчёте не участвует, поэтому место вставки не зависит от того,
    где зазор стоит сейчас, и не дрожит, когда он переезжает.
    """
    count = 0
    for span in spans:
        if span.is_gap:
            continue
        if y < (span.top + span.bottom) / 2:
            return count
        count += 1
    return count


def span_index_at(spans: Sequence[DragSpan], y: float) -> int:
    """Категория под координатой ``y`` или ближайшая к ней.

    Промежутки между категориями и отступы списка принадлежат ближайшей панели:
    отпускание пальца в промежутке не должно оставлять пункт без нового места.
    """
    for index, span in enumerate(spans):
        if span.top <= y <= span.bottom:
            return index
    best_index = 0
    best_distance: float | None = None
    for index, span in enumerate(spans):
        distance = span.top - y if y < span.top else y - span.bottom
        if best_distance is None or distance < best_distance:
            best_index, best_distance = index, distance
    return best_index


def drag_slot_at(spans: Sequence[DragSpan], y: float) -> tuple[int, int]:
    """Категория и место вставки (номер строки среди оставшихся) под пальцем.

    Пункт встаёт перед строкой, чья середина ниже пальца: перестановка
    начинается, когда палец проходит половину строки, а не на её границе.
    Зазор и свёрнутая строка в подсчёте не участвуют — поэтому место вставки
    не зависит от того, где зазор стоит сейчас.
    """
    index = span_index_at(spans, y)
    span = spans[index]
    if y < span.items_top:
        return index, 0
    for entry in span.entries:
        if not entry.is_row:
            continue
        if y < (entry.top + entry.bottom) / 2:
            return index, entry.row_index
    return index, span.row_count


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


@dataclass(frozen=True)
class ItemGestures:
    """Жесты пункта и переключение его отметки.

    Пункт создаётся категорией, поэтому обработчики передаются одним объектом:
    шесть отдельных параметров раздували бы конструкторы `CategoryView` и
    `ItemView`. `long_press` и `tap` вызываются без события (пункт уже известен),
    `drag_*` и `toggle` — с событием: из него берутся координаты пальца у
    жестов, а у отметки — новое значение чекбокса.
    """

    long_press: Callable[[ItemView], object] | None = None
    drag_start: Callable[[ItemView, ft.LongPressStartEvent], object] | None = None
    drag_move: Callable[[ItemView, ft.LongPressMoveUpdateEvent], object] | None = None
    drag_end: Callable[[ItemView, ft.LongPressEndEvent], object] | None = None
    drag_cancel: Callable[[ItemView], object] | None = None
    tap: Callable[[ItemView], object] | None = None
    toggle: Callable[[ItemView, ft.ControlEvent], object] | None = None


@dataclass(frozen=True)
class CategoryGestures:
    """Жесты категории: выделение и перетаскивание всей панели.

    Категория ловит их сама (как и пункт), а не через `ReorderableListView`:
    штатный drag прокручивал список, когда край экрана касалась любая часть
    категории, и длинная категория уезжала сразу (см. `_autoscroll_span()`).
    Внутри панели лежат строки пунктов со своими жестами — они глубже в дереве и
    выигрывают арену, поэтому долгое нажатие по пункту поднимает пункт.
    Обработчики передаются одним объектом: `drag_*` получают ещё и событие
    жеста — из него берутся координаты пальца.
    """

    long_press: Callable[[CategoryView], object] | None = None
    drag_start: Callable[[CategoryView, ft.LongPressStartEvent], object] | None = None
    drag_move: Callable[
        [CategoryView, ft.LongPressMoveUpdateEvent], object
    ] | None = None
    drag_end: Callable[[CategoryView, ft.LongPressEndEvent], object] | None = None
    drag_cancel: Callable[[CategoryView], object] | None = None


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


CATEGORY_ITEM_PADDING = ft.Padding.only(bottom=CATEGORY_SPACING)


def create_category_item(panel: ft.Control) -> ft.Container:
    """Элемент списка: панель категории вместе с промежутком до следующей.

    Промежуток — внутренний отступ обёртки, а не `margin` панели, и не `spacing`
    списка: `spacing` давал бы промежуток и после последней категории. При
    перетаскивании обёртка сворачивается вместе с панелью (отступ снимается), а
    её `margin` занимает зазор на месте будущей вставки.
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


class TitledView:
    """Общая часть категории и пункта: название и ввод нового названия.

    Ввод устроен одинаково: поле занимает место названия (`title_slot`), а
    после завершения на его место возвращается текст. Различаются только
    стиль текста, подсказка и операция хранилища.
    """

    default_title: str

    def __init__(self, title: str) -> None:
        self.title = title
        self.input: ft.TextField | None = None
        self.title_text = self.create_title_text(title)
        self.title_slot = ft.Container(content=self.title_text)

    @property
    def is_editing(self) -> bool:
        return self.input is not None

    def show_input(self, field: ft.TextField) -> None:
        """Ставит поле ввода на место названия."""
        self.input = field
        self.title_slot.content = field

    def show_title(self) -> None:
        """Возвращает текст названия на место поля ввода."""
        self.input = None
        self.title_text.value = self.title
        self.title_slot.content = self.title_text

    # Реализуют подклассы: категория и пункт отличаются стилем и хранилищем.
    def create_title_text(self, title: str) -> ft.Text:
        raise NotImplementedError

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        raise NotImplementedError

    def save_title(self, storage: Storage, title: str) -> str:
        raise NotImplementedError


class CategoryView(TitledView):
    """Категория на экране: панель с названием, пункты, выделение и ввод."""

    default_title = domain.DEFAULT_CATEGORY_TITLE

    def __init__(
        self,
        category: domain.Category,
        items: Sequence[domain.Item] = (),
        *,
        gestures: ItemGestures | None = None,
        category_gestures: CategoryGestures | None = None,
    ) -> None:
        super().__init__(category.title)
        self.category = category
        # Обработчики жестов пунктов передаёт приложение: без них пункт не смог
        # бы выделяться и не знал бы о выделении своей категории.
        self.gestures = gestures or ItemGestures()
        # Обработчики перетаскивания самой категории: выделение и drag за
        # название.
        self.category_gestures = category_gestures or CategoryGestures()
        # Горизонтальный отступ названия переехал с панели на слот названия:
        # так фон выделенного пункта закрашивает всю ширину панели.
        self.title_slot.padding = CATEGORY_TITLE_PADDING
        # Высота названия нужна модели перетаскивания пунктов: по ней считается,
        # где внутри панели начинается контейнер пунктов.
        self.title_height: float | None = None
        self.title_slot.on_size_change = self._on_title_size_change
        # Размеры панели: приходят от клиента и нужны перетаскиванию категории —
        # по ним строятся прокси и зазор, а свёрнутая панель их не меняет.
        self.height: float | None = None
        self.width: float | None = None
        self._collapsed = False
        self.items: list[ItemView] = []
        self.items_box = create_items_box()
        # Зазор на месте вставки: лежит в контейнере пунктов, пока идёт
        # перетаскивание; создаётся приложением на каждый drag.
        self.gap_index: int | None = None
        self.panel = create_category_panel(
            create_category_content(self.title_slot, self.items_box)
        )
        self.panel.on_size_change = self._on_panel_size_change
        # Жесты категории — на обёртке панели, а не на названии: панель
        # сворачивается при перетаскивании, и распознаватель внутри неё клиент
        # пересоздал бы вместе с содержимым — жест оборвался бы на первом же
        # обновлении экрана (см. `collapse`). Так же устроена строка пункта.
        self.gesture_area = ft.GestureDetector(content=self.panel)
        self.gesture_area.on_long_press = item_event_handler(
            self.category_gestures.long_press, self
        )
        self.gesture_area.on_long_press_start = view_event_handler(
            self.category_gestures.drag_start, self
        )
        self.gesture_area.on_long_press_move_update = view_event_handler(
            self.category_gestures.drag_move, self
        )
        self.gesture_area.on_long_press_end = view_event_handler(
            self.category_gestures.drag_end, self
        )
        self.gesture_area.on_long_press_cancel = item_event_handler(
            self.category_gestures.drag_cancel, self
        )
        self.item = create_category_item(self.gesture_area)
        self.selected = False
        for item in items:
            self.append_item(item)
        self._sync_items_box()

    def create_title_text(self, title: str) -> ft.Text:
        return create_category_title(title)

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        return create_category_input(
            self.default_title, on_commit, value, on_tap_outside
        )

    def save_title(self, storage: Storage, title: str) -> str:
        return storage.set_category_title(self.category.id, title)

    def _on_title_size_change(self, event: ft.LayoutSizeChangeEvent) -> None:
        """Клиент сообщил высоту названия: она нужна модели перетаскивания."""
        self.title_height = event.height

    def _on_panel_size_change(self, event: ft.LayoutSizeChangeEvent) -> None:
        """Клиент сообщил размер панели: по нему строятся прокси и зазор.

        Пока панель свёрнута, её высота равна нулю — это не настоящий размер
        панели, и запоминать его нельзя (как и у свёрнутой строки пункта).
        """
        if self._collapsed:
            return
        self.height = event.height
        self.width = event.width

    @property
    def collapsed(self) -> bool:
        """Панель свёрнута: на её месте стоит зазор, сама она в прокси."""
        return self._collapsed

    def collapse(self) -> None:
        """Сворачивает панель: её место занимает зазор, а саму её показывает прокси.

        Высота меняется у самой панели, а не у обёртки с `GestureDetector`:
        иначе клиент пересоздал бы распознаватель, и жест перетаскивания
        оборвался бы на первом же обновлении экрана. Промежуток до следующей
        категории принадлежит обёртке, поэтому снимается и он: иначе на месте
        категории осталась бы лишняя высота — остаток, который пропадал бы
        только после отпускания.
        """
        self._collapsed = True
        self.panel.height = 0
        self.item.padding = None

    def restore(self) -> None:
        """Возвращает панель на место после перетаскивания."""
        self._collapsed = False
        self.panel.height = None
        self.item.padding = CATEGORY_ITEM_PADDING

    def place_gap(
        self, gap: ft.Container, index: int, dragged: ItemView | None = None
    ) -> None:
        """Ставит зазор на место вставки: перед строкой ``index``.

        ``index`` — номер строки среди оставшихся (без перетаскиваемой),
        ``0..n``: ``n`` — в конец категории. Контейнер пунктов остаётся
        видимым, пока в нём лежит свёрнутая строка: иначе она исчезла бы из
        дерева вместе с жестом.
        """
        controls: list[ft.Control] = []
        remaining = 0
        placed = False
        for view in self.items:
            if not placed and remaining == index:
                controls.append(gap)
                placed = True
            if view is not dragged:
                remaining += 1
            controls.append(view.cell)
        if not placed:
            controls.append(gap)
        self.items_box.content.controls = controls
        self.gap_index = index
        self._sync_items_box()

    def remove_gap(self) -> None:
        """Убирает зазор и возвращает контейнеру пунктов обычный вид."""
        self.items_box.content.controls = [view.cell for view in self.items]
        self.gap_index = None
        self._sync_items_box()

    def append_item(self, item: domain.Item) -> "ItemView":
        """Добавляет пункт в конец контейнера пунктов категории."""
        view = ItemView(item, self.gestures)
        view.category_view = self
        self.items.append(view)
        self.items_box.content.controls.append(view.cell)
        self._sync_items_box()
        return view

    def _sync_items_box(self) -> None:
        """Приводит контейнер пунктов и отступы панели к их содержимому.

        Промежуток между пунктами принадлежит ячейке строки, поэтому у панели
        нижний отступ на этот промежуток меньше, пока в контейнере есть что
        показывать. Если показывать нечего (в категории осталась только свёрнутая
        строка перетаскиваемого пункта), контейнер не занимает места вовсе: панель
        выглядит как у категории без пунктов, поэтому после отпускания её высота
        не меняется.
        """
        has_box = bool(self.items) or self.gap_index is not None
        has_content = self.gap_index is not None or any(
            not item.collapsed for item in self.items
        )
        self.items_box.visible = has_box
        self.items_box.padding = ITEMS_BOX_PADDING if has_content else None
        self.panel.padding = category_panel_padding(has_content)

    def set_selected(self, selected: bool) -> None:
        """Выделенная категория отличается от остальных цветом панели."""
        self.selected = selected
        self.panel.bgcolor = (
            CATEGORY_PANEL_SELECTED_COLOR if selected else CATEGORY_PANEL_COLOR
        )


class ItemView(TitledView):
    """Пункт на экране: чекбокс слева, название справа.

    Пункт лежит внутри панели категории, поэтому в обычном состоянии его фон
    прозрачный: сквозь него видна панель, в том числе когда категория выделена.
    Выделенный пункт закрашивается тем же цветом, что и выделенная категория.
    Отметка показывается чекбоксом из БД, а отмеченная строка — серая
    (`ITEM_CHECKED_COLOR`): тап по чекбоксу переключает отметку и пишет её в БД
    (см. `ChecklistApp.toggle_item_checked`).
    """

    default_title = domain.DEFAULT_ITEM_TITLE

    def __init__(
        self,
        item: domain.Item,
        gestures: ItemGestures | None = None,
    ) -> None:
        # Пункт запоминается до создания названия: от отмеченности зависит стиль
        # текста (отмеченный пункт — серый), а `create_title_text` вызывается
        # из конструктора базового класса.
        self.item = item
        super().__init__(item.title)
        self.gestures = gestures or ItemGestures()
        # Категория, в панели которой лежит пункт: по ней решается, что делает
        # тап — внутри выделенной категории он выделяет пункт.
        self.category_view: CategoryView | None = None
        self.selected = False
        # Размеры строки: приходят от клиента (`size_change`) и нужны модели
        # перетаскивания, чтобы знать, где кончается один пункт и начинается
        # следующий, а прокси — чтобы совпасть со строкой по размеру.
        self.height: float | None = None
        self.width: float | None = None
        # Название занимает всё место справа от чекбокса и переносится
        # на вторую строку внутри этой ширины.
        self.title_slot.expand = True
        self.checkbox = create_item_checkbox(item)
        # Чекбокс с прозрачным запирающим слоем: пока что-то выделено или идёт
        # ввод названия, слой виден и ловит тап, поэтому чекбокс не переключается
        # даже на мгновение (см. `create_checkbox_blocker`). Показывать слой
        # приложению помогает `_apply_selection()`.
        self.checkbox_area, self.checkbox_blocker = create_item_checkbox_area(
            self.checkbox
        )
        # Отметку переключает сам чекбокс: тап по нему не доходит до жестов
        # строки (вложенный распознаватель выигрывает арену), поэтому выделение
        # от него не меняется. Что делать с отметкой (её можно менять только
        # без выделения) решает приложение.
        self.checkbox.on_change = view_event_handler(self.gestures.toggle, self)
        self.panel = create_item_panel(self.checkbox_area, self.title_slot)
        self.row = create_item_row(self.panel)
        # Ячейка в контейнере пунктов: строка вместе с промежутком до следующей
        # (см. `create_item_cell`). Она же сворачивается вместе со строкой.
        self.cell = create_item_cell(self.row)
        self._collapsed = False
        # Жесты назначаются после создания строки: обработчики замыкаются на
        # сам пункт. Долгое нажатие приходит двумя событиями — `start` даёт
        # координаты пальца для перетаскивания, `long_press` выделяет пункт
        # (порядок событий задаёт Flutter: сначала `start`).
        self.row.on_tap = item_event_handler(self.gestures.tap, self)
        self.row.on_long_press = item_event_handler(self.gestures.long_press, self)
        self.row.on_long_press_start = view_event_handler(
            self.gestures.drag_start, self
        )
        self.row.on_long_press_move_update = view_event_handler(
            self.gestures.drag_move, self
        )
        self.row.on_long_press_end = view_event_handler(self.gestures.drag_end, self)
        self.row.on_long_press_cancel = item_event_handler(
            self.gestures.drag_cancel, self
        )
        self.row.on_size_change = self._on_row_size_change

    def _on_row_size_change(self, event: ft.LayoutSizeChangeEvent) -> None:
        """Клиент сообщил размер строки: он нужен модели перетаскивания.

        Пока строка свёрнута, её высота равна нулю — это не настоящий размер
        строки, и запоминать его нельзя.
        """
        if self._collapsed:
            return
        self.height = event.height
        self.width = event.width

    @property
    def collapsed(self) -> bool:
        """Строка свёрнута: она остаётся в дереве, но места не занимает."""
        return self._collapsed

    def collapse(self) -> None:
        """Сворачивает строку: её место занимает зазор, а саму строку показывает прокси.

        Высота меняется у самой панели строки, а не у обёртки над
        `GestureDetector`: иначе Flutter пересоздал бы распознаватель, и жест
        перетаскивания оборвался бы на первом же обновлении экрана. Промежуток до
        следующего пункта принадлежит ячейке, поэтому сворачивается и она: иначе
        в контейнере осталась бы лишняя высота на месте пункта.
        """
        self._collapsed = True
        self.panel.height = 0
        self.cell.padding = None
        self._sync_category()

    def restore(self) -> None:
        """Возвращает строку на место после перетаскивания."""
        self._collapsed = False
        self.panel.height = None
        self.cell.padding = ITEM_CELL_PADDING
        self._sync_category()

    def _sync_category(self) -> None:
        """Сообщает категории, что строк стало видно меньше или больше."""
        if self.category_view is not None:
            self.category_view._sync_items_box()

    def create_title_text(self, title: str) -> ft.Text:
        return create_item_title(title, checked=self.item.is_checked)

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        return create_item_input(self.default_title, on_commit, value, on_tap_outside)

    def save_title(self, storage: Storage, title: str) -> str:
        return storage.set_item_title(self.item.id, title)

    def set_checkbox_blocked(self, blocked: bool) -> None:
        """Запирает чекбокс прозрачным слоем, не меняя его вид.

        Клик по чекбоксу в запертом состоянии не доходит до него вовсе, поэтому
        он не переключается даже на мгновение (см. `create_checkbox_blocker`).
        """
        self.checkbox_blocker.visible = blocked

    def set_checked(self, checked: bool) -> None:
        """Применяет отметку к строке: чекбокс и серый цвет отмеченного пункта.

        Модель (`item`) и вид обновляются вместе: чекбокс показывает отметку из
        модели, а название перекрашивается в серый. Размер и положение строки
        при этом не меняются — меняются только цвета.
        """
        self.item = replace(self.item, is_checked=checked)
        self.checkbox.value = checked
        self.checkbox.active_color = ITEM_CHECKED_COLOR if checked else None
        self.title_text.style = item_title_style(checked)

    def set_selected(self, selected: bool) -> None:
        """Выделенный пункт красится тем же цветом, что и выделенная категория."""
        self.selected = selected
        self.panel.bgcolor = (
            ITEM_PANEL_SELECTED_COLOR if selected else ITEM_PANEL_COLOR
        )


@dataclass
class ItemDrag:
    """Перетаскивание пункта: состояние от долгого нажатия до отпускания.

    Строка «поднимается»: её панель сворачивается, в `Stack` над списком
    появляется её копия (`proxy`), которая двигается за пальцем по вертикали, а
    в контейнере пунктов на месте будущей вставки стоит зазор (`gap`). ``origin_y``
    — экранный верх содержимого списка, ``grab_y`` — высота, на которой палец взял
    строку, ``target`` — (категория, номер строки среди оставшихся), где сейчас
    зазор. Положение прокси по горизонтали не хранится: пункт едет в своём
    столбце, как категория. ``epoch`` нумерует запуски автопрокрутки, чтобы
    старый цикл не продолжал работать после остановки, а ``pass_extent`` — докуда
    список мог прокрутиться вниз в начале текущего прохода: по нему видно, вырос
    ли список за проход.
    """

    view: ItemView
    source: tuple[int, int]
    height: float
    origin_y: float
    grab_y: float
    start_y: float
    target: tuple[int, int]
    proxy: ft.Container | None = None
    gap: ft.Container | None = None
    moved: bool = False
    autoscroll: int = 0
    epoch: int = 0
    pass_extent: float | None = None


@dataclass
class CategoryDrag:
    """Перетаскивание категории: состояние от долгого нажатия до отпускания.

    Панель «поднимается»: её место в списке сворачивается, а над списком
    появляется её копия (`proxy`), которая двигается за пальцем по вертикали.
    На месте будущей вставки стоит зазор — `margin` того элемента списка, перед
    которым категория встанет (`_place_category_gap`). ``origin_y`` — экранный
    верх видимой области списка, ``grab_y`` — высота, на которой палец взял
    панель (считая от её верха, то есть с отступом панели), ``title_height`` —
    высота названия: по его полосе считается зона автопрокрутки. ``target`` —
    место вставки среди оставшихся категорий. Остальные поля — как у `ItemDrag`.
    """

    view: CategoryView
    source: int
    height: float
    width: float
    title_height: float
    origin_y: float
    grab_y: float
    start_y: float
    target: int
    proxy: ft.Container | None = None
    panel_top: float | None = None
    autoscroll: int = 0
    epoch: int = 0
    pass_extent: float | None = None

    @property
    def slot_height(self) -> float:
        """Сколько места занимает категория в списке: панель и промежуток."""
        return self.height + CATEGORY_SPACING

    def title_span(self) -> tuple[float, float] | None:
        """Экранные верх и низ области названия у поднятой панели.

        Зона автопрокрутки считается по этой полосе, а не по всей панели: иначе
        длинная категория касалась бы края экрана любым своим пунктом и список
        уезжал бы сразу после подъёма (см. `_autoscroll_span`).
        """
        if self.panel_top is None:
            return None
        top = self.panel_top + CATEGORY_PANEL_VERTICAL_PADDING
        return top, top + self.title_height


class ChecklistApp:
    """Экран списка категорий и обработчики button_area."""

    def __init__(
        self,
        page: ft.Page,
        storage: Storage,
        haptic: ft.HapticFeedback | None = None,
    ) -> None:
        self.page = page
        self.storage = storage
        # Сервис виброотклика: если не передан, создаётся в mount().
        self.haptic = haptic
        # Категории в порядке списка: индекс в нём совпадает с индексом
        # элемента в списке и с индексом в событиях перетаскивания.
        self.views: list[CategoryView] = []
        self.category_list = create_category_list()
        # Прокрутка нужна автопрокрутке при перетаскивании: по её событиям
        # видно, насколько содержимое уехало под пальцем.
        self.category_list.on_scroll = self._on_scroll
        self.category_area = create_category_area(
            self.category_list, self._on_tap, self._on_tap_cancel
        )
        self._editing_view: TitledView | None = None
        # Выделен ровно один элемент — категория или пункт: выделение категории
        # снимается при выделении пункта и наоборот (см. docs/Project.md).
        self._selected_view: CategoryView | None = None
        self._selected_item: ItemView | None = None
        # Идёт перетаскивание категории: кнопки button_area скрыты целиком.
        self._dragging = False
        # Перетаскивание пункта: состояние жеста, категория с зазором и
        # последняя точка пальца (по ней считается место вставки).
        self._item_drag: ItemDrag | None = None
        # Перетаскивание категории: состояние жеста, прокси и зазор.
        self._category_drag: CategoryDrag | None = None
        self._gap_category: CategoryView | None = None
        self._pointer_y: float | None = None
        # Прокрутка списка: нужна и автопрокрутке, и пересчёту места вставки.
        self._scroll_pixels = 0.0
        self._viewport: float | None = None
        # Докуда список может прокрутиться вниз: приходит с `on_scroll`, до
        # первой прокрутки неизвестно.
        self._max_scroll_extent: float | None = None
        # Жесты пунктов передаются категориям одним объектом: пункт создаётся
        # категорией и сам сообщает приложению, что с ним делают.
        self.gestures = ItemGestures(
            long_press=self._on_item_long_press,
            drag_start=self._on_item_drag_start,
            drag_move=self._on_item_drag_move,
            drag_end=self._on_item_drag_end,
            drag_cancel=self._on_item_drag_cancel,
            tap=self._on_item_tap,
            toggle=self.toggle_item_checked,
        )
        # Перетаскивание категории ведёт приложение: жест — долгое нажатие на
        # названии, дальше свои прокси, зазор и автопрокрутка по названию.
        self.category_gestures = CategoryGestures(
            long_press=self._on_category_long_press,
            drag_start=self._on_category_drag_start,
            drag_move=self._on_category_drag_move,
            drag_end=self._on_category_drag_end,
            drag_cancel=self._on_category_drag_cancel,
        )
        self.button_area = create_button_area(self._actions())
        (
            self.plus_button,
            self.pencil_button,
            self.trash_button,
        ) = self.button_area.content.controls
        # Прокси перетаскиваемого пункта живёт здесь же, выше списка: он должен
        # рисоваться поверх панелей категорий. Стек создаётся сразу, а не в
        # mount(), чтобы перетаскивание работало и в тестах без экрана.
        self.stack = ft.Stack(
            expand=True,
            fit=ft.StackFit.EXPAND,
            controls=[self.category_area, self.button_area],
        )
        self._keyboard_open = False
        # Тап вне поля закрыл клавиатуру: следующий on_tap списка — тот же
        # самый тап, он не должен снимать выделение (см. _on_tap).
        self._tap_ended_input = False
        self._apply_selection()

    async def mount(self) -> None:
        """Загружает категории и пункты из БД и собирает экран."""
        categories = await asyncio.to_thread(self.storage.list_categories)
        items = await asyncio.to_thread(self.storage.list_items)
        items_by_category: dict[int, list[domain.Item]] = {}
        for item in items:
            items_by_category.setdefault(item.category_id, []).append(item)
        for category in categories:
            self._append_category(category, items_by_category.get(category.id, ()))
        if self.haptic is None:
            self.haptic = ft.HapticFeedback()
            self.page.services.append(self.haptic)
        self.page.add(
            ft.SafeArea(
                expand=True,
                content=self.stack,
            )
        )
        # Жест «назад» на Android закрывает клавиатуру, не снимая фокус
        # с поля и не присылая on_blur: ввод завершаем по скрытию клавиатуры.
        self.page.on_media_change = self._on_media_change
        # «Назад» при выделенной категории перехватывается: вместо выхода
        # из приложения снимается выделение (см. _on_confirm_pop).
        self.page.views[0].on_confirm_pop = self._on_confirm_pop
        # Обработчики выше назначены после add() — отправляем их клиенту.
        self.page.update()
        if self.storage.recovered_backup is not None:
            self._show_message(
                "Файл данных был повреждён: создана пустая база. Прежние данные "
                f"потеряны (копия: {self.storage.recovered_backup.name})."
            )

    @staticmethod
    def _keyboard_visible(media: ft.PageMediaData) -> bool:
        """Клавиатура открыта. При adjustResize её высота не попадает в
        view_insets: Flutter отдаёт нулевой нижний системный отступ, и
        единственный признак — пропавший нижний padding навигации."""
        if media.device_pixel_ratio == 0:
            # page.media ещё не обновлён клиентом: данных о системе нет.
            return False
        return media.view_insets.bottom > 0 or media.padding.bottom == 0

    def _on_media_change(self, media: ft.PageMediaData) -> None:
        if self._keyboard_visible(media):
            self._keyboard_open = True
        elif self._keyboard_open:
            self._keyboard_open = False
            self._commit_editing()

    def _commit_editing(self) -> None:
        view = self._editing_view
        if view is not None:
            self.page.run_task(self._finish_title_input, view)

    async def create_category(self, event: ft.ControlEvent) -> None:
        """create_category: категория в конец списка, затем ввод названия."""
        try:
            category = await asyncio.to_thread(self.storage.create_category)
        except Exception:
            logger.exception("Не удалось создать категорию")
            self._show_message("Не удалось создать категорию")
            return
        view = self._append_category(category)
        await self._start_title_input(view, scroll_to_end=True)

    async def add_item(self, event: ft.ControlEvent | None = None) -> None:
        """add_item: пункт в конец выделенной категории, затем ввод названия.

        Запись в БД — до обновления экрана: при ошибке новый пункт не
        появляется и показывается сообщение. Поле ввода открывается сразу
        после создания пункта, с пустым значением и подсказкой «Пункт»:
        не введённое название остаётся дефолтным. Поля в фокусе Flutter сам
        показывает на экране, поэтому список к новому пункту прокручивается
        без явного scroll_to: категория не обязательно последняя.
        """
        view = self._selected_view
        if view is None or self._editing_view is not None:
            # Кнопка показана только при выделенной категории; ввод названия
            # скрывает button_area целиком, повторный вызов невозможен.
            return
        try:
            item = await asyncio.to_thread(self.storage.create_item, view.category.id)
        except Exception:
            logger.exception("Не удалось добавить пункт")
            self._show_message("Не удалось добавить пункт")
            return
        item_view = view.append_item(item)
        await self._start_title_input(item_view)

    async def rename_category(
        self, event: ft.ControlEvent | None = None
    ) -> None:
        """rename_category: ввод нового названия вместо названия категории.

        Поле открывается с прежним названием выделенной категории, поэтому
        ввод можно дополнить, а не набирать заново. Выделение при
        переименовании не снимается: после сохранения кнопки
        `rename_category`/`delete_category` остаются на месте.
        """
        view = self._selected_view
        if view is None or self._editing_view is not None:
            # Кнопка показана только при выделенной категории; ввод названия
            # скрывает button_area целиком, повторный вызов невозможен.
            return
        await self._start_title_input(view, initial=view.title)

    async def rename_item(self, event: ft.ControlEvent | None = None) -> None:
        """rename_item: ввод нового названия вместо названия пункта.

        Поле открывается с прежним названием выделенного пункта, поэтому
        ввод можно дополнить, а не набирать заново. Выделение при
        переименовании не снимается: после сохранения кнопки
        `rename_item`/`delete_item` остаются на месте. Ввод на месте названия
        обслуживает та же машинерия, что и у категории: `ItemView` — это
        `TitledView`, а запись идёт в `Storage.set_item_title()`.
        """
        view = self._selected_item
        if view is None or self._editing_view is not None:
            # Кнопка показана только при выделенном пункте; ввод названия
            # скрывает button_area целиком, повторный вызов невозможен.
            return
        await self._start_title_input(view, initial=view.title)

    async def delete_item(self, event: ft.ControlEvent | None = None) -> None:
        """delete_item: удаляет выделенный пункт из списка и из БД.

        Запись в БД — до обновления экрана: при ошибке пункт остаётся на месте
        и показывается сообщение. Выделение снимается: удалённого пункта больше
        нет, кнопки возвращаются к исходному составу. Порядок оставшихся берётся
        из БД, как и после перетаскивания, поэтому дыр в позициях не остаётся.
        """
        view = self._selected_item
        if view is None:
            # Кнопка показана только при выделенном пункте.
            return
        category = view.category_view
        if category is None or view not in category.items:
            return
        editing = self._editing_view
        if editing is view:
            # Ввод названия скрывает button_area целиком, так что сюда не
            # попадают; если состояние всё же такое, поле уходит вместе со
            # строкой, а не остаётся фокусом у несуществующего пункта.
            editing.input = None
            self._editing_view = None
            self._keyboard_open = False
        try:
            remaining = await asyncio.to_thread(
                self.storage.delete_item, view.item.id
            )
        except Exception:
            logger.exception("Не удалось удалить пункт")
            self._show_message("Не удалось удалить пункт")
            return
        self._selected_item = None
        view.set_selected(False)
        self._apply_item_orders({category.category.id: remaining})
        self._apply_selection()
        self.page.update()

    async def toggle_item_checked(
        self, view: ItemView, event: ft.ControlEvent | None = None
    ) -> None:
        """Отметка пункта: тап по чекбоксу переключает состояние и пишет его в БД.

        По спеке отметка переключается, только когда не выделена ни категория, ни
        пункт (docs/features/feature-item.md). Обычный тап в это время до
        чекбокса не доходит — его ловит прозрачный запирающий слой
        (`create_checkbox_blocker`), поэтому клиент даже не рисует переключение.
        Проверка здесь остаётся страховкой: событие может прийти от TalkBack
        (он активирует чекбокс без тапа) или когда выделение появилось между
        событием и обработкой. Тогда значение из модели уходит обратно клиенту.

        Запись — до обновления экрана: при ошибке чекбокс и цвет названия
        остаются прежними, показывается сообщение. Новое значение приходит из
        хранилища, которое принимает его явно (`Storage.set_item_checked`), а не
        инвертирует, так что повторное событие не перевернёт отметку обратно.
        """
        if (
            self._selected_view is not None
            or self._selected_item is not None
            or self._editing_view is not None
        ):
            view.set_checked(view.item.is_checked)
            self.page.update()
            return
        target = not view.item.is_checked
        try:
            checked = await asyncio.to_thread(
                self.storage.set_item_checked, view.item.id, target
            )
        except Exception:
            logger.exception("Не удалось сохранить отметку пункта")
            self._show_message("Не удалось сохранить отметку")
            view.set_checked(view.item.is_checked)
            self.page.update()
            return
        view.set_checked(checked)
        self.page.update()

    async def delete_category(self, event: ft.ControlEvent | None = None) -> None:
        """delete_category: удаляет выделенную категорию из списка и из БД.

        Запись в БД — до обновления экрана: при ошибке категория остаётся на
        месте и показывается сообщение. Вместе с категорией каскадом уходят её
        пункты (см. docs/features/feature-storage.md). Выделение снимается:
        удалённой категории больше нет, кнопки возвращаются к исходному составу.
        Порядок оставшихся берётся из БД, как и после перетаскивания.
        """
        view = self._selected_view
        if view is None:
            # Кнопка показана только при выделенной категории.
            return
        editing = self._editing_view
        if editing is not None and (editing is view or editing in view.items):
            # Ввод названия скрывает button_area целиком, так что сюда не
            # попадают; если состояние всё же такое, поле уходит вместе
            # с панелью, а не остаётся фокусом у несуществующей категории
            # или её пункта.
            editing.input = None
            self._editing_view = None
            self._keyboard_open = False
        try:
            ordered = await asyncio.to_thread(
                self.storage.delete_category, view.category.id
            )
        except Exception:
            logger.exception("Не удалось удалить категорию")
            self._show_message("Не удалось удалить категорию")
            return
        self._remove_view(view)
        self._selected_view = None
        if (
            self._selected_item is not None
            and self._selected_item.category_view is view
        ):
            # Выделение пункта и категории взаимоисключающие, поэтому через UI
            # такое состояние недостижимо; на случай рассинхронизации пункт
            # снимаем вместе с его панелью.
            self._selected_item.set_selected(False)
            self._selected_item = None
        self._apply_category_order(ordered)
        self._apply_selection()
        self.page.update()

    def _append_category(
        self, category: domain.Category, items: Sequence[domain.Item] = ()
    ) -> CategoryView:
        view = CategoryView(
            category,
            items,
            gestures=self.gestures,
            category_gestures=self.category_gestures,
        )
        self.views.append(view)
        self.category_list.controls.append(view.item)
        return view

    def _remove_view(self, view: CategoryView) -> None:
        """Убирает категорию из списка в памяти и из списка элементов."""
        if view in self.views:
            self.views.remove(view)
        self.category_list.controls = [item.item for item in self.views]

    def _end_drag(self) -> None:
        """Снимает любое перетаскивание: категории или пункта.

        Нужен как страховка на случай, когда система прервала жест и событие
        об отпускании не пришло: иначе кнопки остались бы скрытыми, а прокси
        перетаскивания — висеть поверх списка.
        """
        if (
            not self._dragging
            and self._item_drag is None
            and self._category_drag is None
        ):
            return
        self._dragging = False
        self._finish_item_drag()
        self._finish_category_drag()
        self._apply_selection()
        self.page.update()

    def _apply_category_order(self, ordered: list[domain.Category]) -> None:
        """Приводит список категорий в памяти к порядку, сохранённому в БД."""
        by_id = {item.category.id: item for item in self.views}
        self.views = [
            by_id[category.id] for category in ordered if category.id in by_id
        ]
        for category in ordered:
            view = by_id.get(category.id)
            if view is not None:
                view.category = category
        self.category_list.controls = [item.item for item in self.views]

    # Перетаскивание категории: свой жест, прокси, зазор и автопрокрутка.
    #
    # Перетаскивание начинается только у выделенной категории: долгое нажатие
    # сначала выделяет её (палец отпускается), и лишь второе нажатие по ней же
    # поднимает панель. Так случайное долгое нажатие не двигает список.
    #
    # Штатный ReorderableListView автопрокручивает список, когда край экрана
    # касается любая часть перетаскиваемой категории (у него `_dragTargetRect` —
    # весь элемент). У длинной категории этот прямоугольник выходит за край
    # сразу, поэтому список начинал ехать в первый же миг перетаскивания. Здесь
    # зона автопрокрутки считается по полосе названия (`CategoryDrag.title_span`),
    # а порядок сохраняется по отпусканию, как и у пункта.

    async def _on_category_long_press(self, view: CategoryView) -> None:
        """Долгое нажатие на панели: выделение и виброотклик.

        Виброотклик даётся на каждое долгое нажатие: первое выделяет категорию,
        второе по ней же поднимает её для перетаскивания — пользователь должен
        почувствовать оба. Пока идёт ввод названия, выделение не меняется:
        долгое нажатие в поле — это работа с текстом.
        """
        if self._editing_view is not None:
            return
        self._select_category(view)
        if self.haptic is not None:
            await self.haptic.medium_impact()

    def _on_category_drag_start(
        self, view: CategoryView, event: ft.LongPressStartEvent
    ) -> None:
        """Категория «поднимается»: панель сворачивается, над списком — прокси.

        Поднимается только **выделенная** категория: перетаскивание начинается
        вторым долгим нажатием, после того как первое выделило категорию и палец
        был отпущен. Событие приходит до `on_long_press` этого жеста, поэтому
        здесь видно выделение, оставшееся от прошлого жеста, а не текущее.
        Размеры панели приходят от клиента (`size_change`): без них не из чего
        построить ни прокси, ни зазор, поэтому долгое нажатие просто выделяет
        категорию.
        """
        if (
            self._editing_view is not None
            or self._item_drag is not None
            or self._category_drag is not None
        ):
            return
        if view is not self._selected_view:
            return
        global_position = event.global_position
        local_position = event.local_position
        if global_position is None or local_position is None:
            return
        if view not in self.views:
            return
        if view.height is None or view.width is None:
            return
        index = self.views.index(view)
        # Точка нажатия приходит в координатах панели: прокси встаёт по её верху.
        grab_y = local_position.y
        drag = CategoryDrag(
            view=view,
            source=index,
            height=view.height,
            width=view.width,
            title_height=view.title_height or CATEGORY_TITLE_HEIGHT_FALLBACK,
            origin_y=global_position.y
            - grab_y
            - category_base_top(self._category_slot_heights(), index)
            + self._scroll_pixels,
            grab_y=grab_y,
            start_y=global_position.y,
            target=index,
        )
        self._category_drag = drag
        self._pointer_y = global_position.y
        # Пока категория перетаскивается, кнопки скрыты целиком.
        self._dragging = True
        view.collapse()
        drag.proxy = create_category_proxy(view, drag.width)
        # Категория едет в своём столбце: прокси встаёт ровно над списком
        # (у содержимого списка отступ `LIST_PADDING`) и по горизонтали не
        # двигается — как и панель, которую вёл клиент.
        drag.proxy.left = LIST_PADDING
        self.stack.controls.append(drag.proxy)
        self._place_category_gap(drag)
        self._move_category_proxy(drag, global_position.y)
        # Прокрутка уводит поднятую категорию за пределы видимой области, и
        # ленивый список уничтожил бы её виджет вместе с распознавателем жеста.
        self.category_list.cache_extent = self._drag_cache_extent(drag)
        self._apply_selection()
        self.page.update()

    def _on_category_drag_move(
        self, view: CategoryView, event: ft.LongPressMoveUpdateEvent
    ) -> None:
        """Палец движется: прокси идёт за ним, зазор переезжает на новую цель."""
        drag = self._category_drag
        if drag is None or drag.view is not view:
            return
        self._pointer_y = event.global_position.y
        self._move_category_proxy(drag, self._pointer_y)
        self._update_category_target(drag)
        self._update_autoscroll(drag)
        self.page.update()

    async def _on_category_drag_end(
        self, view: CategoryView, event: ft.LongPressEndEvent
    ) -> None:
        """Палец отпущен: категория встаёт на новое место, порядок пишется в БД.

        Запись — до обновления списка: при ошибке порядок в памяти и на экране
        остаётся прежним, показывается сообщение (как у остальных операций).
        Порядок из БД — источник истины: им обновляются позиции.
        """
        drag = self._category_drag
        if drag is None or drag.view is not view:
            self._end_drag()
            return
        if event.global_position is not None:
            # Точка отпускания уточняет цель: последнее движение могло прийти
            # раньше, чем палец остановился.
            self._pointer_y = event.global_position.y
            self._update_category_target(drag)
        target = drag.target
        self._finish_category_drag()
        if target == drag.source:
            self.page.update()
            return
        try:
            ordered = await asyncio.to_thread(
                self.storage.move_category, view.category.id, target
            )
        except Exception:
            logger.exception("Не удалось сохранить порядок категорий")
            self._show_message("Не удалось сохранить порядок категорий")
            self.page.update()
            return
        self._apply_category_order(ordered)
        self.page.update()

    def _on_category_drag_cancel(self, view: CategoryView) -> None:
        """Жест отменён: прокси и зазор убираются, порядок не меняется."""
        drag = self._category_drag
        if drag is None or drag.view is not view:
            return
        self._finish_category_drag()
        self.page.update()

    def _finish_category_drag(self) -> None:
        """Возвращает список в обычный вид после перетаскивания категории.

        Прокси убирается со стека, зазор — из отступов элементов списка, панель
        снова получает свою высоту, а начатая автопрокрутка останавливается.
        """
        drag = self._category_drag
        if drag is None:
            return
        self._category_drag = None
        # Проход по краю списка мог ещё идти: отменяем его, иначе список
        # продолжал бы ехать после отпускания категории.
        drag.epoch += 1
        if drag.autoscroll:
            drag.autoscroll = 0
            self.page.run_task(self._cancel_scroll)
        if drag.proxy is not None:
            for position, control in enumerate(self.stack.controls):
                if control is drag.proxy:
                    self.stack.controls.pop(position)
                    break
        self._clear_category_gap()
        drag.view.restore()
        # Кеш возвращается к обычному: список снова строит только видимое.
        self.category_list.cache_extent = None
        self._dragging = False
        self._apply_selection()

    def _category_slot_heights(self) -> list[float]:
        """Высоты слотов категорий: панель вместе с промежутком до следующей.

        Берётся измеренная панель, а если клиент её ещё не присылал (категория
        за пределами видимой области) — высота по шаблону.
        """
        heights: list[float] = []
        for view, (title_height, row_heights) in zip(
            self.views, self._item_metrics(), strict=True
        ):
            panel_height = (
                view.height
                if view.height is not None
                else category_panel_height(title_height, row_heights)
            )
            heights.append(panel_height + CATEGORY_SPACING)
        return heights

    def _category_spans(self, drag: CategoryDrag) -> list[CategorySpan]:
        """Раскладка списка при текущем месте зазора."""
        return build_category_spans(
            self._category_slot_heights(),
            dragged=drag.source,
            target=drag.target,
        )

    def _update_category_target(self, drag: CategoryDrag) -> bool:
        """Пересчитывает место вставки по текущей точке пальца.

        ``True`` — цель изменилась и зазор переехал.
        """
        if self._pointer_y is None or drag.source >= len(self.views):
            return False
        target = category_span_at(
            self._category_spans(drag),
            self._model_y(drag, self._pointer_y),
        )
        if target == drag.target:
            return False
        drag.target = target
        self._place_category_gap(drag)
        return True

    def _place_category_gap(self, drag: CategoryDrag) -> None:
        """Ставит зазор на место вставки: отступом элемента списка.

        Зазор — `margin` того элемента, перед которым категория встанет (или
        нижний отступ последнего, если место — конец списка). Так список
        остаётся прежним: элементы не переставляются и не пересоздаются, а
        распознаватель жеста поднятой категории живёт до отпускания. Высота
        зазора — целый слот категории, поэтому остальные панели не сдвигаются.
        """
        self._clear_category_gap()
        position = drag.target if drag.target < drag.source else drag.target + 1
        gap = ft.Margin.only(top=drag.slot_height)
        if position < len(self.views):
            self.views[position].item.margin = gap
        elif self.views:
            self.views[-1].item.margin = ft.Margin.only(bottom=drag.slot_height)

    def _clear_category_gap(self) -> None:
        """Снимает зазор со всех элементов списка."""
        for view in self.views:
            view.item.margin = None

    def _move_category_proxy(self, drag: CategoryDrag, pointer_y: float) -> None:
        """Двигает прокси категории за пальцем — только по вертикали."""
        if drag.proxy is None:
            return
        drag.panel_top = pointer_y - drag.grab_y
        drag.proxy.top = drag.panel_top - drag.origin_y

    def _select_category(self, view: CategoryView) -> None:
        """Выделяет категорию: другой цвет панели и состав кнопок.

        Выделение применяется идемпотентно: повторный вызов для уже выделенной
        категории всё равно отправляет изменения клиенту — начинающемуся
        перетаскиванию нужен свежий вид элемента. Выделенным может быть только
        один элемент, поэтому выделение с пункта снимается.
        """
        self._clear_item_selection()
        if view is not self._selected_view:
            if self._selected_view is not None:
                self._selected_view.set_selected(False)
            self._selected_view = view
            view.set_selected(True)
        self._apply_selection()
        self.page.update()

    def _select_item(self, view: ItemView) -> None:
        """Выделяет пункт: розовый фон строки и кнопки пункта.

        Розовый — тот же `ITEM_PANEL_SELECTED_COLOR`, что и у выделенной
        категории. Категория при этом не выделена: выделен всегда ровно один
        элемент, поэтому выделение с категории снимается.
        """
        if self._selected_view is not None:
            self._selected_view.set_selected(False)
            self._selected_view = None
        if view is not self._selected_item:
            self._clear_item_selection()
            self._selected_item = view
        view.set_selected(True)
        self._apply_selection()
        self.page.update()

    def _clear_item_selection(self) -> None:
        """Снимает выделение с пункта, если он выделен."""
        view = self._selected_item
        if view is None:
            return
        self._selected_item = None
        view.set_selected(False)

    async def _on_item_long_press(self, view: ItemView) -> None:
        """Долгое нажатие по пункту: пункт выделяется и даёт виброотклик.

        Долгое нажатие перехватывает пункт, а не список: иначе оно начинало бы
        перетаскивание категории (см. `create_item_row`). Пока идёт ввод
        названия, выделение не меняется — как и при тапе, которым закрывают
        клавиатуру.

        Событие приходит после `on_long_press_start` этого же жеста: первое
        нажатие только выделяет пункт, а подъём начался, если пункт был выделен
        раньше (снимается лишь застрявшее перетаскивание категории).
        """
        self._finish_category_drag()
        if self._editing_view is not None:
            return
        self._select_item(view)
        if self.haptic is not None:
            await self.haptic.medium_impact()

    def _on_item_drag_start(
        self, view: ItemView, event: ft.LongPressStartEvent
    ) -> None:
        """Долгое нажатие принято: пункт «поднимается» и готов к перетаскиванию.

        Поднимается только **выделенный** пункт: перетаскивание начинается
        вторым долгим нажатием, после того как первое выделило пункт и палец был
        отпущен. Событие приходит до `on_long_press` этого жеста, поэтому здесь
        видно выделение, оставшееся от прошлого жеста. Дальше этот жест даёт
        `on_long_press_move_update`, а отпускание — `on_long_press_end`.

        Размеры строк приходят от клиента (`size_change`). Без размера самой
        нажатой строки перетаскивание не начинается: её нечем свернуть и не из
        чего построить прокси, поэтому долгое нажатие просто выделяет пункт.
        """
        if (
            self._editing_view is not None
            or self._item_drag is not None
            or self._category_drag is not None
        ):
            return
        if view is not self._selected_item:
            return
        source = view.category_view
        global_position = event.global_position
        local_position = event.local_position
        if source is None or global_position is None or local_position is None:
            return
        if view.height is None or view.width is None:
            return
        if source not in self.views or view not in source.items:
            return
        metrics = self._item_metrics()
        category_index = self.views.index(source)
        source_index = source.items.index(view)
        # Экранный верх содержимого списка: от него считаются и модель, и
        # положение прокси (Stack лежит ровно над областью списка). Точка
        # нажатия внутри строки плюс её верх в модели дают этот верх.
        drag = ItemDrag(
            view=view,
            source=(category_index, source_index),
            height=view.height,
            origin_y=global_position.y
            - local_position.y
            - base_row_top(metrics, category_index, source_index)
            + self._scroll_pixels,
            grab_y=local_position.y,
            start_y=global_position.y,
            target=(category_index, source_index),
        )
        self._item_drag = drag
        self._pointer_y = global_position.y
        # Строка сворачивается, а на её место встают зазор и прокси. Зазор
        # занимает целый слот строки, поэтому пункты не сдвигаются.
        view.collapse()
        drag.gap = create_item_gap(item_slot_height(drag.height))
        self._place_gap(drag, drag.target)
        drag.proxy = create_item_proxy(view)
        # Пункт едет в своём столбце: прокси встаёт ровно над строкой списка
        # (у содержимого списка отступ `LIST_PADDING`) и по горизонтали не
        # двигается — как панель категории, которую клиент ведёт только вдоль
        # оси списка.
        drag.proxy.left = LIST_PADDING
        self.stack.controls.append(drag.proxy)
        self._move_proxy(drag, global_position.y)
        # Пока пункт перетаскивается, список держит в дереве все категории:
        # прокрутка уводит исходную строку за пределы видимой области, и ленивый
        # список уничтожил бы её виджет вместе с распознавателем жеста (см.
        # _drag_cache_extent).
        self.category_list.cache_extent = self._drag_cache_extent(drag)
        # Кнопки прячутся сразу, не дожидаясь события выделения: порядок двух
        # событий долгого нажатия задаёт клиент, а drag уже начался.
        self._apply_selection()
        self.page.update()

    def _drag_cache_extent(self, drag: ItemDrag | CategoryDrag) -> float:
        """Кеш списка на время перетаскивания пункта или категории.

        Прокрутка уводит перетаскиваемое за край видимой области. Ленивый
        список держит в дереве только то, что попадает в его кеш (по
        умолчанию ~250 px за краем), остальное уничтожает — вместе с
        `GestureDetector` перетаскиваемого. Уничтоженный распознаватель молча
        перестаёт присылать `long_press_move_update` и `long_press_end`: прокси
        замирает там, где его застал проход, отпускание пальца не обрабатывается,
        а список остаётся с включённой автопрокруткой. Поэтому на время
        перетаскивания кеш растягивается на всё содержимое: элементы остаются в
        дереве, и жест живёт до отпускания.

        Высоты дальних элементов — оценка, поэтому запас двойной. Больше
        содержимого кеш не стоит ничего: строить больше, чем есть в списке,
        нельзя.
        """
        return 2 * (self._content_height(drag) + self._list_viewport(drag))

    def _item_metrics(self) -> list[tuple[float, list[float]]]:
        """Высоты строк: измеренные, а для невидимых строк — оценка.

        Клиент присылает `size_change` только для того, что реально разложено:
        строки за пределами видимой области размеров не имеют, пока не попадут
        в неё. Измеренные высоты берутся как есть, остальные оцениваются по
        среднему измеренному (или по шаблону, если измерений нет вовсе). На
        место вставки под пальцем это не влияет: строки рядом с пальцем видны и
        измерены, а оценка нужна только невидимым строкам ниже или выше экрана.
        """
        measured_items = [
            item_view.height
            for category in self.views
            for item_view in category.items
            if item_view.height is not None
        ]
        item_height = (
            sum(measured_items) / len(measured_items)
            if measured_items
            else ITEM_ROW_HEIGHT_FALLBACK
        )
        measured_titles = [
            category.title_height
            for category in self.views
            if category.title_height is not None
        ]
        title_height = (
            sum(measured_titles) / len(measured_titles)
            if measured_titles
            else CATEGORY_TITLE_HEIGHT_FALLBACK
        )
        return [
            (
                category.title_height
                if category.title_height is not None
                else title_height,
                [
                    item_view.height
                    if item_view.height is not None
                    else item_height
                    for item_view in category.items
                ],
            )
            for category in self.views
        ]

    def _place_gap(self, drag: ItemDrag, target: tuple[int, int]) -> None:
        """Ставит зазор на место вставки; прежняя категория его теряет.

        Высота зазора — целый слот пункта, она одна и та же в любой категории:
        свёрнутая строка теперь не занимает места вовсе (её ячейка сворачивается
        вместе со строкой), поэтому остатка на месте пункта не остаётся — ни в
        своей категории, ни в чужой.
        """
        if drag.gap is None:
            return
        category = self.views[target[0]]
        if self._gap_category is not None and self._gap_category is not category:
            self._gap_category.remove_gap()
        category.place_gap(drag.gap, target[1], drag.view)
        self._gap_category = category

    def _drop_gap(self) -> None:
        """Убирает зазор из списка."""
        if self._gap_category is not None:
            self._gap_category.remove_gap()
            self._gap_category = None

    def _model_y(self, drag: ItemDrag, pointer_y: float) -> float:
        """Координата модели под пальцем с учётом прокрутки списка."""
        return pointer_y - drag.origin_y + self._scroll_pixels

    def _move_proxy(self, drag: ItemDrag, pointer_y: float) -> None:
        """Двигает прокси строки за пальцем — только по вертикали.

        По горизонтали пункт не едет: в списке он живёт в одном столбце, и
        переставлять его вбок некуда. Так же ведёт себя категория — клиент
        двигает её только вдоль оси списка, и копия пункта должна выглядеть
        так же. Поэтому здесь меняется только ``top``, а ``left`` выставлен при
        подъёме.
        """
        if drag.proxy is None:
            return
        drag.proxy.top = pointer_y - drag.origin_y - drag.grab_y

    def _update_drag_target(self, drag: ItemDrag) -> bool:
        """Пересчитывает место вставки по текущей точке пальца.

        ``True`` — цель изменилась и зазор переехал: экран нужно обновить.
        Раскладка строится от текущего зазора, поэтому палец сравнивается с
        серединами строк так, как они видны на экране. Высоты берутся заново:
        пока шла прокрутка, строки попадали в видимую область и измерялись.
        """
        if not drag.moved or self._pointer_y is None:
            return False
        spans = build_drag_spans(
            self._item_metrics(),
            source=drag.source,
            height=drag.height,
            target=drag.target,
        )
        category_index, insert_index = drag_slot_at(
            spans, self._model_y(drag, self._pointer_y)
        )
        if category_index >= len(self.views):
            return False
        if (category_index, insert_index) == drag.target:
            return False
        drag.target = (category_index, insert_index)
        self._place_gap(drag, drag.target)
        return True

    def _on_item_drag_move(
        self, view: ItemView, event: ft.LongPressMoveUpdateEvent
    ) -> None:
        """Палец движется: прокси идёт за ним, зазор переезжает на новую цель.

        Раскладка пересчитывается через текущее положение зазора, поэтому
        перестановка начинается, когда палец проходит середину соседней
        строки, — как и при перетаскивании категории. Порог и цель считаются по
        вертикальному сдвигу: движение вбок пункт не переставляет и прокси не
        сдвигает.
        """
        drag = self._item_drag
        if drag is None or drag.view is not view:
            return
        self._pointer_y = event.global_position.y
        if not drag.moved:
            if abs(self._pointer_y - drag.start_y) < ITEM_DRAG_THRESHOLD:
                return
            drag.moved = True
        self._move_proxy(drag, self._pointer_y)
        self._update_drag_target(drag)
        self._update_autoscroll(drag)
        self.page.update()

    async def _on_item_drag_end(
        self, view: ItemView, event: ft.LongPressEndEvent
    ) -> None:
        """Палец отпущен: пункт встаёт на новое место, порядок пишется в БД.

        Запись — до обновления списка: при ошибке порядок в памяти и на экране
        остаётся прежним, показывается сообщение (как у остальных операций).
        Порядок из БД применяется к пунктам прежней и новой категории, поэтому
        перенос в другую категорию ничем не отличается от перестановки внутри
        своей. Выделение переживает перетаскивание, как и у категории.
        """
        drag = self._item_drag
        if drag is None or drag.view is not view:
            self._end_drag()
            return
        if drag.moved and event.global_position is not None:
            # Точка отпускания уточняет цель: последнее движение могло прийти
            # раньше, чем палец остановился.
            self._pointer_y = event.global_position.y
            self._update_drag_target(drag)
        target = drag.target
        self._finish_item_drag()
        source = view.category_view
        if not drag.moved or source is None:
            # Жест без движения: это было выделение, а не перетаскивание.
            self.page.update()
            return
        target_category = self.views[target[0]]
        if target_category is source and target[1] == drag.source[1]:
            self.page.update()
            return
        try:
            orders = await asyncio.to_thread(
                self.storage.move_item,
                view.item.id,
                target_category.category.id,
                target[1],
            )
        except Exception:
            logger.exception("Не удалось переместить пункт")
            self._show_message("Не удалось переместить пункт")
            self.page.update()
            return
        self._apply_item_orders(orders)
        self.page.update()

    def _on_item_drag_cancel(self, view: ItemView) -> None:
        """Жест отменён: прокси и зазор убираются, порядок не меняется."""
        drag = self._item_drag
        if drag is None or drag.view is not view:
            return
        self._finish_item_drag()
        self.page.update()

    def _finish_item_drag(self) -> None:
        """Возвращает список в обычный вид после перетаскивания пункта.

        Прокси убирается со стека, зазор — из контейнера пунктов, свёрнутая
        строка снова получает свою высоту, а начатая автопрокрутка
        останавливается. Порядок пунктов на этом шаге не меняется: его применяет
        вызывающий по данным хранилища.
        """
        drag = self._item_drag
        if drag is None:
            return
        self._item_drag = None
        # Проход по краю списка мог ещё идти: отменяем его, иначе список
        # продолжал бы ехать после отпускания пункта.
        drag.epoch += 1
        if drag.autoscroll:
            drag.autoscroll = 0
            self.page.run_task(self._cancel_scroll)
        if drag.proxy is not None:
            for position, control in enumerate(self.stack.controls):
                if control is drag.proxy:
                    self.stack.controls.pop(position)
                    break
        self._drop_gap()
        drag.view.restore()
        # Кеш возвращается к обычному: список снова строит только видимое.
        self.category_list.cache_extent = None
        self._apply_selection()

    def _active_drag(self) -> ItemDrag | CategoryDrag | None:
        """Текущее перетаскивание: категории или пункта (одно за раз)."""
        return self._item_drag or self._category_drag

    def _finish_active_drag(self) -> None:
        """Завершает текущее перетаскивание без записи порядка."""
        if self._item_drag is not None:
            self._finish_item_drag()
        elif self._category_drag is not None:
            self._finish_category_drag()

    def _refresh_target(self, drag: ItemDrag | CategoryDrag) -> bool:
        """Пересчитывает место вставки после прокрутки списка."""
        if isinstance(drag, CategoryDrag):
            return self._update_category_target(drag)
        return self._update_drag_target(drag)

    def _autoscroll_span(
        self, drag: ItemDrag | CategoryDrag
    ) -> tuple[float, float] | None:
        """Полоса, которую автопрокрутка сравнивает с краями экрана.

        У пункта это сам палец, у категории — область названия поднятой панели:
        категория «касается» края только названием, а не любым своим пунктом.
        Иначе длинная категория, чей низ уходит за экран, начинала бы прокрутку
        в первый же миг перетаскивания.
        """
        if isinstance(drag, CategoryDrag):
            return drag.title_span()
        if self._pointer_y is None:
            return None
        return self._pointer_y, self._pointer_y

    def _autoscroll_direction(self, drag: ItemDrag | CategoryDrag) -> int:
        """Куда прокручивать список: -1 вверх, 1 вниз, 0 — не надо.

        Зона — `AUTOSCROLL_EDGE` у верхней и нижней границы видимой области
        списка: содержимое уезжает под пальцем, поэтому до невидимой категории
        можно добраться, не отпуская пункт. Пока прокрутка идёт, зона шире на
        `AUTOSCROLL_HYSTERESIS`: палец, стоящий на самой границе зоны, не должен
        выключать и снова включать её дрожанием в пиксель.
        """
        span = self._autoscroll_span(drag)
        if span is None:
            return 0
        edge = AUTOSCROLL_EDGE + (AUTOSCROLL_HYSTERESIS if drag.autoscroll else 0)
        top = drag.origin_y
        bottom = top + self._list_viewport(drag)
        if span[0] < top + edge:
            return -1
        if span[1] > bottom - edge:
            return 1
        return 0

    def _list_viewport(self, drag: ItemDrag | CategoryDrag) -> float:
        """Высота видимой области списка в логических пикселях.

        После первой прокрутки её присылает клиент (`on_scroll`), до этого она
        оценивается по размеру окна за вычетом отступов представления и
        системной навигации. Оценка нужна только для зоны автопрокрутки:
        ошибка в несколько пикселей ей не мешает.
        """
        if self._viewport:
            return self._viewport
        height = self.page.height or 0
        media = self.page.media
        bottom_padding = (media.padding.bottom if media else 0) or 0
        view = self.page.views[0] if self.page.views else None
        view_padding = getattr(view, "padding", None)
        view_bottom = getattr(view_padding, "bottom", 0) or 0
        return max(height - bottom_padding - view_bottom - drag.origin_y, 0)

    def _update_autoscroll(self, drag: ItemDrag | CategoryDrag) -> None:
        """Включает, выключает или разворачивает автопрокрутку.

        Саму прокрутку выполняет клиент: ему заказывается один анимированный
        проход до края списка. Поэтому позиция идёт его кадрами, а не рывками из
        Python. Раньше шаг 12 px заказывался раз в 40 мс, и каждый заказ ждал
        ответа клиента: позиция менялась ~25 раз в секунду, а неравномерность
        ответов добавляла рывки — прокрутка получалась дёрганой.
        """
        direction = self._autoscroll_direction(drag)
        if direction == drag.autoscroll:
            return
        was = drag.autoscroll
        drag.autoscroll = direction
        # Прошлый проход отменяется: его задача проверит номер и выйдет, а
        # анимацию в клиенте останавливает `_cancel_scroll`.
        drag.epoch += 1
        if was:
            self.page.run_task(self._cancel_scroll)
        if direction:
            self.page.run_task(self._scroll_to_edge, drag, drag.epoch)

    async def _scroll_to_edge(
        self, drag: ItemDrag | CategoryDrag, epoch: int
    ) -> None:
        """Анимированный проход списка до края, к которому ведёт палец.

        Длительность считается по оставшемуся пути, поэтому скорость одна и та
        же при любой длине списка, а край — точная цель: клиент берёт его сам
        (`offset=-1` — конец, `0` — начало) уже в момент прокрутки. Поэтому
        список никогда не уезжает за край и не пружинит обратно: раньше именно
        эти пружины (каждый шаг заказывался «на 12 px», в том числе когда
        прокручивать было уже некуда) и давали дёрганье у границы списка.
        """
        if self._active_drag() is not drag or drag.epoch != epoch or not drag.autoscroll:
            return
        distance = self._autoscroll_distance(drag)
        if distance <= AUTOSCROLL_REST:
            # Список уже у края: заказывать нечего, и повторять запросы нельзя —
            # каждый уход за край клиент возвращает пружиной.
            return
        # Докуда список мог прокрутиться вниз перед проходом: по этой величине
        # видно, вырос ли он за проход (см. _on_scroll).
        drag.pass_extent = self._max_scroll_extent
        await self.category_list.scroll_to(
            offset=-1.0 if drag.autoscroll > 0 else 0.0,
            duration=round(distance / AUTOSCROLL_SPEED * 1000),
            curve=ft.AnimationCurve.EASE,
        )

    async def _cancel_scroll(self) -> None:
        """Останавливает анимированную прокрутку там, где список стоит сейчас."""
        await self.category_list.scroll_to(delta=0)

    def _autoscroll_distance(self, drag: ItemDrag | CategoryDrag) -> float:
        """Сколько ещё можно прокрутить в сторону пальца, в пикселях.

        Нужна только для длительности прохода: цель у клиента абсолютная (край
        списка), поэтому ошибка в оценке меняет лишь скорость, а уехать за край
        она не даёт. Вверх остаток точный — это сама прокрутка (начало списка —
        нуль). Вниз берётся большее из измеренного (`on_scroll`) и оценённого по
        раскладке: измеренное могло устареть, если список вырос без прокрутки, а
        оценка — ошибиться на несколько пикселей, и остановиться раньше края
        хуже, чем заказать лишний проход в уже достигнутый край.
        """
        if drag.autoscroll > 0:
            measured = (
                self._max_scroll_extent - self._scroll_pixels
                if self._max_scroll_extent is not None
                else 0.0
            )
            estimated = (
                self._content_height(drag)
                - self._list_viewport(drag)
                - self._scroll_pixels
            )
            return max(measured, estimated, 0.0)
        return max(self._scroll_pixels, 0.0)

    def _content_height(self, drag: ItemDrag | CategoryDrag) -> float:
        """Высота содержимого списка по раскладке перетаскивания.

        Панели категорий не измеряются, но раскладка повторяет шаблон панели,
        так что низ последней категории вместе с нижним отступом списка — это
        почти точная высота содержимого.
        """
        if isinstance(drag, CategoryDrag):
            return self._category_spans(drag)[-1].bottom + LIST_BOTTOM_PADDING
        spans = build_drag_spans(
            self._item_metrics(),
            source=drag.source,
            height=drag.height,
            target=drag.target,
        )
        if not spans:
            return 0.0
        return spans[-1].bottom + LIST_BOTTOM_PADDING

    def _on_scroll(self, event: ft.OnScrollEvent) -> None:
        """Список прокрутился: место вставки пересчитывается под пальцем.

        Автопрокрутка двигает содержимое, а палец стоит на месте, поэтому
        координата модели под ним меняется — зазор переезжает вместе с ней.
        Прокси двигать не нужно: он привязан к пальцу.

        Прокрутку ведёт клиент, так что событие — единственный способ узнать,
        где сейчас содержимое и докуда оно может ехать. По концу прохода
        прокрутка продолжается, только если список за проход стал выше: зазор
        переезжает, и конец списка уезжает вниз.

        Прокрутка пользователя (событие `user`) означает, что перетаскивание
        пункта уже кончилось: пока жест жив, список двигает только
        автопрокрутка. Так выходит, если система оборвала жест, не прислав
        отпускания — например, строка ушла из списка вместе с распознавателем.
        Тогда перетаскивание снимается: иначе прокси висел бы поверх списка, а
        автопрокрутка возвращала бы список к краю, за который его уводит палец.
        """
        delta = event.pixels - self._scroll_pixels
        self._scroll_pixels = event.pixels
        self._viewport = event.viewport_dimension
        if math.isfinite(event.max_scroll_extent):
            # У безгранично прокручиваемого списка тут бесконечность: она
            # сломала бы расчёт длительности прохода.
            self._max_scroll_extent = event.max_scroll_extent
        drag = self._active_drag()
        if drag is None:
            return
        if event.event_type == ft.ScrollType.START:
            # Размеры на начало прохода: с ними сравнивается конец прохода.
            drag.pass_extent = event.max_scroll_extent
        elif event.event_type == ft.ScrollType.USER:
            # Список поехал от пальца — жест перетаскивания потерян.
            drag.autoscroll = 0
            self._finish_active_drag()
            self.page.update()
            return
        if delta and self._refresh_target(drag):
            self.page.update()
        if event.event_type == ft.ScrollType.END and drag.autoscroll > 0:
            # Продолжение — только если конец списка уехал вниз: остаток «до
            # края» для этого не годится, он положителен и тогда, когда список
            # отъехал от края сам.
            grown = (
                drag.pass_extent is not None
                and event.max_scroll_extent
                > drag.pass_extent + AUTOSCROLL_EXTENT_EPS
            )
            drag.pass_extent = event.max_scroll_extent
            if grown:
                self.page.run_task(self._scroll_to_edge, drag, drag.epoch)

    def _apply_item_orders(self, orders: dict[int, list[domain.Item]]) -> None:
        """Раскладывает пункты затронутых категорий по порядку из БД.

        После переноса пункта хранилище возвращает порядок прежней и новой
        категорий, и он — источник истины, как и у категорий. Строки пунктов не
        пересоздаются: они переезжают между контейнерами как есть (клиент
        сопоставляет контролы по идентификатору), поэтому отметки, размеры и
        выделение сохраняются.
        """
        by_id = {
            item_view.item.id: item_view
            for category in self.views
            for item_view in category.items
        }
        for category in self.views:
            ordered = orders.get(category.category.id)
            if ordered is None:
                continue
            item_views: list[ItemView] = []
            for item in ordered:
                item_view = by_id.get(item.id)
                if item_view is None:
                    continue
                item_view.item = item
                item_view.category_view = category
                item_views.append(item_view)
            category.items = item_views
            category.items_box.content.controls = [
                item_view.cell for item_view in item_views
            ]
            category._sync_items_box()

    async def _on_item_tap(self, view: ItemView) -> None:
        """Тап по пункту: внутри выделенной категории он выделяет пункт.

        Тап по пункту в невыделенной категории — обычный тап по области списка:
        он снимает выделение. Тап, которым закрывают клавиатуру, выделение не
        снимает, а ввод названия — завершает.
        """
        # Тап возможен только когда перетаскивания уже нет. Если система
        # прервала жест, не прислав on_reorder_end, кнопки остались бы скрытыми.
        self._end_drag()
        if self._editing_view is not None:
            # Ввод закончится сохранением названия; выделение не трогаем.
            self._commit_editing()
            return
        if self._tap_ended_input:
            # Это тот же тап, что уже закрыл клавиатуру (on_tap_outside поля
            # приходит раньше события пункта): выделение остаётся.
            self._tap_ended_input = False
            return
        if (
            view.category_view is not None
            and view.category_view is self._selected_view
        ):
            self._select_item(view)
            if self.haptic is not None:
                await self.haptic.medium_impact()
            return
        self._deselect()

    def _on_tap(self, event: ft.ControlEvent | None = None) -> None:
        """Тап по списку завершает ввод названия или снимает выделение.

        Тап, которым закрывают клавиатуру, выделение не снимает: ввод
        завершается, а выделенная категория остаётся выделенной (см.
        feature-category.md). Тот же тап приходит и вторым событием — тапом
        списка; его отсекает флаг `_tap_ended_input`, выставленный
        обработчиком `on_tap_outside` поля ввода.
        """
        # Тап возможен только когда перетаскивания уже нет. Если система
        # прервала жест, не прислав on_reorder_end, кнопки остались бы скрытыми.
        self._end_drag()
        if self._editing_view is not None:
            # Ввод закончится сохранением названия; выделение не трогаем.
            self._commit_editing()
            return
        if self._tap_ended_input:
            # Это тот же тап, что уже закрыл клавиатуру (on_tap_outside поля
            # приходит раньше on_tap списка): выделение остаётся.
            self._tap_ended_input = False
            return
        self._deselect()

    def _on_tap_cancel(self, event: ft.ControlEvent | None = None) -> None:
        """Жест перестал быть тапом: флаг «этот тап закрыл клавиатуру» снят.

        Иначе, если тап вне поля превратится в прокрутку, флаг остался бы
        выставленным и съел следующий, уже обычный тап по списку.
        """
        self._tap_ended_input = False

    def _deselect(self) -> None:
        """Снимает выделение с категории или пункта: выделен всегда один."""
        view = self._selected_view
        item_view = self._selected_item
        if view is None and item_view is None:
            return
        self._selected_view = None
        self._selected_item = None
        if view is not None:
            view.set_selected(False)
        if item_view is not None:
            item_view.set_selected(False)
        self._apply_selection()
        self.page.update()

    def _actions(self) -> tuple[ButtonAction, ButtonAction, ButtonAction]:
        """Действия трёх слотов button_area для текущего выделения.

        Слоты постоянные (плюс, карандаш, корзина), иконки у категорий и
        пунктов совпадают, поэтому при смене выделения меняется действие
        каждого слота, а не набор кнопок (см. docs/Project.md).

        Без выделения виден только плюс — создание категории. При выделенной
        категории плюс добавляет пункт, а карандаш и корзина работают с этой
        категорией. При выделенном пункте плюс снова создаёт категорию —
        категория в этот момент не выделена (см.
        docs/features/feature-button-area.md), — а карандаш и корзина работают
        с пунктом.
        """
        if self._selected_item is not None:
            return (
                ButtonAction(LABEL_CREATE_CATEGORY, self.create_category),
                ButtonAction(LABEL_RENAME_ITEM, self.rename_item),
                ButtonAction(LABEL_DELETE_ITEM, self.delete_item),
            )
        if self._selected_view is not None:
            return (
                ButtonAction(LABEL_ADD_ITEM, self.add_item),
                ButtonAction(LABEL_RENAME_CATEGORY, self.rename_category),
                ButtonAction(LABEL_DELETE_CATEGORY, self.delete_category),
            )
        return (
            ButtonAction(LABEL_CREATE_CATEGORY, self.create_category),
            ButtonAction(LABEL_RENAME_CATEGORY, self.rename_category, visible=False),
            ButtonAction(LABEL_DELETE_CATEGORY, self.delete_category, visible=False),
        )

    def _set_checkboxes_blocked(self, blocked: bool) -> None:
        """Запирает или отпускает чекбоксы всех пунктов.

        Отметку можно менять только когда ничего не выделено и не идёт ввод
        названия ([feature-item.md](features/feature-item.md)), поэтому в
        остальное время чекбоксы не должны реагировать на тап. Слой над
        чекбоксом прозрачный: внешний вид не меняется, в отличие от `disabled`.
        """
        for category in self.views:
            for item_view in category.items:
                item_view.set_checkbox_blocked(blocked)

    def _apply_selection(self) -> None:
        """Показывает действия, подходящие текущему выделению и вводу."""
        selected = self._selected_view is not None or self._selected_item is not None
        editing = self._editing_view is not None
        for button, action in zip(
            (self.plus_button, self.pencil_button, self.trash_button),
            self._actions(),
            strict=True,
        ):
            bind_button(button, action)
        # Пока что-то выделено или идёт ввод, чекбоксы не реагируют на тап: иначе
        # клиент на мгновение нарисовал бы переключение, а сервер его откатил.
        self._set_checkboxes_blocked(selected or editing)
        # Пока идёт ввод названия или перетаскивание (категории или пункта),
        # контейнер скрыт целиком (см. feature-button-area.md): кнопки не
        # должны заслонять список в момент, когда по нему ведут пальцем.
        self.button_area.visible = (
            not editing and not self._dragging and self._item_drag is None
        )
        # Пока категория или пункт выделены или идёт ввод названия, «назад»
        # перехватывается вместо закрытия приложения: он снимает выделение
        # либо завершает ввод (см. _on_confirm_pop).
        self.page.views[0].can_pop = not selected and not editing

    async def _on_confirm_pop(self, event: ft.ControlEvent) -> None:
        """Кнопка или жест «назад»: завершает ввод или снимает выделение.

        Приложение при этом не закрывается. «Назад» во время ввода названия
        сохраняет введённое название и оставляет выделение: по спеке ввод
        заканчивается и кнопкой «назад» (см. feature-category.md). Пока
        открыта клавиатура, первый «назад» обычно забирает Android; сюда он
        приходит, когда клавиатуры уже нет или её закрытие не отследилось.
        """
        view = self.page.views[-1]
        if self._editing_view is not None:
            await self._finish_title_input(self._editing_view)
            await view.confirm_pop(False)
            return
        selected = (
            self._selected_view is not None or self._selected_item is not None
        )
        if selected:
            self._deselect()
        await view.confirm_pop(not selected)

    async def _start_title_input(
        self,
        view: TitledView,
        initial: str | None = None,
        scroll_to_end: bool = False,
    ) -> None:
        """Показывает поле ввода на месте названия и открывает клавиатуру.

        ``initial`` — прежнее название: при переименовании поле заполнено им.
        ``scroll_to_end`` — для новой категории: она добавлена в конец, и её
        надо доскроллить, чтобы поле было видно. Новый пункт может быть и не
        последним на экране, поэтому для него прокрутку делает сам Flutter:
        поле в фокусе он показывает на экране. Переименовываемый элемент
        (категория или пункт) уже выделен на экране — прокрутка ему не нужна.
        """
        field = self._begin_title_input(view, initial)
        if scroll_to_end:
            await self.category_list.scroll_to(offset=-1)
        await field.focus()

    def _begin_title_input(
        self, view: TitledView, initial: str | None = None
    ) -> ft.TextField:
        """Переводит название в режим ввода и скрывает кнопки button_area."""
        field = view.create_input(
            value=initial or "",
            on_commit=self._title_commit_handler(view),
            on_tap_outside=self._title_tap_outside_handler(view),
        )
        view.show_input(field)
        self._editing_view = view
        self._tap_ended_input = False
        # Пока идёт ввод, кнопки скрыты: клавиатура иначе поднимала бы их
        # вместе с содержимым, и они перекрывали бы список.
        self._apply_selection()
        # Клавиатура может быть уже открыта (ввод уже начат).
        self._keyboard_open = self._keyboard_visible(self.page.media)
        # Патч с новым полем должен уйти раньше вызова focus(): иначе клиент
        # ещё не знает контрол, к которому относится вызов.
        self.page.update()
        return field

    def _title_commit_handler(self, view: TitledView):
        async def commit(event: ft.ControlEvent) -> None:
            await self._finish_title_input(view)

        return commit

    def _title_tap_outside_handler(self, view: TitledView):
        """Тап вне поля: завершает ввод и помечает, что тап уже обработан.

        `on_tap_outside` приходит на нажатие, а `on_tap` списка — на отпускание,
        поэтому без флага тот же самый тап снял бы выделение, чего спека не
        разрешает. Флаг выставляется, только если ввод ещё идёт: если тап
        списка пришёл первым и уже завершил ввод, помечать нечего.
        """

        async def tap_outside(event: ft.ControlEvent) -> None:
            if view.input is None:
                return
            self._tap_ended_input = True
            await self._finish_title_input(view)

        return tap_outside

    async def _finish_title_input(self, view: TitledView) -> None:
        """Сохраняет введённое название и возвращает на место поля текст.

        Название категории и название пункта вводятся одинаково; различаются
        только дефолт (``view.default_title``) и операция хранилища
        (``view.save_title``).
        """
        field = view.input
        if field is None:
            # on_blur приходит после on_submit/on_tap_outside — второй раз не пишем.
            return
        view.input = None
        if self._editing_view is view:
            self._editing_view = None
        new_title = domain.normalize_title(field.value, view.default_title)
        if new_title != view.title:
            try:
                # Коммит в БД — до обновления UI: при ошибке экран не меняется.
                new_title = await asyncio.to_thread(
                    view.save_title, self.storage, new_title
                )
            except Exception:
                logger.exception("Не удалось сохранить название")
                self._show_message("Не удалось сохранить название")
            else:
                view.title = new_title
        view.show_title()
        if self._editing_view is None:
            # Ввод завершён — кнопки возвращаются в правый нижний угол.
            self._apply_selection()
        # Финиш может прийти из задачи (закрытие клавиатуры), а не из события:
        # автообновление в этом случае не сработает, поэтому обновляем явно.
        self.page.update()

    def _show_message(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))


async def main(page: ft.Page):
    page.title = "Чеклист"
    # Светлая тема зафиксирована: иконки кнопок чёрные (см. docs/Design.md).
    page.theme_mode = ft.ThemeMode.LIGHT

    try:
        storage = await asyncio.to_thread(open_storage)
    except (StorageError, OSError) as error:
        logger.exception("Не удалось открыть БД")
        page.add(ft.Text(f"Не удалось открыть данные приложения: {error}"))
        return

    app = ChecklistApp(page, storage)
    await app.mount()


if __name__ == "__main__":
    ft.run(main)
