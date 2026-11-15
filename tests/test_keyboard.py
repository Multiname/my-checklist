"""Клавиатура на Android: как приложение узнаёт, что она открыта, и
как ввод названия завершается её скрытием."""

from support import FakePage, media
from ui.app import ChecklistApp


def test_keyboard_visible_by_navigation_padding():
    # При adjustResize keyboard hidden = нижний padding навигации на месте,
    # open = он пропал.
    assert ChecklistApp._keyboard_visible(media(bottom_padding=16)) is False
    assert ChecklistApp._keyboard_visible(media(bottom_padding=0)) is True


def test_keyboard_visible_by_view_insets():
    assert ChecklistApp._keyboard_visible(media(bottom_inset=300)) is True


def test_keyboard_visible_without_client_media():
    assert ChecklistApp._keyboard_visible(media(pixel_ratio=0)) is False


def test_keyboard_close_commits_editing():
    page = FakePage()
    app = ChecklistApp(page, storage=None)
    view = object()
    app._editing_view = view

    app._on_media_change(media(bottom_padding=0))
    assert page.tasks == []

    app._on_media_change(media(bottom_padding=16))

    assert len(page.tasks) == 1
    handler, args = page.tasks[0]
    assert handler == app._finish_title_input
    assert args == (view,)


def test_keyboard_close_without_editing_does_nothing():
    page = FakePage()
    app = ChecklistApp(page, storage=None)

    app._on_media_change(media(bottom_padding=0))
    app._on_media_change(media(bottom_padding=16))

    assert page.tasks == []
