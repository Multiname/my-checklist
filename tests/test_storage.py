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
