"""Тесты слоя хранения: схема, категории, сохранность между запусками."""

import sqlite3
from pathlib import Path

import pytest

import domain
import storage


def open_db(tmp_path: Path) -> storage.Storage:
    return storage.open_storage(tmp_path / "app.db")


def read_rows(db_path: Path, query: str, parameters: tuple = ()) -> list[tuple]:
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(query, parameters).fetchall()
    finally:
        connection.close()


def test_first_run_creates_empty_database(tmp_path):
    database = open_db(tmp_path)
    try:
        assert database.list_categories() == []
        assert database.recovered_backup is None
    finally:
        database.close()


def test_schema_version_is_recorded(tmp_path):
    db_path = tmp_path / "app.db"
    open_db(tmp_path).close()

    assert read_rows(
        db_path, "SELECT value FROM meta WHERE key = 'schema_version'"
    ) == [(str(storage.SCHEMA_VERSION),)]


def test_create_category_appends_to_end(tmp_path):
    database = open_db(tmp_path)
    try:
        first = database.create_category()
        second = database.create_category("Работа")

        assert first == domain.Category(id=first.id, title="Категория", position=0)
        assert second.title == "Работа"
        assert [
            (category.title, category.position)
            for category in database.list_categories()
        ] == [("Категория", 0), ("Работа", 1)]
    finally:
        database.close()


def test_create_category_normalizes_title(tmp_path):
    database = open_db(tmp_path)
    try:
        assert database.create_category("  Дом  ").title == "Дом"
        assert database.create_category("   ").title == "Категория"
    finally:
        database.close()


def test_created_category_survives_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    created = database.create_category("Работа")
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert database.list_categories() == [created]
    finally:
        database.close()


def test_set_category_title_saves_and_survives_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    category = database.create_category()
    saved_title = database.set_category_title(category.id, "  Работа ")
    database.close()
    assert saved_title == "Работа"

    database = storage.open_storage(db_path)
    try:
        assert database.list_categories() == [
            domain.Category(id=category.id, title="Работа", position=0)
        ]
    finally:
        database.close()


def make_categories(database: storage.Storage, *titles: str) -> list[domain.Category]:
    return [database.create_category(title) for title in titles]


def test_move_category_down_keeps_order_and_positions(tmp_path):
    database = open_db(tmp_path)
    try:
        home, work, rest = make_categories(database, "Дом", "Работа", "Отдых")

        ordered = database.move_category(home.id, 2)

        assert ordered == [
            domain.Category(id=work.id, title="Работа", position=0),
            domain.Category(id=rest.id, title="Отдых", position=1),
            domain.Category(id=home.id, title="Дом", position=2),
        ]
        assert database.list_categories() == ordered
    finally:
        database.close()


def test_move_category_up_keeps_order_and_positions(tmp_path):
    database = open_db(tmp_path)
    try:
        home, work, rest = make_categories(database, "Дом", "Работа", "Отдых")

        ordered = database.move_category(rest.id, 0)

        assert [category.title for category in ordered] == [
            "Отдых",
            "Дом",
            "Работа",
        ]
        assert [category.position for category in ordered] == [0, 1, 2]
    finally:
        database.close()


def test_move_category_clamps_position_to_list_bounds(tmp_path):
    database = open_db(tmp_path)
    try:
        home, work = make_categories(database, "Дом", "Работа")

        assert [c.title for c in database.move_category(home.id, 99)] == [
            "Работа",
            "Дом",
        ]
        assert [c.title for c in database.move_category(home.id, -5)] == [
            "Дом",
            "Работа",
        ]
    finally:
        database.close()


def test_moved_order_survives_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home, work, rest = make_categories(database, "Дом", "Работа", "Отдых")
    database.move_category(home.id, 2)
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert [
            (category.title, category.position)
            for category in database.list_categories()
        ] == [("Работа", 0), ("Отдых", 1), ("Дом", 2)]
    finally:
        database.close()


def test_move_unknown_category_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        make_categories(database, "Дом")

        with pytest.raises(storage.StorageError):
            database.move_category(999, 0)
        assert [c.title for c in database.list_categories()] == ["Дом"]
    finally:
        database.close()


def test_delete_category_removes_it_and_keeps_positions_continuous(tmp_path):
    database = open_db(tmp_path)
    try:
        home, work, rest = make_categories(database, "Дом", "Работа", "Отдых")

        remaining = database.delete_category(home.id)

        assert remaining == [
            domain.Category(id=work.id, title="Работа", position=0),
            domain.Category(id=rest.id, title="Отдых", position=1),
        ]
        assert database.list_categories() == remaining
    finally:
        database.close()


def test_deleted_category_stays_deleted_after_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home, work = make_categories(database, "Дом", "Работа")
    database.delete_category(home.id)
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert [
            (category.title, category.position)
            for category in database.list_categories()
        ] == [("Работа", 0)]
    finally:
        database.close()


def test_delete_category_removes_its_items(tmp_path):
    """Пункты удалённой категории уходят каскадом (feature-storage.md)."""
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home, work = make_categories(database, "Дом", "Работа")
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO items (category_id, title, position) VALUES (?, ?, ?)",
            (home.id, "Помыть посуду", 0),
        )
        connection.execute(
            "INSERT INTO items (category_id, title, position) VALUES (?, ?, ?)",
            (home.id, "Пропылесосить", 1),
        )
        connection.execute(
            "INSERT INTO items (category_id, title, position) VALUES (?, ?, ?)",
            (work.id, "Отчёт", 0),
        )
        connection.commit()
    finally:
        connection.close()

    database.delete_category(home.id)

    assert read_rows(db_path, "SELECT title FROM items ORDER BY position") == [
        ("Отчёт",)
    ]
    database.close()


def test_delete_category_removes_items_created_through_storage(tmp_path):
    """Каскад удаляет и пункты, созданные обычными операциями хранилища.

    После повторного открытия БД в ней нет ни удалённой категории, ни её
    пунктов, а пункты других категорий остаются на своих местах
    (docs/features/feature-storage.md, сценарий 5).
    """
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home, work = make_categories(database, "Дом", "Работа")
    database.create_item(home.id, "Помыть посуду")
    database.create_item(home.id, "Пропылесосить")
    database.create_item(work.id, "Отчёт")

    database.delete_category(home.id)
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert [
            (category.title, category.position)
            for category in database.list_categories()
        ] == [("Работа", 0)]
        assert [
            (item.title, item.category_id, item.position)
            for item in database.list_items()
        ] == [("Отчёт", work.id, 0)]
    finally:
        database.close()

    # В самой БД тоже не осталось пунктов удалённой категории.
    assert read_rows(db_path, "SELECT category_id FROM items") == [(work.id,)]


def test_delete_unknown_category_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        make_categories(database, "Дом")

        with pytest.raises(storage.StorageError):
            database.delete_category(999)
        assert [c.title for c in database.list_categories()] == ["Дом"]
    finally:
        database.close()


def test_positions_are_normalized_on_load(tmp_path):
    db_path = tmp_path / "app.db"
    open_db(tmp_path).close()

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO categories (title, position) VALUES ('Первая', 5), ('Вторая', 5)"
        )
        connection.commit()
    finally:
        connection.close()

    database = storage.open_storage(db_path)
    try:
        assert [
            (category.title, category.position)
            for category in database.list_categories()
        ] == [("Первая", 0), ("Вторая", 1)]
    finally:
        database.close()


def test_newer_schema_is_rejected(tmp_path):
    db_path = tmp_path / "app.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "INSERT INTO meta (key, value) VALUES ('schema_version', '99');"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(storage.SchemaTooNewError):
        storage.open_storage(db_path)


def test_corrupt_database_is_quarantined(tmp_path):
    db_path = tmp_path / "app.db"
    db_path.write_bytes(b"this is definitely not an sqlite database")

    database = storage.open_storage(db_path)
    try:
        assert database.recovered_backup is not None
        assert database.recovered_backup.is_file()
        assert (
            database.recovered_backup.read_bytes()
            == b"this is definitely not an sqlite database"
        )
        assert database.list_categories() == []
    finally:
        database.close()


def test_default_db_path_uses_flet_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))

    assert storage.default_db_path() == tmp_path / storage.DB_FILENAME


def test_default_db_path_falls_back_to_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    monkeypatch.chdir(tmp_path)

    assert storage.default_db_path() == tmp_path / storage.DB_FILENAME


def test_create_item_appends_to_the_category_and_starts_unchecked(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")

        first = database.create_item(home.id, "Помыть посуду")
        second = database.create_item(home.id)

        assert first == domain.Item(
            id=first.id,
            category_id=home.id,
            title="Помыть посуду",
            is_checked=False,
            position=0,
        )
        assert (second.title, second.position) == ("Пункт", 1)
        assert database.list_items() == [first, second]
    finally:
        database.close()


def test_create_item_normalizes_title(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")

        assert database.create_item(home.id, "  Помыть  ").title == "Помыть"
        assert database.create_item(home.id, "   ").title == "Пункт"
    finally:
        database.close()


def test_create_item_in_unknown_category_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        with pytest.raises(storage.StorageError):
            database.create_item(999)
        assert database.list_items() == []
    finally:
        database.close()


def test_created_items_survive_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home = database.create_category("Дом")
    first = database.create_item(home.id, "Помыть посуду")
    second = database.create_item(home.id, "Пропылесосить")
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert database.list_items() == [first, second]
    finally:
        database.close()


def test_list_items_orders_by_category_order_and_position(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        work = database.create_category("Работа")
        home_first = database.create_item(home.id, "Посуда")
        work_first = database.create_item(work.id, "Отчёт")
        home_second = database.create_item(home.id, "Пылесос")

        assert database.list_items() == [home_first, home_second, work_first]

        # Пункты идут в порядке категорий: после перестановки категорий
        # меняется и порядок пунктов, не теряя порядка внутри категории.
        database.move_category(work.id, 0)
        assert database.list_items() == [work_first, home_first, home_second]
    finally:
        database.close()


def test_set_item_title_saves_and_survives_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home = database.create_category("Дом")
    created = database.create_item(home.id)

    saved = database.set_item_title(created.id, "  Купить хлеб ")
    database.close()
    assert saved == "Купить хлеб"

    database = storage.open_storage(db_path)
    try:
        assert database.list_items() == [
            domain.Item(
                id=created.id,
                category_id=home.id,
                title="Купить хлеб",
                is_checked=False,
                position=0,
            )
        ]
    finally:
        database.close()


def test_item_positions_are_normalized_on_load(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home = database.create_category("Дом")
    database.close()

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO items (category_id, title, position) "
            "VALUES (?, 'Первая', 5), (?, 'Вторая', 5)",
            (home.id, home.id),
        )
        connection.commit()
    finally:
        connection.close()

    database = storage.open_storage(db_path)
    try:
        assert [(item.title, item.position) for item in database.list_items()] == [
            ("Первая", 0),
            ("Вторая", 1),
        ]
    finally:
        database.close()


def test_item_positions_are_per_category(tmp_path):
    """Позиция пункта считается внутри своей категории, а не по всей таблице."""
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        work = database.create_category("Работа")

        home_first = database.create_item(home.id, "Посуда")
        work_first = database.create_item(work.id, "Отчёт")

        assert (home_first.position, work_first.position) == (0, 0)
    finally:
        database.close()


def item_titles(items: list[domain.Item]) -> list[str]:
    return [item.title for item in items]


def test_move_item_down_keeps_order_and_positions(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        first = database.create_item(home.id, "Первый")
        second = database.create_item(home.id, "Второй")
        third = database.create_item(home.id, "Третий")

        orders = database.move_item(first.id, home.id, 2)

        # Позиция — как у move_category: в списке после удаления перемещаемого.
        assert list(orders) == [home.id]
        assert item_titles(orders[home.id]) == ["Второй", "Третий", "Первый"]
        assert [item.position for item in orders[home.id]] == [0, 1, 2]
        assert database.list_items() == orders[home.id]
        # Пункт не потерялся: id и категория прежние.
        assert orders[home.id][-1].id == first.id
        assert orders[home.id][0].id == second.id
        assert orders[home.id][1].id == third.id
    finally:
        database.close()


def test_move_item_up_keeps_order_and_positions(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        first = database.create_item(home.id, "Первый")
        second = database.create_item(home.id, "Второй")
        third = database.create_item(home.id, "Третий")

        ordered = database.move_item(third.id, home.id, 0)[home.id]

        assert item_titles(ordered) == ["Третий", "Первый", "Второй"]
        assert [item.id for item in ordered] == [third.id, first.id, second.id]
    finally:
        database.close()


def test_move_item_clamps_position_to_the_category_bounds(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        first = database.create_item(home.id, "Первый")
        second = database.create_item(home.id, "Второй")

        assert item_titles(database.move_item(first.id, home.id, 99)[home.id]) == [
            "Второй",
            "Первый",
        ]
        assert item_titles(database.move_item(first.id, home.id, -5)[home.id]) == [
            "Первый",
            "Второй",
        ]
    finally:
        database.close()


def test_move_item_to_another_category_orders_both_categories(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        work = database.create_category("Работа")
        dishes = database.create_item(home.id, "Посуда")
        vacuum = database.create_item(home.id, "Пылесос")
        report = database.create_item(work.id, "Отчёт")

        orders = database.move_item(vacuum.id, work.id, 0)

        assert set(orders) == {home.id, work.id}
        assert item_titles(orders[home.id]) == ["Посуда"]
        assert [item.position for item in orders[home.id]] == [0]
        assert item_titles(orders[work.id]) == ["Пылесос", "Отчёт"]
        assert [item.position for item in orders[work.id]] == [0, 1]
        # Пункт теперь принадлежит новой категории, а не прежней.
        assert [item.category_id for item in orders[work.id]] == [work.id, work.id]
        assert orders[work.id][0].id == vacuum.id
        assert orders[work.id][1].id == report.id
        assert orders[home.id][0].id == dishes.id
        assert item_titles(database.list_items()) == ["Посуда", "Пылесос", "Отчёт"]
    finally:
        database.close()


def test_move_item_to_empty_category_starts_at_zero(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        work = database.create_category("Работа")
        only = database.create_item(home.id, "Посуда")

        orders = database.move_item(only.id, work.id, 0)

        assert orders[home.id] == []
        assert [(item.title, item.position) for item in orders[work.id]] == [
            ("Посуда", 0)
        ]
        assert item_titles(database.list_items()) == ["Посуда"]
    finally:
        database.close()


def test_moved_item_order_survives_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home = database.create_category("Дом")
    work = database.create_category("Работа")
    first = database.create_item(home.id, "Первый")
    second = database.create_item(home.id, "Второй")
    database.create_item(work.id, "Отчёт")
    database.move_item(second.id, work.id, 1)
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert [
            (item.title, item.category_id, item.position)
            for item in database.list_items()
        ] == [
            ("Первый", home.id, 0),
            ("Отчёт", work.id, 0),
            ("Второй", work.id, 1),
        ]
        assert database.list_items()[2].id == second.id
        assert database.list_items()[0].id == first.id
    finally:
        database.close()


def test_move_unknown_item_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        created = database.create_item(home.id, "Посуда")

        with pytest.raises(storage.StorageError):
            database.move_item(999, home.id, 0)
        assert database.list_items() == [created]
    finally:
        database.close()


def test_move_item_to_unknown_category_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        created = database.create_item(home.id, "Посуда")

        with pytest.raises(storage.StorageError):
            database.move_item(created.id, 999, 0)
        # БД не изменилась: пункт остался в своей категории.
        assert database.list_items() == [created]
    finally:
        database.close()


def test_delete_item_removes_it_and_keeps_positions_continuous(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        first = database.create_item(home.id, "Первый")
        second = database.create_item(home.id, "Второй")
        third = database.create_item(home.id, "Третий")

        remaining = database.delete_item(second.id)

        assert remaining == [
            domain.Item(
                id=first.id,
                category_id=home.id,
                title="Первый",
                is_checked=False,
                position=0,
            ),
            domain.Item(
                id=third.id,
                category_id=home.id,
                title="Третий",
                is_checked=False,
                position=1,
            ),
        ]
        assert database.list_items() == remaining
    finally:
        database.close()


def test_delete_item_keeps_other_categories_untouched(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        work = database.create_category("Работа")
        home_first = database.create_item(home.id, "Посуда")
        home_second = database.create_item(home.id, "Пылесос")
        work_first = database.create_item(work.id, "Отчёт")

        remaining = database.delete_item(home_first.id)

        assert [item.id for item in remaining] == [home_second.id]
        assert database.list_items() == [
            domain.Item(
                id=home_second.id,
                category_id=home.id,
                title="Пылесос",
                is_checked=False,
                position=0,
            ),
            domain.Item(
                id=work_first.id,
                category_id=work.id,
                title="Отчёт",
                is_checked=False,
                position=0,
            ),
        ]
    finally:
        database.close()


def test_deleted_item_stays_deleted_after_reopen(tmp_path):
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home = database.create_category("Дом")
    first = database.create_item(home.id, "Первый")
    second = database.create_item(home.id, "Второй")
    database.delete_item(first.id)
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert database.list_items() == [
            domain.Item(
                id=second.id,
                category_id=home.id,
                title="Второй",
                is_checked=False,
                position=0,
            )
        ]
    finally:
        database.close()


def test_delete_unknown_item_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        created = database.create_item(home.id, "Посуда")

        with pytest.raises(storage.StorageError):
            database.delete_item(999)
        assert database.list_items() == [created]
    finally:
        database.close()


def test_set_item_checked_saves_explicit_value_and_survives_reopen(tmp_path):
    """Отметка пишется явно и восстанавливается после перезапуска.

    Значение передаётся аргументом, а не инвертируется в SQL: повторная запись
    того же значения отметку не переворачивает (см. feature-storage.md).
    """
    db_path = tmp_path / "app.db"
    database = storage.open_storage(db_path)
    home = database.create_category("Дом")
    first = database.create_item(home.id, "Молоко")
    second = database.create_item(home.id, "Хлеб")

    assert database.set_item_checked(first.id, True) is True
    assert database.set_item_checked(first.id, True) is True
    database.close()

    database = storage.open_storage(db_path)
    try:
        assert [(item.title, item.is_checked) for item in database.list_items()] == [
            ("Молоко", True),
            ("Хлеб", False),
        ]
        assert database.list_items()[0].position == first.position
        assert database.list_items()[1].position == second.position
    finally:
        database.close()


def test_set_item_checked_can_be_cleared(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        created = database.create_item(home.id, "Молоко")
        database.set_item_checked(created.id, True)

        assert database.set_item_checked(created.id, False) is False
        assert database.list_items()[0].is_checked is False
    finally:
        database.close()


def test_set_item_checked_does_not_touch_other_items(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        work = database.create_category("Работа")
        first = database.create_item(home.id, "Молоко")
        other = database.create_item(home.id, "Хлеб")
        report = database.create_item(work.id, "Отчёт")

        database.set_item_checked(first.id, True)

        assert [(item.id, item.is_checked) for item in database.list_items()] == [
            (first.id, True),
            (other.id, False),
            (report.id, False),
        ]
    finally:
        database.close()


def test_set_item_checked_unknown_item_is_rejected(tmp_path):
    database = open_db(tmp_path)
    try:
        home = database.create_category("Дом")
        created = database.create_item(home.id, "Посуда")

        with pytest.raises(storage.StorageError):
            database.set_item_checked(999, True)
        # БД не изменилась: отметка прежняя.
        assert database.list_items() == [created]
    finally:
        database.close()

