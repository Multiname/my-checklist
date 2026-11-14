"""Точка входа приложения «Чеклист»."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import flet as ft

import domain
from storage import Storage, StorageError, open_storage

logger = logging.getLogger(__name__)

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
# Нижний отступ списка: последняя категория не прячется под button_area.
LIST_BOTTOM_PADDING = BUTTON_AREA_HEIGHT + BUTTON_AREA_MARGIN + LIST_PADDING
# Вложенная тема списка: прокси перетаскивания ReorderableListView — это
# Material, который рисует светлый прямоугольник на весь элемент (вместе с
# промежутком до следующей категории) и тень вокруг него. Прозрачные фон, тень
# и тонировка делают прокси невидимым: при перетаскивании видно только панель
# категории, и её высота не меняется. На вид самих категорий тема не влияет —
# панель красится явно заданным bgcolor, а роли цветовой схемы наследуются.
LIST_THEME = ft.Theme(
    canvas_color=ft.Colors.TRANSPARENT,
    color_scheme=ft.ColorScheme(
        shadow=ft.Colors.TRANSPARENT,
        surface_tint=ft.Colors.TRANSPARENT,
    ),
)

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


def create_item_title(title: str) -> ft.Text:
    """Название пункта: мельче названия категории, как и текст пунктов."""
    return ft.Text(
        value=title,
        style=ITEM_TITLE_STYLE,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )


def create_items_box() -> ft.Container:
    """Контейнер пунктов внутри панели категории.

    Пока пунктов нет, контейнер скрыт и не занимает места: панель категории
    выглядит и измеряется как до появления пунктов. Отступ от названия задан
    внутренним padding контейнера, а не `spacing` колонки панели: скрытый
    контейнер не добавляет высоты, а `spacing` колонки добавил бы её и для
    пустого контейнера.
    """
    return ft.Container(
        visible=False,
        padding=ft.Padding.only(top=CATEGORY_ITEMS_TOP),
        content=ft.Column(spacing=ITEM_SPACING, tight=True),
    )


def create_item_panel(checkbox: ft.Checkbox, title: ft.Control) -> ft.Container:
    """Шаблон пункта: чекбокс слева, название справа, фон прозрачный.

    Горизонтальный отступ задан самому пункту, а не панели категории: так
    выделенный пункт закрашивает строку во всю ширину панели, как на макете, а
    текст и чекбокс остаются на прежнем месте.
    """
    return ft.Container(
        bgcolor=ITEM_PANEL_COLOR,
        padding=ITEM_PANEL_PADDING,
        content=ft.Row(
            controls=[checkbox, title],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def create_item_row(panel: ft.Control, on_long_press, on_tap) -> ft.GestureDetector:
    """Область пункта: ловит тап и долгое нажатие по пункту.

    Жесты принадлежат пункту, а не списку: `ReorderableListView` оборачивает
    каждый элемент в `ReorderableDelayedDragStartListener`, и без своего
    обработчика долгое нажатие по пункту начинало бы перетаскивание категории.
    Распознаватель пункта лежит глубже в дереве, поэтому попадает в арену жестов
    раньше (и его таймер долгого нажатия срабатывает первым): долгое нажатие по
    пункту выделяет пункт, по остальной панели категории — категорию.
    Проверено на устройстве.
    """
    return ft.GestureDetector(
        content=panel,
        on_long_press=on_long_press,
        on_tap=on_tap,
    )


def item_event_handler(
    handler: Callable[[ItemView], Awaitable[None]] | None, view: ItemView
):
    """Обработчик жеста пункта: передаёт приложению сам пункт, а не событие.

    Flet ждёт от асинхронного обработчика корутину, а `lambda`, возвращающая
    корутину, — обычная функция: её результат никто не ждёт. Поэтому обёртка —
    `async def`.
    """

    async def handle(event: ft.ControlEvent | None) -> None:
        if handler is not None:
            await handler(view)

    return handle


def create_category_content(title: ft.Control, items: ft.Control) -> ft.Column:
    """Содержимое панели категории: название, под ним — контейнер пунктов."""
    return ft.Column(controls=[title, items], spacing=0, tight=True)


def create_category_panel(content: ft.Control) -> ft.Container:
    """Шаблон категории: прямоугольная панель вокруг названия и пунктов.

    У панели только вертикальные отступы: горизонтальные несут название и
    пункты, поэтому фон выделенного пункта доходит до краёв панели.
    """
    return ft.Container(
        bgcolor=CATEGORY_PANEL_COLOR,
        border_radius=CATEGORY_PANEL_RADIUS,
        padding=CATEGORY_PANEL_PADDING,
        content=content,
    )


def create_category_item(panel: ft.Container) -> ft.Container:
    """Элемент списка: панель категории вместе с промежутком до следующей.

    Промежуток — внутренний отступ обёртки, а не `margin` панели, и не `spacing`
    списка: `ReorderableListView` `spacing` не поддерживает. Прокси
    перетаскивания рисует прямоугольник элемента целиком, но фон и тень прокси
    прозрачные (см. `LIST_THEME`), поэтому промежуток в нём не виден, а высота
    панели при перетаскивании не меняется.
    """
    return ft.Container(
        content=panel,
        padding=ft.Padding.only(bottom=CATEGORY_SPACING),
    )


def create_category_list() -> ft.ReorderableListView:
    """Список категорий на весь экран: прокручивается, категории переставляются.

    Перетаскивание выполняет сам `ReorderableListView`: на Android он
    оборачивает каждый элемент в `ReorderableDelayedDragStartListener`, поэтому
    drag начинается сразу после долгого нажатия — отпускать палец не нужно.
    Выделение по началу drag и сохранение нового порядка делает
    `ChecklistApp` (`on_reorder_start` и `on_reorder`).
    """
    return ft.ReorderableListView(
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
    category_list: ft.ReorderableListView, on_tap, on_tap_cancel=None
) -> ft.Container:
    """Область списка: тап по ней снимает выделение категории.

    Тап ловит обёртка списка, а не экран целиком: `button_area` лежит выше
    в `Stack`, поэтому тапы по кнопкам сюда не доходят. Прокрутка выделение
    не снимает — жест переходит к списку (drag побеждает в арене жестов);
    `on_tap_cancel` сообщает, что жест перестал быть тапом.

    Вложенная тема (`LIST_THEME`) нужна прокси перетаскивания: он лежит выше
    списка в overlay, но наследует темы, захваченные у элемента, поэтому
    прозрачные фон/тень/тонировка действуют и на него.
    """
    return ft.Container(
        theme=LIST_THEME,
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
        on_item_long_press: Callable[[ItemView], Awaitable[None]] | None = None,
        on_item_tap: Callable[[ItemView], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(category.title)
        self.category = category
        # Обработчики жестов пунктов передаёт приложение: без них пункт не смог
        # бы выделяться и не знал бы о выделении своей категории.
        self._item_long_press = on_item_long_press
        self._item_tap = on_item_tap
        # Горизонтальный отступ названия переехал с панели на слот названия:
        # так фон выделенного пункта закрашивает всю ширину панели.
        self.title_slot.padding = CATEGORY_TITLE_PADDING
        self.items: list[ItemView] = []
        self.items_box = create_items_box()
        self.panel = create_category_panel(
            create_category_content(self.title_slot, self.items_box)
        )
        self.item = create_category_item(self.panel)
        self.selected = False
        for item in items:
            self.append_item(item)

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

    def append_item(self, item: domain.Item) -> "ItemView":
        """Добавляет пункт в конец контейнера пунктов категории."""
        view = ItemView(item, self._item_long_press, self._item_tap)
        view.category_view = self
        self.items.append(view)
        self.items_box.content.controls.append(view.row)
        self.items_box.visible = True
        return view

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
    Отметка показывается чекбоксом из БД; переключение отметки — задача 8
    этапа 3.
    """

    default_title = domain.DEFAULT_ITEM_TITLE

    def __init__(
        self,
        item: domain.Item,
        on_long_press: Callable[[ItemView], Awaitable[None]] | None = None,
        on_tap: Callable[[ItemView], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(item.title)
        self.item = item
        # Категория, в панели которой лежит пункт: по ней решается, что делает
        # тап — внутри выделенной категории он выделяет пункт.
        self.category_view: CategoryView | None = None
        self.selected = False
        # Название занимает всё место справа от чекбокса и переносится
        # на вторую строку внутри этой ширины.
        self.title_slot.expand = True
        self.checkbox = ft.Checkbox(value=item.is_checked)
        self.panel = create_item_panel(self.checkbox, self.title_slot)
        self.row = create_item_row(
            self.panel,
            item_event_handler(on_long_press, self),
            item_event_handler(on_tap, self),
        )

    def create_title_text(self, title: str) -> ft.Text:
        return create_item_title(title)

    def create_input(
        self, *, on_commit, value: str = "", on_tap_outside=None
    ) -> ft.TextField:
        return create_item_input(self.default_title, on_commit, value, on_tap_outside)

    def save_title(self, storage: Storage, title: str) -> str:
        return storage.set_item_title(self.item.id, title)

    def set_selected(self, selected: bool) -> None:
        """Выделенный пункт красится тем же цветом, что и выделенная категория."""
        self.selected = selected
        self.panel.bgcolor = (
            ITEM_PANEL_SELECTED_COLOR if selected else ITEM_PANEL_COLOR
        )


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
        self.category_list.on_reorder_start = self._on_reorder_start
        self.category_list.on_reorder = self._on_reorder
        self.category_list.on_reorder_end = self._on_reorder_end
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
        self.button_area = create_button_area(self._actions())
        (
            self.plus_button,
            self.pencil_button,
            self.trash_button,
        ) = self.button_area.content.controls
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
                content=ft.Stack(
                    expand=True,
                    fit=ft.StackFit.EXPAND,
                    controls=[self.category_area, self.button_area],
                ),
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
            on_item_long_press=self._on_item_long_press,
            on_item_tap=self._on_item_tap,
        )
        self.views.append(view)
        self.category_list.controls.append(view.item)
        return view

    def _remove_view(self, view: CategoryView) -> None:
        """Убирает категорию из списка в памяти и из списка элементов."""
        if view in self.views:
            self.views.remove(view)
        self.category_list.controls = [item.item for item in self.views]

    def _view_at(self, index: int | None) -> CategoryView | None:
        """Категория по индексу из события списка; None — если такого нет."""
        if index is None or not 0 <= index < len(self.views):
            return None
        return self.views[index]

    async def _on_reorder_start(self, event: ft.OnReorderEvent) -> None:
        """Долгое нажатие по категории: выделение и сразу перетаскивание.

        `on_reorder_start` приходит в момент, когда `ReorderableListView` уже
        начал drag (на Android — после долгого нажатия): палец отпускать и
        нажимать ещё раз не нужно. Виброотклик даётся на каждый drag, в том
        числе повторный по уже выделенной категории: это новое перетаскивание.
        """
        view = self._view_at(event.old_index)
        if view is None:
            return
        # Пока категория перетаскивается, кнопки скрыты целиком:
        # _apply_selection() внутри _select_category() отправляет это клиенту.
        self._dragging = True
        self._select_category(view)
        if self.haptic is not None:
            await self.haptic.medium_impact()

    def _on_reorder_end(self, event: ft.OnReorderEvent) -> None:
        """Перетаскивание закончено: кнопки button_area возвращаются.

        Событие приходит и при перетаскивании без смены позиции — тогда
        `on_reorder` не приходит, и без него кнопки остались бы скрытыми.
        """
        self._end_drag()

    def _end_drag(self) -> None:
        """Снимает состояние перетаскивания и возвращает кнопки button_area."""
        if not self._dragging:
            return
        self._dragging = False
        self._apply_selection()
        self.page.update()

    async def _on_reorder(self, event: ft.OnReorderEvent) -> None:
        """Категорию отпустили на новом месте: новый порядок сохраняется в БД."""
        old_index, new_index = event.old_index, event.new_index
        view = self._view_at(old_index)
        if view is None or new_index is None or old_index == new_index:
            return
        # Экран уже показывает новый порядок: элемент переставил сам список.
        # Список в памяти повторяет его, иначе любое следующее обновление
        # вернуло бы прежний порядок.
        self._move_view(old_index, new_index)
        try:
            ordered = await asyncio.to_thread(
                self.storage.move_category, view.category.id, new_index
            )
        except Exception:
            logger.exception("Не удалось сохранить порядок категорий")
            self._show_message("Не удалось сохранить порядок категорий")
            return
        # Порядок из БД — источник истины: им же обновляются позиции категорий.
        self._apply_category_order(ordered)
        self.page.update()

    def _move_view(self, old_index: int, new_index: int) -> None:
        """Переставляет категорию в списке в памяти и в списке элементов."""
        new_index = max(0, min(new_index, len(self.views) - 1))
        view = self.views.pop(old_index)
        self.views.insert(new_index, view)
        self.category_list.controls = [item.item for item in self.views]

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
        """
        self._end_drag()
        if self._editing_view is not None:
            return
        self._select_item(view)
        if self.haptic is not None:
            await self.haptic.medium_impact()

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
        с пунктом. `rename_item` и `delete_item` пока заглушки: их обработчики
        появятся на задачах 5 и 6 этапа 3.
        """
        if self._selected_item is not None:
            return (
                ButtonAction(LABEL_CREATE_CATEGORY, self.create_category),
                ButtonAction(LABEL_RENAME_ITEM),
                ButtonAction(LABEL_DELETE_ITEM),
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
        # Пока идёт ввод названия или перетаскивание категории, контейнер
        # скрыт целиком (см. feature-button-area.md).
        self.button_area.visible = not editing and not self._dragging
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
        поле в фокусе он показывает на экране.
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
