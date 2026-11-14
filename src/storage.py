"""Слой хранения чеклиста: локальная БД SQLite без ORM.

Правила схемы, порядка и транзакций — в docs/features/feature-storage.md.
Слой синхронный: приложение вызывает его из потоков (`asyncio.to_thread`),
поэтому соединение открыто с `check_same_thread=False`, а доступ к нему
сериализуется блокировкой.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

from domain import DEFAULT_CATEGORY_TITLE, Category, normalize_title

DB_FILENAME = "app.db"
SCHEMA_VERSION = 1

# Миграции применяются последовательно: ключ — версия, в которую переводит
# набор операторов. Каждый набор выполняется в своей транзакции.
_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS categories (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            title    TEXT    NOT NULL CHECK (length(trim(title)) > 0),
            position INTEGER NOT NULL CHECK (position >= 0)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL
                        REFERENCES categories(id) ON DELETE CASCADE,
            title       TEXT    NOT NULL CHECK (length(trim(title)) > 0),
            is_checked  INTEGER NOT NULL DEFAULT 0 CHECK (is_checked IN (0, 1)),
            position    INTEGER NOT NULL CHECK (position >= 0)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_items_category_position
            ON items(category_id, position)
        """,
    ),
}


class StorageError(Exception):
    """Хранилище не удалось открыть или изменить."""


class SchemaTooNewError(StorageError):
    """Файл БД создан более новой версией приложения: понижение не поддерживается."""

    def __init__(self, found: int) -> None:
        super().__init__(
            f"Версия схемы БД {found} новее поддерживаемой {SCHEMA_VERSION}: "
            "обновите приложение"
        )
        self.found = found


def default_db_path() -> Path:
    """Путь к ``app.db`` в приватном каталоге данных приложения.

    Клиент Flet выставляет `FLET_APP_STORAGE_DATA`: на Android это внутреннее
    хранилище приложения, в ``flet run`` — ``.flet/storage/data``. В собранном
    приложении рабочий каталог процесса — тот же каталог данных, поэтому
    запасной вариант — текущий каталог.
    """
    data_dir = os.environ.get("FLET_APP_STORAGE_DATA")
    return Path(data_dir or Path.cwd()) / DB_FILENAME


class Storage:
    """Категории в SQLite. Одна пользовательская операция — одна транзакция."""

    def __init__(
        self, connection: sqlite3.Connection, *, recovered_backup: Path | None = None
    ) -> None:
        self._conn = connection
        self._lock = threading.Lock()
        self.recovered_backup = recovered_backup
        """Куда переименован повреждённый файл БД, если его пришлось заменить."""

    def close(self) -> None:
        self._conn.close()

    def list_categories(self) -> list[Category]:
        """Все категории в порядке отображения."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, position FROM categories "
                "ORDER BY position ASC, id ASC"
            ).fetchall()
        return [
            Category(id=row["id"], title=row["title"], position=row["position"])
            for row in rows
        ]

    def create_category(self, title: str = DEFAULT_CATEGORY_TITLE) -> Category:
        """Добавляет категорию в конец списка и возвращает её."""
        title = normalize_title(title, DEFAULT_CATEGORY_TITLE)
        with self._lock, self._conn:
            (next_position,) = self._conn.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM categories"
            ).fetchone()
            cursor = self._conn.execute(
                "INSERT INTO categories (title, position) VALUES (?, ?)",
                (title, next_position),
            )
            category_id = int(cursor.lastrowid or 0)
            _materialize_category_positions(self._conn)
            (position,) = self._conn.execute(
                "SELECT position FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
        return Category(id=category_id, title=title, position=position)

    def set_category_title(self, category_id: int, title: str) -> str:
        """Сохраняет название категории; возвращает нормализованное значение."""
        title = normalize_title(title, DEFAULT_CATEGORY_TITLE)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE categories SET title = ? WHERE id = ?", (title, category_id)
            )
        return title

    def move_category(self, category_id: int, new_position: int) -> list[Category]:
        """Переставляет категорию и возвращает получившийся порядок категорий.

        ``new_position`` — позиция в списке после удаления перемещаемой
        категории (так её присылает `ReorderableListView`); значение вне
        диапазона подрезается к ``0..n-1``. Позиции после перемещения
        материализуются заново, как и после любой изменяющей операции
        (см. docs/features/feature-storage.md).
        """
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id FROM categories ORDER BY position ASC, id ASC"
            ).fetchall()
            ids = [row["id"] for row in rows]
            if category_id not in ids:
                raise StorageError(f"Категория {category_id} не найдена")
            ids.remove(category_id)
            target = max(0, min(new_position, len(ids)))
            ids.insert(target, category_id)
            for position, moved_id in enumerate(ids):
                self._conn.execute(
                    "UPDATE categories SET position = ? WHERE id = ?",
                    (position, moved_id),
                )
            _materialize_category_positions(self._conn)
            rows = self._conn.execute(
                "SELECT id, title, position FROM categories "
                "ORDER BY position ASC, id ASC"
            ).fetchall()
        return [
            Category(id=row["id"], title=row["title"], position=row["position"])
            for row in rows
        ]


def open_storage(db_path: Path | str | None = None) -> Storage:
    """Открывает (при первом запуске — создаёт) БД приложения.

    Повреждённый или нечитаемый файл переименовывается в
    ``app.db.corrupt-<timestamp>`` и заменяется пустой БД: приложение не падает,
    а поле ``recovered_backup`` сообщает, куда делись прежние данные.
    """
    path = Path(db_path) if db_path is not None else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        return Storage(_open_connection(path))
    except sqlite3.DatabaseError:
        backup = _quarantine(path)
        try:
            return Storage(_open_connection(path), recovered_backup=backup)
        except sqlite3.DatabaseError as error:
            raise StorageError(f"Не удалось создать БД {path}: {error}") from error


def _open_connection(path: Path) -> sqlite3.Connection:
    """Соединение с прагмами, схемой и нормализованным порядком категорий."""
    connection = sqlite3.connect(path, check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        # Прагмы задаются на каждом соединении: foreign_keys не хранится в файле.
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        _migrate(connection)
        with connection:
            _materialize_category_positions(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def _migrate(connection: sqlite3.Connection) -> None:
    version = _schema_version(connection)
    if version > SCHEMA_VERSION:
        raise SchemaTooNewError(version)
    for target in range(version + 1, SCHEMA_VERSION + 1):
        with connection:
            for statement in _MIGRATIONS[target]:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(target),),
            )


def _schema_version(connection: sqlite3.Connection) -> int:
    meta = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone()
    if meta is None:
        return 0
    row = connection.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except ValueError as error:
        raise sqlite3.DatabaseError(
            f"Повреждённая версия схемы: {row[0]!r}"
        ) from error


def _materialize_category_positions(connection: sqlite3.Connection) -> None:
    """Переписывает ``position`` в ``0..n-1`` по текущему порядку."""
    rows = connection.execute(
        "SELECT id, position FROM categories ORDER BY position ASC, id ASC"
    ).fetchall()
    for position, row in enumerate(rows):
        if row["position"] != position:
            connection.execute(
                "UPDATE categories SET position = ? WHERE id = ?",
                (position, row["id"]),
            )


def _quarantine(path: Path) -> Path:
    """Убирает повреждённый файл БД (и его WAL-спутники) в сторону."""
    backup = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}")
    path.replace(backup)
    for suffix in ("-wal", "-shm"):
        side_file = path.with_name(path.name + suffix)
        if side_file.exists():
            side_file.replace(backup.with_name(backup.name + suffix))
    return backup
