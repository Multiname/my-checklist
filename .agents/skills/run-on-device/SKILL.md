---
name: run-on-device
description: Собрать Flet-приложение проекта, поставить его на Android-смартфон по USB и запустить (debug-APK через adb). Команда завершается сама после успешного запуска приложения — ожидать выхода не нужно.
---

# Запуск приложения на смартфоне по USB

Инструмент — `tools/run_on_device.cmd` (обёртка над `tools/run_on_device.ps1`, внутри `flet debug android`).
Он собирает debug-APK, ставит его на телефон через adb, запускает приложение
и **завершается сам** (код 0), как только приложение появилось на устройстве.
Wi-Fi и приложение Flet из Play Store не нужны: всё идёт по USB.

## Запуск

1. Телефон подключён кабелем (передающим данные), экран включён, в настройках
   разработчика включена «Отладка по USB», запрос «Разрешить отладку по USB?» подтверждён.
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

Скрипт сам завершается после запуска приложения: ждать окончания фоновой задачи
или читать логи до конца не нужно. Приложение на телефоне остаётся запущенным.

## Что делает скрипт

1. Перенаправляет профиль пользователя в `.flet\home` и переменные инструментов
   (`PUB_CACHE`, `GRADLE_USER_HOME`, `TEMP`, `JAVA_TOOL_OPTIONS`): Flet, Flutter, JDK,
   Android SDK и Gradle пишут в `Path.home()`, а писать в настоящий профиль нельзя.
2. При первом запуске разворачивает toolchain в `.flet\home`: Flutter SDK, JDK 17,
   Android SDK с platform-tools. Это несколько ГиБ и десятки минут, повторные запуски
   toolchain не трогают.
3. Проверяет SHA256 скачанных Flutter-архива и шаблона flet и приводит кэш
   шаблона к android-only: вырезает каталоги `windows/` и `linux/`, а также
   `RECORD_AUDIO` из debug/profile-манифестов, и ставит маркер
   `android-only-v2.marker` (иначе Flutter пытается создать симлинки для
   desktop-платформ и падает с `WinError 1314`, а приложение просит микрофон).
4. Патчит плагин `serious_python_android` в кэше pub: если архивы Python для Android
   уже скачаны в `.flet\home\.flet\cache\python-build`, сборка не ходит за ними на GitHub
   (иначе ETag-запрос к GitHub может упасть с `502 Bad Gateway` и сломать сборку).
5. Запускает adb-сервер, ждёт устройство в состоянии `device` (до `-WaitSeconds`,
   по умолчанию 180 с) и выбирает его.
6. Запускает `flet debug android` → `flutter run --no-resident`: упаковка Python-кода,
   сборка Gradle, установка APK, запуск на телефоне. После запуска `flutter run` выходит.
7. Проверяет по `adb shell pidof`, что процесс приложения жив (до `-VerifySeconds`,
   по умолчанию 60 с), и печатает итог.

`INTERNET` и `RECORD_AUDIO` выключены в `[tool.flet.android.permission]`
(`pyproject.toml`): в release-манифесте их нет. Debug-сборка оставляет
`INTERNET` из debug-манифеста Flutter — он нужен для hot reload.

## Признак успеха

В логе есть `√ Built build\app\outputs\flutter-apk\app-debug.apk`,
`Installing ... app-debug.apk...`, `Syncing files to device <модель>`, а последние строки:

```
Готово: com.blackline.my_checklist собран, установлен и запущен на <id> (pid <N>).
Приложение можно закрыть: adb shell am force-stop com.blackline.my_checklist
```

Код возврата — 0. На телефоне открыто приложение «My checklist».

Пакет приложения — `com.blackline.my_checklist` (организация `org` и название
`product` в `[tool.flet]`). Первый запуск с нуля идёт около
40 минут (toolchain + `assembleDebug` с NDK и CMake); при готовом toolchain —
30–40 секунд (инкрементальная сборка ~16 с, установка ~8 с).

## Повторная проверка без пересборки

Если код не менялся, сборку можно не запускать: APK уже стоит на телефоне.

```powershell
& .flet\home\Android\sdk\platform-tools\adb.exe shell am start -W -n com.blackline.my_checklist/.MainActivity
& .flet\home\Android\sdk\platform-tools\adb.exe shell pidof com.blackline.my_checklist
```

Запуск занимает меньше секунды, приложение отрисовывается через 3–5 с.
Закрыть приложение:

```powershell
& .flet\home\Android\sdk\platform-tools\adb.exe shell am force-stop com.blackline.my_checklist
```

## Режим с логами и hot reload

Если нужны логи приложения или hot reload, добавьте `-Attach`:

```powershell
cmd /c "tools\run_on_device.cmd -DeviceId <id> -Attach"
```

Тогда `flutter run` остаётся подключённым (`Syncing files to device`, `Flutter run key commands`),
в консоли работают `r` (hot reload), `R` (hot restart), `d` (detach), `q` (quit).
Такой процесс завершается только вручную (Ctrl+C или прервать фоновую задачу).
Если телефон заблокируется или экран погаснет, соединение отвалится
(`Lost connection to device`) и приложение будет закрыто — запустите команду заново
или поднимите приложение через `am start`.

## Параметры

| Параметр | Смысл |
|---|---|
| `-DeviceId <id>` | ID устройства из `adb devices`; обязателен при нескольких телефонах |
| `-SetupOnly` | только toolchain и список устройств, без сборки |
| `-Attach` | остаться подключённым к устройству: логи и hot reload |
| `-Release` | release-сборка вместо debug (дольше); подписывается ключом из `.secrets\key.properties`, без него сборка останавливается |
| `-WaitSeconds <n>` | сколько ждать устройство (по умолчанию 180) |
| `-VerifySeconds <n>` | сколько ждать запуска приложения после установки (по умолчанию 60) |
| остальные аргументы | передаются в `flet debug` (например `--route=/items`) |

## Что где лежит

| Путь | Содержимое |
|---|---|
| `.flet\home\flutter\<версия>` | Flutter SDK |
| `.flet\home\java\17.0.13+11` | JDK 17 |
| `.flet\home\Android\sdk` | Android SDK; adb — в `platform-tools\adb.exe` |
| `.flet\home\.gradle`, `.flet\home\.pub-cache` | кэши Gradle и pub |
| `.flet\home\.flet\cache\python-build` | архивы Python для Android (используются вместо GitHub) |
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
| `502 Bad Gateway` на `github.com/flet-dev/python-build/...` | GitHub временно отвечает ошибкой. Если архивы уже в `.flet\home\.flet\cache\python-build`, скрипт берёт их оттуда; иначе нужен доступ к GitHub — повторить позже |
| `SHA256 не совпал` | Скачанный Flutter-архив или шаблон flet повреждён/подменён; скрипт удаляет файл и предлагает повторить. Проверить сеть/прокси и запустить снова |
| `Нет эталонного SHA256 для ...` | Обновился flet/Flutter. Добавить новую версию и её SHA256 в `$FlutterSha256`/`$FletTemplateSha256` в `tools\run_on_device.ps1` |
| `No matching distribution found for msgpack...` | Недоступен индекс колёс Flet `https://pypi.flet.dev` (нужен VPN/прокси); без него APK не собрать |
| `CreateFile failed 5` / `Access denied` при запуске | Скрипт запущен без полного доступа (danger-full-access) |
| `Lost connection to device` | Телефон заблокировался или экран погас (в режиме `-Attach`); приложение при этом закрывается — запустить снова |
| `процесс ... не появился за 60 с` | APK собрался и установился, но приложение упало при старте: смотреть `adb logcat` |
| Сборка падает на непонятной ошибке Gradle | Удалить `build\` и запустить снова; при необходимости `flutter clean` через `.flet\home\flutter\<версия>\bin\flutter.bat` |
| `UnicodeEncodeError: 'charmap' codec` в выводе flet | Не выставлен `PYTHONIOENCODING=utf-8`; запускайте только через `tools\run_on_device.cmd`, а не `flet.exe` напрямую |
