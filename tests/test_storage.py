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
