---
name: run-on-device
description: Собрать Flet-приложение проекта и запустить его на Android-смартфоне, подключённом по USB (debug-APK через adb), чтобы проверить текущую версию на живом устройстве.
---

# Запуск приложения на смартфоне по USB

Инструмент — `tools/run_on_device.cmd` (обёртка над `tools/run_on_device.ps1`, внутри `flet debug android`).
Он собирает debug-APK, ставит его на телефон через adb и запускает приложение.
Wi-Fi и приложение Flet из Play Store не нужны: всё идёт по USB.

## Запуск

1. Телефон подключён кабелем (передающим данные), в настройках разработчика включена
   «Отладка по USB», запрос «Разрешить отладку по USB?» подтверждён.
2. Выполните из корня проекта — **обязательно с полным доступом** (`danger-full-access`):

```powershell
cmd /c "tools\run_on_device.cmd -DeviceId <id>"
```

Полный доступ нужен потому, что Flutter и Gradle запускают дочерние процессы (adb, java, git)
через пайпы, а ограниченная песочница Windows запрещает их создание: сборка падает с
`CreateFile failed 5` или `ProcessException: Отказано в доступе`.

3. Если ID устройства неизвестен или подключено несколько телефонов:

```powershell
cmd /c "tools\run_on_device.cmd -SetupOnly"
```

Команда разворачивает toolchain (если его ещё нет) и печатает `adb devices -l`.
Если подключён ровно один телефон, `-DeviceId` можно не указывать.

## Что делает скрипт

1. Перенаправляет профиль пользователя в `.flet\home` и переменные инструментов
   (`PUB_CACHE`, `GRADLE_USER_HOME`, `TEMP`, `JAVA_TOOL_OPTIONS`): Flet, Flutter, JDK,
   Android SDK и Gradle пишут в `Path.home()`, а писать в настоящий профиль нельзя.
2. При первом запуске разворачивает toolchain в `.flet\home`: Flutter SDK, JDK 17,
   Android SDK с platform-tools. Это несколько ГиБ и десятки минут, повторные запуски
   toolchain не трогают.
3. Приводит кэш шаблона Flutter-проекта к android-only: вырезает из него каталоги
   `windows/` и `linux/` и ставит маркер `android-only.marker` (иначе Flutter пытается
   создать для них симлинки и падает с `WinError 1314`).
4. Запускает adb-сервер, ждёт устройство в состоянии `device` (до `-WaitSeconds`,
   по умолчанию 180 с) и выбирает его.
5. Запускает `flet debug android`: упаковка Python-кода, `flutter run` — сборка Gradle,
   установка APK, запуск на телефоне.

## Признак успеха

В логе появляются `√ Built build\app\outputs\flutter-apk\app-debug.apk`,
`Installing ... app-debug.apk...`, затем:

```
Syncing files to device <модель>

Flutter run key commands.
```

и телефон открывает приложение («Чеклист»). Процесс после этого не завершается —
он остаётся подключённым к устройству (`flutter run`) и печатает логи приложения.

Пакет приложения — `com.example.my_checklist`. Первый запуск с нуля идёт около
40 минут (toolchain + `assembleDebug` с NDK и CMake), последующие — заметно
быстрее.

## Остановка

Прервите фоновую задачу (или Ctrl+C). Приложение на телефоне при этом остаётся
запущенным — это проверено; чтобы закрыть его:

```powershell
& .flet\home\Android\sdk\platform-tools\adb.exe shell am force-stop com.example.my_checklist
```

## Параметры

| Параметр | Смысл |
|---|---|
| `-DeviceId <id>` | ID устройства из `adb devices`; обязателен при нескольких телефонах |
| `-SetupOnly` | только toolchain и список устройств, без сборки |
| `-Release` | release-сборка вместо debug (дольше) |
| `-WaitSeconds <n>` | сколько ждать устройство (по умолчанию 180) |
| остальные аргументы | передаются в `flet debug` (например `--route=/items`) |

## Что где лежит

| Путь | Содержимое |
|---|---|
| `.flet\home\flutter\<версия>` | Flutter SDK |
| `.flet\home\java\17.0.13+11` | JDK 17 |
| `.flet\home\Android\sdk` | Android SDK; adb — в `platform-tools\adb.exe` |
| `.flet\home\.gradle`, `.flet\home\.pub-cache` | кэши Gradle и pub |
| `build\flutter` | сгенерированный Flutter-проект |
| `build\flutter\build\app\outputs\flutter-apk\app-debug.apk` | собранный debug-APK (в логе путь печатается от `build\flutter`, т.е. как `build\app\outputs\flutter-apk\app-debug.apk`) |
| `.flet\tmp` | временные файлы (TEMP/TMP) |

`.flet\` и `build\` в git не попадают. Удалять `.flet\home` можно, но тогда toolchain
скачается заново.

## Типовые ошибки

| Симптом | Причина и что делать |
|---|---|
| `Устройство не найдено` | Кабель/отладка: включить «Отладку по USB», подтвердить запрос на телефоне, проверить `adb devices` |
| `Телефон виден, но отладка по USB не авторизована` | Разблокировать телефон и нажать «Разрешить» в запросе |
| `Building with plugins requires symlink support` / `WinError 1314` | В шаблоне Flutter-проекта вернулись каталоги `windows`/`linux` (например, после обновления flet). Удалить `.flet\home\.flet\cache\build-template` и повторить запуск — скрипт снова сделает шаблон android-only. «Режим разработчика» Windows здесь не помогает: процесс работает с пониженными правами |
| `No matching distribution found for msgpack...` | Недоступен индекс колёс Flet `https://pypi.flet.dev` (нужен VPN/прокси); без него APK не собрать |
| `CreateFile failed 5` / `Access denied` при запуске | Скрипт запущен без полного доступа (danger-full-access) |
| Сборка падает на непонятной ошибке Gradle | Удалить `build\` и запустить снова; при необходимости `flutter clean` через `.flet\home\flutter\<версия>\bin\flutter.bat` |
| `UnicodeEncodeError: 'charmap' codec` в выводе flet | Не выставлен `PYTHONIOENCODING=utf-8`; запускайте только через `tools\run_on_device.cmd`, а не `flet.exe` напрямую |
