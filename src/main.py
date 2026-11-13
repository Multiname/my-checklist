"""Точка входа приложения «Чеклист»."""

from __future__ import annotations

import asyncio
import logging

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
CATEGORY_PANEL_RADIUS = 12
CATEGORY_PANEL_PADDING = ft.Padding.symmetric(horizontal=16, vertical=12)
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
# Нижний отступ списка: последняя категория не прячется под button_area.
LIST_BOTTOM_PADDING = BUTTON_AREA_HEIGHT + BUTTON_AREA_MARGIN + LIST_PADDING

# Иконки лежат в src/assets/icons (assets_dir по умолчанию — "assets"
# относительно main.py), поэтому пути указываются от каталога assets.
ICON_PLUS = "icons/plus-sign.webp"
ICON_PENCIL = "icons/pencil.webp"
ICON_TRASH = "icons/trash-bin.webp"


def _no_op(event: ft.ControlEvent):
    """Заглушка обработчика: тап по кнопке даёт ripple, но ничего не делает."""


def icon_button(icon_src: str, label: str, on_click) -> ft.Container:
    """Круглая кнопка с иконкой для button_area.

    Подсказка задана только через semantics_label: виджет tooltip перехватывает
    долгое нажатие и задерживает эффект тапа (проверено на устройстве).
    """
    return ft.Container(
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
        on_click=on_click,
        content=ft.Image(
            src=icon_src,
            width=BUTTON_ICON_SIZE,
            height=BUTTON_ICON_SIZE,
            fit=ft.BoxFit.CONTAIN,
            semantics_label=label,
        ),
    )


def create_button_area(on_create_category=_no_op) -> ft.Container:
    """button_area: контейнер с кнопками управления категориями справа снизу."""
    return ft.Container(
        right=BUTTON_AREA_MARGIN,
        bottom=BUTTON_AREA_MARGIN,
        content=ft.Column(
            spacing=BUTTON_SPACING,
            tight=True,
            controls=[
                icon_button(ICON_PLUS, "Создать категорию", on_create_category),
                icon_button(ICON_PENCIL, "Переименовать категорию", _no_op),
                icon_button(ICON_TRASH, "Удалить категорию", _no_op),
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


def create_category_panel(title: str) -> ft.Container:
    """Шаблон категории: название поверх прямоугольной панели."""
    return ft.Container(
        bgcolor=CATEGORY_PANEL_COLOR,
        border_radius=CATEGORY_PANEL_RADIUS,
        padding=CATEGORY_PANEL_PADDING,
        content=create_category_title(title),
    )


def create_category_list() -> ft.ListView:
    """Список категорий на весь экран: прокручивается, не уходит под кнопки."""
    return ft.ListView(
        expand=True,
        spacing=CATEGORY_SPACING,
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


def create_category_input(hint_text: str, on_commit) -> ft.TextField:
    """Поле ввода названия на месте названия категории.

    Клавиатура появляется за счёт autofocus; ввод завершается кнопкой действия
    клавиатуры, тапом вне поля, потерей фокуса и скрытием клавиатуры
    (жест «назад» обрабатывается через page.on_media_change).
    """
    return ft.TextField(
        hint_text=hint_text,
        hint_style=CATEGORY_HINT_STYLE,
        text_style=CATEGORY_TITLE_STYLE,
        # Поле выглядит как название категории, а не как форма. dense убирает
        # минимальную высоту Material-поля, чтобы панель не становилась выше.
        border=ft.NoInputBorder(),
        content_padding=0,
        dense=True,
        min_lines=1,
        max_lines=2,
        autofocus=True,
        on_submit=on_commit,
        on_blur=on_commit,
        on_tap_outside=on_commit,
    )


class CategoryView:
    """Категория на экране: панель с названием и состояние ввода названия."""

    def __init__(self, category: domain.Category) -> None:
        self.category = category
        self.title = category.title
        self.panel = create_category_panel(self.title)
        self.title_text: ft.Text = self.panel.content
        self.input: ft.TextField | None = None

    @property
    def is_editing(self) -> bool:
        return self.input is not None


class ChecklistApp:
    """Экран списка категорий и обработчики button_area."""

    def __init__(self, page: ft.Page, storage: Storage) -> None:
        self.page = page
        self.storage = storage
        self.views: dict[int, CategoryView] = {}
        self.category_list = create_category_list()
        self.button_area = create_button_area(self.create_category)
        self._editing_view: CategoryView | None = None
        self._keyboard_open = False

    async def mount(self) -> None:
        """Загружает категории из БД и собирает экран."""
        for category in await asyncio.to_thread(self.storage.list_categories):
            self._append_category(category)
        self.page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Stack(
                    expand=True,
                    fit=ft.StackFit.EXPAND,
                    controls=[self.category_list, self.button_area],
                ),
            )
        )
        # Жест «назад» на Android закрывает клавиатуру, не снимая фокус
        # с поля и не присылая on_blur: ввод завершаем по скрытию клавиатуры.
        self.page.on_media_change = self._on_media_change
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
        await self._start_title_input(view)

    def _append_category(self, category: domain.Category) -> CategoryView:
        view = CategoryView(category)
        self.views[category.id] = view
        self.category_list.controls.append(view.panel)
        return view

    async def _start_title_input(self, view: CategoryView) -> None:
        """Показывает поле ввода на месте названия и открывает клавиатуру."""
        field = self._begin_title_input(view)
        # Категория добавлена в конец — доскролливаем, чтобы поле было видно.
        await self.category_list.scroll_to(offset=-1)
        await field.focus()

    def _begin_title_input(self, view: CategoryView) -> ft.TextField:
        """Переводит категорию в режим ввода и скрывает кнопки button_area."""
        field = create_category_input(
            hint_text=domain.DEFAULT_CATEGORY_TITLE,
            on_commit=self._title_commit_handler(view),
        )
        view.input = field
        view.panel.content = field
        self._editing_view = view
        # Пока идёт ввод, кнопки скрыты: клавиатура иначе поднимала бы их
        # вместе с содержимым, и они перекрывали бы список.
        self.button_area.visible = False
        # Клавиатура может быть уже открыта (ввод уже начат).
        self._keyboard_open = self._keyboard_visible(self.page.media)
        # Патч с новым полем должен уйти раньше вызова focus(): иначе клиент
        # ещё не знает контрол, к которому относится вызов.
        self.page.update()
        return field

    def _title_commit_handler(self, view: CategoryView):
        async def commit(event: ft.ControlEvent) -> None:
            await self._finish_title_input(view)

        return commit

    async def _finish_title_input(self, view: CategoryView) -> None:
        """Сохраняет введённое название и возвращает на панель текст."""
        field = view.input
        if field is None:
            # on_blur приходит после on_submit/on_tap_outside — второй раз не пишем.
            return
        view.input = None
        if self._editing_view is view:
            self._editing_view = None
        new_title = domain.normalize_title(
            field.value, domain.DEFAULT_CATEGORY_TITLE
        )
        if new_title != view.title:
            try:
                # Коммит в БД — до обновления UI: при ошибке экран не меняется.
                new_title = await asyncio.to_thread(
                    self.storage.set_category_title, view.category.id, new_title
                )
            except Exception:
                logger.exception("Не удалось сохранить название категории")
                self._show_message("Не удалось сохранить название")
            else:
                view.title = new_title
        view.title_text.value = view.title
        view.panel.content = view.title_text
        if self._editing_view is None:
            # Ввод завершён — кнопки возвращаются в правый нижний угол.
            self.button_area.visible = True
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
