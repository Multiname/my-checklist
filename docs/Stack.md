# Stack.md — стек и версии

## Язык
- Python 3.12 (Flet требует Python ≥ 3.10; версия фиксируется, чтобы локальная
  среда совпадала с интерпретатором, встроенным в APK)
- Стандартная библиотека + Flet; каждая сторонняя зависимость добавляется осознанно

## UI: Flet 1.1.x
- Flet 1.1.2 — Python-фреймворк, рендер через Flutter: весь UI пишется на Python,
  без Dart, Kotlin, Swift и JS
- Лицензия Apache-2.0, тема Material 3 из коробки
- API 1.x: точка входа `ft.run(main)`; устаревший `ft.app(target=main)` из 0.x не
  использовать
- Контролы, на которые опирается спека:
    - `GestureDetector` — долгое нажатие (`on_long_press_start`,
      `on_long_press_end`, `on_long_press_move_update`, `on_long_press_cancel`), тап
      (`on_tap`, `on_tap_cancel`), `on_size_change` (`size_change` — размеры
      контролов приходят от клиента)
    - `ListView` (`cache_extent`, `scroll_to`, `on_scroll`), `Stack`, `SafeArea`,
      `TextField`, `Checkbox`, `IconButton`, `Image`
- Известные ограничения Flet, принятые заранее:
    - перетаскивание пункта между категориями не встроено — реализуется вручную
      на событиях жеста, со своим прокси, зазором и автопрокруткой
    - автоскролл у краёв при перетаскивании — вручную (программный скролл клиента)
    - размер APK — десятки МБ (CPython + движок Flutter), это ожидаемо
    - нативные виджеты не используются; платформенные мелочи (системная кнопка
      «Назад», поведение клавиатуры) проверяются на живом устройстве
- Ошибка 1.1.2, обойдённая в коде: клиент присылает `offset_from_origin` как `ofo`
  в `LongPressMoveUpdateEvent` — см. [Project.md](Project.md), «Перетаскивание
  пунктов».

## Хранилище: SQLite
- SQLite через стандартный модуль `sqlite3`, без ORM и без нативных зависимостей
- Схема, инварианты, транзакции и миграции — в
  [feature-storage.md](features/feature-storage.md)
- Никаких сетевых БД, аккаунтов и синхронизации: приложение полностью локальное

## Сборка и платформа
- Целевая платформа — только Android (см. Non-Goals в
  [ProjectIntent.md](ProjectIntent.md)): iOS и веб не поддерживаются
- `flet build apk` и `flet build aab` собираются на Windows; JDK 17 и Android SDK
  Flet устанавливает сам
- `--split-per-abi` — если нужен APK меньшего размера для сайдлоада
- Локальная итерация — `flet run` на десктопе, проверка на устройстве —
  `tools\run_on_device.cmd` (см. [Environment.md](Environment.md))
- Минимальная версия Android задаётся шаблоном Flet
  (`android/app/build.gradle.kts`) и фиксируется в репозитории при первом билде
- Релизная сборка и подпись пока не настраивались — [KnownIssues.md](KnownIssues.md)

## Правила для реализации
- Не добавлять зависимости с нативным кодом (`numpy`, `cryptography`, пакеты с
  `pydantic-core` и т.п.): для Android нужны готовые колёса, иначе сборка APK падает
- Версия Flet фиксируется в `pyproject.toml` и не обновляется без чтения changelog:
  между мажорными версиями менялся API
- Один экран, без навигации и настроек
- Тесты: `pytest` для доменной логики, слоя хранения и параметров UI-шаблонов;
  интерактивных UI-тестов (эмулятор, скриншоты) нет — поведение на устройстве
  проверяется вручную по [Verification.md](Verification.md)

## Версии
| Компонент | Версия | Где фиксируется |
|---|---|---|
| Python | 3.12.16 | `pyproject.toml` (`requires-python`), `.python/3.12` |
| Flet | 1.1.2 | `pyproject.toml` |
| SQLite | встроенный в CPython | — |
| pytest | 9.2.0 | `pyproject.toml` (dev-зависимости) |
