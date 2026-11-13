from pathlib import Path

import flet as ft

import main


def test_app_module_is_importable():
    assert callable(main.main)


def test_button_area_is_pinned_to_bottom_right():
    button_area = main.create_button_area()

    assert button_area.right == main.BUTTON_AREA_MARGIN
    assert button_area.bottom == main.BUTTON_AREA_MARGIN


def test_button_area_has_category_buttons():
    buttons = main.create_button_area().content.controls

    assert [button.content.src for button in buttons] == [
        main.ICON_PLUS,
        main.ICON_PENCIL,
        main.ICON_TRASH,
    ]
    for button in buttons:
        assert button.width == main.BUTTON_SIZE
        assert button.height == main.BUTTON_SIZE
        assert button.shape == ft.BoxShape.CIRCLE


def test_button_icons_exist_in_assets():
    assets_dir = Path(__file__).parent.parent / "src" / "assets"

    for icon in (main.ICON_PLUS, main.ICON_PENCIL, main.ICON_TRASH):
        assert (assets_dir / icon).is_file()
