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

from domain import (
    DEFAULT_CATEGORY_TITLE,
    DEFAULT_ITEM_TITLE,
    Category,
    Item,
    normalize_title,
)

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
    """Категории и пункты в SQLite. Одна пользовательская операция — одна транзакция."""

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

    def delete_category(self, category_id: int) -> list[Category]:
        """Удаляет категорию и возвращает оставшийся порядок категорий.

        Пункты удалённой категории уходят каскадом (`ON DELETE CASCADE`),
        отдельного удаления не нужно (см. docs/features/feature-storage.md).
        Позиции оставшихся категорий материализуются заново, поэтому дыр
        в порядке не остаётся; возвращённый список — источник истины для UI.
        Неизвестный ``id`` — ``StorageError``, БД при этом не меняется.
        """
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM categories WHERE id = ?", (category_id,)
            )
            if cursor.rowcount == 0:
                # Транзакция откатится: удалять было нечего.
                raise StorageError(f"Категория {category_id} не найдена")
            _materialize_category_positions(self._conn)
            rows = self._conn.execute(
                "SELECT id, title, position FROM categories "
                "ORDER BY position ASC, id ASC"
            ).fetchall()
        return [
            Category(id=row["id"], title=row["title"], position=row["position"])
            for row in rows
        ]

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

    def list_items(self) -> list[Item]:
        """Все пункты в порядке категорий и позиций внутри каждой категории.

        Один запрос с JOIN, без N+1 (см. docs/features/feature-storage.md):
        JOIN нужен только ради порядка — пункты идут в том же порядке
        категорий, что и на экране, а внутри категории — по ``position``.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT i.id, i.category_id, i.title, i.is_checked, i.position "
                "FROM items AS i JOIN categories AS c ON c.id = i.category_id "
                "ORDER BY c.position ASC, i.position ASC, i.id ASC"
            ).fetchall()
        return [_item_from_row(row) for row in rows]

    def create_item(
        self, category_id: int, title: str = DEFAULT_ITEM_TITLE
    ) -> Item:
        """Добавляет пункт в конец категории и возвращает его.

        Пункт без категории не существует (``category_id`` NOT NULL), поэтому
        неизвестный ``category_id`` — ``StorageError``, а БД не меняется
        (транзакция откатывается). Отметка при создании снята —
        ``is_checked = 0`` (см. docs/features/feature-item.md).
        """
        title = normalize_title(title, DEFAULT_ITEM_TITLE)
        with self._lock, self._conn:
            known = self._conn.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category_id,)
            ).fetchone()
            if known is None:
                raise StorageError(f"Категория {category_id} не найдена")
            (next_position,) = self._conn.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM items "
                "WHERE category_id = ?",
                (category_id,),
            ).fetchone()
            cursor = self._conn.execute(
                "INSERT INTO items (category_id, title, is_checked, position) "
                "VALUES (?, ?, 0, ?)",
                (category_id, title, next_position),
            )
            item_id = int(cursor.lastrowid or 0)
            _materialize_item_positions(self._conn, category_id)
            (position,) = self._conn.execute(
                "SELECT position FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        return Item(
            id=item_id,
            category_id=category_id,
            title=title,
            is_checked=False,
            position=position,
        )

    def set_item_title(self, item_id: int, title: str) -> str:
        """Сохраняет название пункта; возвращает нормализованное значение."""
        title = normalize_title(title, DEFAULT_ITEM_TITLE)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE items SET title = ? WHERE id = ?", (title, item_id)
            )
        return title

    def set_item_checked(self, item_id: int, is_checked: bool) -> bool:
        """Сохраняет отметку пункта; возвращает записанное значение.

        Значение передаётся явно (`is_checked`), а не инвертируется в SQL
        (см. docs/features/feature-storage.md): так запись остаётся
        идемпотентной, и повторное событие клиента не перевернёт отметку
        обратно. Неизвестный ``id`` — ``StorageError``, БД при этом не
        меняется (транзакция откатывается).
        """
        value = 1 if is_checked else 0
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE items SET is_checked = ? WHERE id = ?", (value, item_id)
            )
            if cursor.rowcount == 0:
                raise StorageError(f"Пункт {item_id} не найден")
        return bool(value)

    def move_item(
        self, item_id: int, category_id: int, new_position: int
    ) -> dict[int, list[Item]]:
        """Перемещает пункт и возвращает порядок затронутых категорий.

        ``category_id`` — категория, в которую встаёт пункт (может быть прежней),
        ``new_position`` — позиция среди пунктов этой категории после удаления
        перемещаемого пункта (так же, как у ``move_category``); значение вне
        диапазона подрезается. При переносе в другую категорию позиции
        материализуются заново в двух контейнерах — прежней и новой категории
        (см. docs/features/feature-storage.md), поэтому дыр в порядке не
        остаётся. Неизвестный пункт или категория — ``StorageError``, БД при
        этом не меняется (транзакция откатывается).
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT category_id FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                raise StorageError(f"Пункт {item_id} не найден")
            previous_category_id = int(row["category_id"])
            if category_id != previous_category_id:
                known = self._conn.execute(
                    "SELECT 1 FROM categories WHERE id = ?", (category_id,)
                ).fetchone()
                if known is None:
                    raise StorageError(f"Категория {category_id} не найдена")
            target_ids = [
                moved["id"]
                for moved in self._conn.execute(
                    "SELECT id FROM items WHERE category_id = ? AND id <> ? "
                    "ORDER BY position ASC, id ASC",
                    (category_id, item_id),
                ).fetchall()
            ]
            position = max(0, min(new_position, len(target_ids)))
            target_ids.insert(position, item_id)
            self._conn.execute(
                "UPDATE items SET category_id = ? WHERE id = ?",
                (category_id, item_id),
            )
            for index, moved_id in enumerate(target_ids):
                self._conn.execute(
                    "UPDATE items SET position = ? WHERE id = ?",
                    (index, moved_id),
                )
            _materialize_item_positions(self._conn, previous_category_id)
            _materialize_item_positions(self._conn, category_id)
            affected = [previous_category_id]
            if category_id != previous_category_id:
                affected.append(category_id)
            return {cid: self._read_items(cid) for cid in affected}

    def delete_item(self, item_id: int) -> list[Item]:
        """Удаляет пункт и возвращает оставшийся порядок его категории.

        Позиции оставшихся пунктов материализуются заново, поэтому дыр в
        порядке не остаётся; возвращённый список — источник истины для UI,
        как и после ``move_item`` (см. docs/features/feature-storage.md).
        Неизвестный ``id`` — ``StorageError``, БД при этом не меняется
        (транзакция откатывается).
        """
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT category_id FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None:
                raise StorageError(f"Пункт {item_id} не найден")
            category_id = int(row["category_id"])
            self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            _materialize_item_positions(self._conn, category_id)
            return self._read_items(category_id)

    def _read_items(self, category_id: int) -> list[Item]:
        """Пункты одной категории в порядке отображения.

        Вызывается внутри транзакции ``move_item``: порядок читается из БД
        после материализации и остаётся источником истины для UI.
        """
        rows = self._conn.execute(
            "SELECT id, category_id, title, is_checked, position FROM items "
            "WHERE category_id = ? ORDER BY position ASC, id ASC",
            (category_id,),
        ).fetchall()
        return [_item_from_row(row) for row in rows]


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
    """Соединение с прагмами, схемой и нормализованным порядком строк."""
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
            _materialize_all_item_positions(connection)
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


def _materialize_item_positions(
    connection: sqlite3.Connection, category_id: int
) -> None:
    """Переписывает ``position`` пунктов категории в ``0..n-1``."""
    rows = connection.execute(
        "SELECT id, position FROM items WHERE category_id = ? "
        "ORDER BY position ASC, id ASC",
        (category_id,),
    ).fetchall()
    for position, row in enumerate(rows):
        if row["position"] != position:
            connection.execute(
                "UPDATE items SET position = ? WHERE id = ?",
                (position, row["id"]),
            )


def _materialize_all_item_positions(connection: sqlite3.Connection) -> None:
    """Нормализует порядок пунктов во всех категориях (после открытия БД)."""
    rows = connection.execute("SELECT DISTINCT category_id FROM items").fetchall()
    for row in rows:
        _materialize_item_positions(connection, row["category_id"])


def _item_from_row(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        category_id=row["category_id"],
        title=row["title"],
        is_checked=bool(row["is_checked"]),
        position=row["position"],
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
