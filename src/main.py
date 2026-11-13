"""Точка входа приложения «Чеклист»."""

import flet as ft

# Параметры button_area — см. docs/Design.md
BUTTON_SIZE = 56
BUTTON_ICON_SIZE = 24
BUTTON_SPACING = 12
BUTTON_AREA_MARGIN = 16

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


def create_button_area() -> ft.Container:
    """button_area: контейнер с кнопками управления категориями справа снизу."""
    return ft.Container(
        right=BUTTON_AREA_MARGIN,
        bottom=BUTTON_AREA_MARGIN,
        content=ft.Column(
            spacing=BUTTON_SPACING,
            tight=True,
            controls=[
                icon_button(ICON_PLUS, "Создать категорию", _no_op),
                icon_button(ICON_PENCIL, "Переименовать категорию", _no_op),
                icon_button(ICON_TRASH, "Удалить категорию", _no_op),
            ],
        ),
    )


def main(page: ft.Page):
    page.title = "Чеклист"
    # Светлая тема зафиксирована: иконки кнопок чёрные (см. docs/Design.md).
    page.theme_mode = ft.ThemeMode.LIGHT

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Stack(
                expand=True,
                controls=[
                    ft.Container(
                        content=ft.Text("Чеклист"),
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    ),
                    create_button_area(),
                ],
            ),
        )
    )


if __name__ == "__main__":
    ft.run(main)
