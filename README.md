# Мобильный чеклист

Приложение для ведения списка чекбоксов. Только Android.

## Документация

- [docs/README.md](docs/README.md) — точка входа в документацию
- [docs/Project.md](docs/Project.md) — окружение и детали реализации

## Окружение

Окружение уже создано: `.venv` (Python 3.12). Активация:

```powershell
.venv\Scripts\Activate.ps1
```

## Запуск

```powershell
flet run
```

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
Подробности — [docs/Project.md](docs/Project.md), скилл агента —
[.agents/skills/run-on-device/SKILL.md](.agents/skills/run-on-device/SKILL.md).

## Тесты

```powershell
python -m pytest
```
