"""Действия слотов button_area.

Кнопки постоянные (плюс, карандаш, корзина), а действие зависит от
выделения: слот хранит подпись для TalkBack, обработчик и видимость
(см. docs/Project.md, «button_area: три переиспользуемых слота»)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import flet as ft

from ui.gestures import no_op
from ui.theme import (
    BUTTON_AREA_MARGIN,
    BUTTON_ICON_SIZE,
    BUTTON_ICONS,
    BUTTON_SIZE,
    BUTTON_SPACING,
)


@dataclass(frozen=True)
class ButtonAction:
    """Действие одного слота button_area.

    Кнопки постоянные (плюс, карандаш, корзина), а действие зависит от
    выделения: у категорий и пунктов иконки одни и те же, поэтому слот хранит
    только подпись (её читает TalkBack), обработчик и видимость.
    """

    label: str
    handler: Callable[..., object] = no_op
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
