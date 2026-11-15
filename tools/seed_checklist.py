"""Создаёт seed-БД для замеров прокрутки: категории по пять пунктов.

Нужен, чтобы замеры на устройстве шли на одинаковых данных:

    .venv\\Scripts\\python.exe tools\\seed_checklist.py .tmp\\seed.db

Готовый файл заливается на телефон (см. docs/Verification.md, «Замеры
прокрутки»): `adb push`, затем `run-as com.blackline.my_checklist cp`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import storage  # noqa: E402


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp/seed.db")
    for suffix in ("", "-wal", "-shm"):
        side = Path(str(path) + suffix)
        if side.exists():
            side.unlink()

    store = storage.open_storage(path)
    try:
        for category_index in range(15):
            category = store.create_category(f"Категория {category_index + 1}")
            for item_index in range(5):
                item = store.create_item(
                    category.id, f"Пункт {category_index + 1}.{item_index + 1}"
                )
                # Каждый третий пункт отмечен: в списке есть и серые строки.
                if item_index % 3 == 1:
                    store.set_item_checked(item.id, True)
    finally:
        store.close()

    print(f"seed: {path} ({path.stat().st_size} байт, 15 категорий по 5 пунктов)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
