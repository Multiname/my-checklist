"""button_area: три постоянных слота и действия, которые они несут."""

from pathlib import Path

import pytest

from support import default_actions
from ui import theme
from ui.actions import (
    ButtonAction,
    create_button_area,
)


def test_button_area_is_pinned_to_bottom_right():
    button_area = create_button_area(default_actions())

    assert button_area.right == theme.BUTTON_AREA_MARGIN
    assert button_area.bottom == theme.BUTTON_AREA_MARGIN


def test_button_area_has_three_permanent_slots():
    """Слоты постоянные: плюс, карандаш и корзина — по кнопке на слот."""
    buttons = create_button_area(default_actions()).content.controls

    assert [button.content.src for button in buttons] == list(theme.BUTTON_ICONS)
    for button in buttons:
        assert button.width == theme.BUTTON_SIZE
        assert button.height == theme.BUTTON_SIZE
        assert button.border_radius == theme.BUTTON_SIZE / 2


def test_button_area_binds_each_action_to_its_slot():
    actions = default_actions()

    buttons = create_button_area(actions).content.controls

    assert [button.content.semantics_label for button in buttons] == [
        action.label for action in actions
    ]
    assert [button.visible for button in buttons] == [True, False, False]


def test_button_area_requires_one_action_per_slot():
    with pytest.raises(ValueError):
        create_button_area([ButtonAction(theme.LABEL_CREATE_CATEGORY)])


def test_buttons_are_clickable_with_ink_ripple():
    for button in create_button_area(default_actions()).content.controls:
        assert button.ink is True
        assert callable(button.on_click)


@pytest.mark.parametrize("slot", [0, 1, 2])
def test_slot_runs_given_handler(slot):
    """Каждый слот зовёт своё действие — слоты не перепутаны местами."""
    events = []
    actions = default_actions()
    actions[slot] = ButtonAction(
        actions[slot].label, lambda event: events.append(event)
    )
    button = create_button_area(actions).content.controls[slot]

    button.on_click(None)

    assert len(events) == 1


def test_button_icons_exist_in_assets():
    assets_dir = Path(__file__).parent.parent / "src" / "assets"

    for icon in theme.BUTTON_ICONS:
        assert (assets_dir / icon).is_file()
