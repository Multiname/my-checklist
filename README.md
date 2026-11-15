# My checklist

Приложение для ведения списка чекбоксов: категории и пункты с отметками, только
Android, данные — локально в SQLite.

## Документация

Точка входа — [docs/README.md](docs/README.md). Коротко:

- [docs/features/](docs/features/README.md) — требования к функциям
- [docs/Design.md](docs/Design.md) — параметры внешнего вида
- [docs/Project.md](docs/Project.md) — детали реализации
- [docs/Environment.md](docs/Environment.md) — окружение, сборка, песочница
- [docs/Verification.md](docs/Verification.md) — что проверено на устройстве
- [docs/KnownIssues.md](docs/KnownIssues.md) — что осталось к выпуску

## Окружение

Окружение уже создано: `.venv` (Python 3.12). Активация:

```powershell
.venv\Scripts\Activate.ps1
```

## Запуск

```powershell
flet run
```

В песочнице DSH перед запуском нужно подменить профиль, иначе Flet не сможет
писать свой кэш:

```powershell
$env:USERPROFILE = "$PWD\.flet\home"
flet run
```

Подробности — [docs/Environment.md](docs/Environment.md).

## Запуск на телефоне по USB

```powershell
# toolchain и список подключённых устройств
cmd /c "tools\run_on_device.cmd -SetupOnly"

# сборка, установка и запуск на смартфоне (ID устройства — из вывода выше)
cmd /c "tools\run_on_device.cmd -DeviceId <id>"

# то же, но остаться подключённым к телефону: логи и hot reload
cmd /c "tools\run_on_device.cmd -DeviceId <id> -Attach"
```

Нужны полный доступ (Flutter запускает adb, java и git через пайпы), свободный
индекс `pypi.flet.dev` и включённая на телефоне отладка по USB. Без `-Attach`
команда завершается сама после запуска приложения и печатает «Готово: …».
Подробности — [docs/Environment.md](docs/Environment.md), скилл агента —
[.agents/skills/run-on-device/SKILL.md](.agents/skills/run-on-device/SKILL.md).

## Тесты

```powershell
.venv\Scripts\python.exe -m pytest
```

261 тест. Тесты хранилища используют `tmp_path` и требуют полного доступа к
файловой системе — [docs/Environment.md](docs/Environment.md), «Ограничения
песочницы».

## Структура

Код — в `src`: точка входа `src/main.py`, интерфейс — пакет `src/ui`
(параметры, шаблоны контролов, виды, перетаскивание и экран), домен и хранилище —
`src/domain.py` и `src/storage.py`. Карта пакета — [src/ui/__init__.py](src/ui/__init__.py),
подробности — [docs/Project.md](docs/Project.md), «Структура проекта».
