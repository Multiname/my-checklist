"""Шаблоны контролов: панели категории и пункта, список и поля ввода."""

import flet as ft

from support import item
from ui import theme
from ui.controls import (
    create_category_area,
    create_category_input,
    create_category_item,
    create_category_list,
    create_category_panel,
    create_category_title,
)


def test_category_panel_is_rectangular_with_title_on_top():
    panel = create_category_panel(create_category_title("Работа"))

    assert isinstance(panel, ft.Container)
    assert panel.content.value == "Работа"
    assert panel.content.style == theme.CATEGORY_TITLE_STYLE
    assert panel.bgcolor == theme.CATEGORY_PANEL_COLOR
    assert panel.border_radius == theme.CATEGORY_PANEL_RADIUS
    assert panel.padding == theme.CATEGORY_PANEL_PADDING
    # Горизонтальных отступов у панели нет: их несут название и пункты, иначе
    # выделенный пункт не смог бы закрасить панель до краёв.
    assert panel.padding.left == panel.padding.right == 0
    assert panel.padding.top == theme.CATEGORY_PANEL_VERTICAL_PADDING
    assert panel.padding.bottom == theme.CATEGORY_PANEL_VERTICAL_PADDING


def test_category_item_keeps_the_gap_inside_the_list_item():
    """Промежуток — часть элемента списка, панель остаётся панелью."""
    panel = create_category_panel("Работа")

    item = create_category_item(panel)

    assert item.content is panel
    assert item.padding == theme.CATEGORY_ITEM_PADDING
    assert item.padding == ft.Padding.only(bottom=theme.CATEGORY_SPACING)
    assert item.bgcolor is None
    assert item.margin is None


def test_category_area_only_wraps_the_list_for_taps():
    """Своей темы у области списка нет: прокси рисует приложение, а не клиент."""
    category_list = create_category_list()

    category_area = create_category_area(category_list, lambda event: None)

    assert category_area.content.content is category_list
    assert category_area.content.on_tap is not None
    assert category_area.theme is None


def test_category_list_scrolls_full_screen_above_button_area():
    category_list = create_category_list()

    assert isinstance(category_list, ft.ListView)
    assert category_list.expand is True
    # Список строится целиком: иначе scroll_to() после создания не работает.
    assert category_list.build_controls_on_demand is False
    assert category_list.auto_scroll is False
    assert category_list.padding.bottom >= theme.BUTTON_AREA_HEIGHT


def test_category_input_shows_keyboard_and_commits_on_focus_loss():
    def on_commit(event):
        pass

    category_input = create_category_input("Категория", on_commit)

    assert category_input.autofocus is True
    assert category_input.hint_text == "Категория"
    assert category_input.on_submit is on_commit
    assert category_input.on_blur is on_commit
    assert category_input.on_tap_outside is on_commit


def test_category_input_has_same_line_height_as_title():
    """Панель не должна менять высоту при переходе в режим ввода."""
    category_input = create_category_input("Категория", lambda event: None)
    title = create_category_title("Работа")

    assert category_input.text_style == title.style
    assert category_input.hint_style.size == theme.CATEGORY_TITLE_SIZE
    assert category_input.hint_style.height == theme.CATEGORY_TITLE_LINE_HEIGHT
    assert category_input.dense is True
