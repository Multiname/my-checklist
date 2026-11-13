"""Тесты доменных правил (без UI и БД)."""

import domain


def test_normalize_title_trims_edges():
    assert domain.normalize_title("  Работа  ", domain.DEFAULT_CATEGORY_TITLE) == "Работа"


def test_normalize_title_replaces_line_breaks_with_spaces():
    assert (
        domain.normalize_title("Работа\nи дом", domain.DEFAULT_CATEGORY_TITLE)
        == "Работа и дом"
    )


def test_normalize_title_uses_default_for_empty_input():
    default = domain.DEFAULT_CATEGORY_TITLE

    assert domain.normalize_title("", default) == default
    assert domain.normalize_title("   \n ", default) == default
    assert domain.normalize_title(None, default) == default
