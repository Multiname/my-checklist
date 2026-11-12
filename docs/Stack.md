### Язык
- Python 3.12 (Flet требует Python ≥ 3.10; версия фиксируется, чтобы локальная среда совпадала с интерпретатором, встроенным в APK)
- Стандартная библиотека + Flet; каждая сторонняя зависимость добавляется осознанно

### UI: Flet 1.1.x
- Flet 1.1.2 — Python-фреймворк, рендер через Flutter: весь UI пишется на Python, без Dart, Kotlin, Swift и JS
- Лицензия Apache-2.0, тема Material 3 из коробки
- API 1.x: точка входа `ft.run(main)`; устаревший `ft.app(target=main)` из 0.x не использовать
- Контролы, на которые опирается спека:
    - `GestureDetector` — долгое нажатие (`on_long_press_start`, `on_long_press_end`), тап (`on_tap`, `on_tap_cancel`), панорамирование для перетаскивания (`on_pan_start`, `on_pan_update`, `on_pan_end`), `drag_interval`
    - `Draggable` + `DragTarget` (`group`, `content_feedback`, `on_drag_start`, `on_will_accept`, `on_accept`, `on_leave`) — перетаскивание с целями сброса
    - `ReorderableListView` + `ReorderableDragHandle` — перестановка внутри одного списка (`on_reorder`)
    - `ListView`, `Stack`, `SafeArea`, `TextField`, `IconButton`, `Icon`
- Известные ограничения Flet, принятые заранее:
    - перетаскивание пункта между категориями не встроено — реализуется вручную на `Draggable`/`DragTarget`
    - автоскролл у краёв при перетаскивании — вручную (программный скролл + таймер)
    - размер APK — десятки МБ (CPython + движок Flutter), это ожидаемо
    - нативные виджеты не используются; платформенные мелочи (системная кнопка «Назад», поведение клавиатуры) проверяются на живом устройстве

### Хранилище: SQLite
- SQLite через стандартный модуль `sqlite3`, без ORM и без нативных зависимостей
- Схема, инварианты, транзакции и миграции — в [feature-storage.md](features/feature-storage.md)
- Никаких сетевых БД, аккаунтов и синхронизации: приложение полностью локальное

### Сборка и платформа
- Целевая платформа — только Android (см. Non-Goals): iOS и веб не поддерживаются
- `flet build apk` и `flet build aab` собираются на Windows; JDK 17 и Android SDK Flet устанавливает сам
- `--split-per-abi` — если нужен APK меньшего размера для сайдлоада
- Локальная итерация — `flet run` на десктопе, проверка на устройстве — `flet run --android`
- Минимальная версия Android задаётся шаблоном Flet (`android/app/build.gradle.kts`) и фиксируется в репозитории при первом билде

### Правила для реализации
- Не добавлять зависимости с нативным кодом (`numpy`, `cryptography`, пакеты с `pydantic-core` и т.п.): для Android нужны готовые колёса, иначе сборка APK падает
- Версия Flet фиксируется в `pyproject.toml` и не обновляется без чтения changelog: между мажорными версиями менялся API
- Один экран, без навигации и настроек
- Тесты: `pytest` для доменной логики и слоя хранения, UI-тесты не требуются

### Версии
| Компонент | Версия | Где фиксируется |
|---|---|---|
| Python | 3.12 | `pyproject.toml` (`requires-python`) |
| Flet | 1.1.2 | `pyproject.toml` |
| SQLite | встроенный в CPython | — |
| pytest | актуальная на момент старта | `pyproject.toml` (dev-зависимости) |