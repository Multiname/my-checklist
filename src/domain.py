"""Доменные правила чеклиста, не зависящие от UI и хранилища.

Хранилище не придумывает значения: названия нормализуются здесь, до записи
(см. docs/features/feature-storage.md).
"""

from dataclasses import dataclass

# Название категории по умолчанию: подставляется, если ввод оставлен пустым
# (см. docs/features/feature-category.md).
DEFAULT_CATEGORY_TITLE = "Категория"


@dataclass(frozen=True)
class Category:
    """Категория — заголовок для группы пунктов."""

    id: int
    title: str
    position: int


def normalize_title(raw: str | None, default: str) -> str:
    """Приводит введённое название к значению, допустимому в БД.

    Обрезает пробелы по краям и склеивает одиночными пробелами (в названии
    категории нет переносов строк); пустой результат заменяет на ``default``:
    в БД название не может быть пустым после ``trim``.
    """
    title = " ".join((raw or "").split())
    return title or default
