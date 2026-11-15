"""Параметры внешнего вида: размеры, цвета, стили, тексты и пороги.

Числа и цвета сверены с docs/Design.md, поведение, которое из них
следует, — в docs/Project.md. Модуль не зависит от остальных модулей
`ui`, поэтому импортируется где угодно: сначала параметры, потом код."""

from __future__ import annotations

import flet as ft


# Параметры button_area — см. docs/Design.md
BUTTON_SIZE = 56
BUTTON_ICON_SIZE = 24
BUTTON_SPACING = 12
BUTTON_AREA_MARGIN = 16
BUTTON_AREA_HEIGHT = BUTTON_SIZE * 3 + BUTTON_SPACING * 2

# Параметры списка категорий и шаблона категории — см. docs/Design.md
LIST_PADDING = 16
CATEGORY_SPACING = 8
# Промежуток до следующей категории — внутренний отступ элемента списка
# (`create_category_item`), а не `spacing` списка: `spacing` давал бы промежуток
# и после последней категории.
CATEGORY_ITEM_PADDING = ft.Padding.only(bottom=CATEGORY_SPACING)
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
# Частота событий прокрутки (`ListView.scroll_interval`, мс). Каждое событие
# уходит из клиента в Python, поэтому во время обычной прокрутки оно не нужно
# вовсе: позиция списка там не используется. Частая позиция нужна только при
# перетаскивании — по ней пересчитывается место вставки и продолжается проход
# автопрокрутки.
SCROLL_INTERVAL_IDLE = 250
SCROLL_INTERVAL_DRAG = 10
# Кеш списка категорий (логические px): столько содержимого клиент держит
# построенным. Список собирается целиком, но строит строки только по мере того,
# как они попадают в кеш (по умолчанию ~250 px за краем экрана). Каждая сборка —
# это виджеты, элементы и раскладка целой панели с пунктами; в кадре прокрутки она
# стоит несколько миллисекунд, поэтому длинный список дёргался на каждой новой
# строке. С растянутым кешем список строится один раз, а прокрутка только сдвигает
# готовое содержимое. Списку длиннее кеша строки снова строятся по краю экрана.
SCROLL_CACHE_EXTENT = 20000
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
