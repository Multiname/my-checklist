# Environment.md

Окружение разработки, сборка и ограничения песочницы. Стек и версии — в
[Stack.md](Stack.md), запуск приложения на телефоне — в
[.agents/skills/run-on-device/SKILL.md](../.agents/skills/run-on-device/SKILL.md).

## Python и виртуальное окружение
- Версия: **3.12.16** (пин из [Stack.md](Stack.md)).
- Системный Python 3.12 на машине отсутствовал, поэтому интерпретатор установлен
  переносимым в `.python/3.12` — сборка python-build-standalone
  (`cpython-3.12.16+20261110-x86_64-pc-windows-msvc-install_only`).
  `.python/` в git не попадает.
- `.venv` создан из `.python/3.12\python.exe`; активация —
  `.venv\Scripts\Activate.ps1`. Все команды проекта (`python`, `pip`, `pytest`,
  `flet`) выполняются из `.venv`.

### Установленные зависимости
| Пакет | Версия | Назначение |
|---|---|---|
| flet | 1.1.2 | UI-фреймворк (Flutter-рендер) |
| flet-cli | 1.1.2 | команды `flet run`, `flet build` |
| flet-desktop | 1.1.2 | десктопный клиент для `flet run` |
| pytest | 9.2.0 | тесты доменной логики и слоя хранения |

`flet-cli` и `flet-desktop` установлены явно: пакет `flet` не тянет их
зависимостями, а `flet.exe` при первом запуске сам доустанавливает `flet-cli`,
что в ограниченном режиме песочницы падает.

## Запуск на десктопе
Из корня проекта: `.venv\Scripts\flet.exe run`.

### В песочнице DSH
Программы, запускаемые из папки проекта, не могут писать в профиль пользователя,
а Flet кэширует десктопный клиент в `~/.flet`. Поэтому профиль подменяется на
каталог проекта:

```powershell
$env:USERPROFILE = "$PWD\.flet\home"
.venv\Scripts\flet.exe run
```

Первый такой запуск скачивает клиент Flet (~100 МБ) в `.flet/home`; каталог
`.flet/` в git не попадает. Проверено: окно приложения открывается, создание
категории сохраняется в `.flet/storage/data/app.db` и восстанавливается при
следующем запуске. Этот файл — dev-данные, его можно удалить.

`flet run` останавливается не сразу: после `Stop-Process flet` дочерние
`python.exe` ещё держат `app.db` и pid-файлы в корне проекта. Пока они живы, файл
удалить нельзя; процессы ищутся по пути `.venv\Scripts\python.exe` /
`.python\3.12\python.exe` от корня проекта.

## Сборка под Android
Первый запуск `tools\run_on_device.cmd` разворачивает toolchain в `.flet\home`
(Flutter SDK, JDK 17, Android SDK с platform-tools и кэши Gradle/pub) — это
несколько ГиБ и десятки минут; повторные запуски toolchain не трогают. Что где
лежит, какие параметры есть у скрипта и что делать при типовых ошибках — скилл
[run-on-device](../.agents/skills/run-on-device/SKILL.md).

Артефакты сборки:

| Путь | Что это |
|---|---|
| `build\flutter` | сгенерированный Flutter-проект |
| `build\flutter\build\app\outputs\flutter-apk\app-debug.apk` | собранный debug-APK |
| `build\python-app`, `build\site-packages\<abi>` | упакованный Python-код приложения и зависимости по ABI |

`build\` и `.flet\` в git не попадают.

### Особенности окружения, без которых сборка не идёт
- **Flutter ставится не flet, а скриптом.** Встроенный распаковщик flet
  (Python `zipfile`) падает на архиве Flutter: в нём есть файлы, которые вместе
  с каталогом проекта дают 262 символа, а Windows ограничивает путь 260. Скрипт
  качает архив `curl.exe` и распаковывает `tar.exe`.
- **`JAVA_TOOL_OPTIONS=-Duser.home=<.flet\home>`.** JVM берёт `user.home` из
  профиля Windows, а не из `USERPROFILE`, поэтому без этого `sdkmanager` пишет
  в `C:\Users\<user>\.android` и не может скачать даже списки пакетов.
- **`PYTHONIOENCODING=utf-8`.** Иначе flet падает с `UnicodeEncodeError:
  'charmap' codec` на первом же выводе pip (консоль здесь cp1251).
- **Шаблон Flutter-проекта чистится от desktop-платформ и RECORD_AUDIO.**
  В шаблоне `flet-build-template` есть `windows/` и `linux/`; Flutter создаёт
  для них симлинки на плагины, а окружение агента их создавать не может
  (`WinError 1314`; «Режим разработчика» Windows не помогает — процесс работает
  с пониженными правами). В debug/profile-манифестах шаблона также объявлен
  `RECORD_AUDIO`; приложению микрофон не нужен, поэтому строка удаляется.
- **Артефакты toolchain проверяются по SHA256.** Flutter-архив и
  `flet-build-template.zip` сверяются с эталонами в `tools\run_on_device.ps1`
  (`$FlutterSha256`, `$FletTemplateSha256`). При обновлении flet нужно добавить
  туда новую версию; неизвестная версия — ошибка, а не скачивание без проверки.
- **Разрешения Android выключены в `pyproject.toml`.** В
  `[tool.flet.android.permission]` стоят `INTERNET = false` и
  `RECORD_AUDIO = false`; flet добавляет в main-манифест
  `tools:node="remove"`. В debug-сборке `INTERNET` остаётся из debug-манифеста
  Flutter для hot reload, в release его нет.
- **Архивы Python для Android берутся из локального кэша.** Плагин
  `serious_python_android` на каждой сборке делает ETag-запрос к GitHub и при
  ответе `502 Bad Gateway` валит сборку, хотя архивы уже лежат в
  `.flet\home\.flet\cache\python-build`. Скрипт идемпотентно патчит
  `build.gradle.kts` плагина: если файл скачан, задача пропускается.

### Сеть
Индекс колёс Flet `https://pypi.flet.dev` нужен при упаковке Python-кода
(`flet debug` вызывает pip): для Android единственная нативная зависимость Flet —
`msgpack`, её Android-колесо есть только там. Без VPN/прокси pip падает с
`No matching distribution found for msgpack>=1.1.0`. GitHub нужен за шаблоном
flet и архивами `python-build`, Google Storage — за Flutter; всё это только пока
соответствующих файлов нет в локальном кэше.

## Ограничения песочницы DSH (Windows)
В ограниченном режиме (workspace-write) каталоги, созданные с правами `0700`
(`tempfile.mkdtemp`, `Path.mkdir(mode=0o700)` внутри pytest), становятся
недоступны процессу. С полным доступом нужно выполнять:
- установку и обновление пакетов через pip;
- тесты, использующие `tmp_path` (простые тесты без временных каталогов
  проходят и в ограниченном режиме).

Отдельное ограничение действует даже при полном доступе: программы, запускаемые
из папки проекта (`.venv\Scripts\python.exe`, `.python\3.12\python.exe`), не
могут писать в профиль пользователя `C:\Users\<user>`. Поэтому `flet run`
запускается с подменённым `USERPROFILE` (см. выше), а запуск на телефоне
подменяет все каталоги инструментов.

Сборка под Android требует полного доступа и по другой причине: в ограниченном
режиме Dart (движок Flutter) не может запускать дочерние процессы через пайпы —
`git`, `java`, `adb` падают с `CreateFile failed 5` и
`ProcessException: Отказано в доступе`.

Из-за ограничения с `0700` в `pyproject.toml` отключён кэш pytest
(`addopts = "-p no:cacheprovider"`): иначе каждый запуск создаёт в корне
недоступные каталоги `pytest-cache-files-*`. Тесты без `tmp_path` идут
в обычном режиме.

Тесты хранилища используют `tmp_path`, поэтому запускаются только с полным
доступом. Их временный каталог (`pytest-of-*`) может появиться в корне проекта
с правами `0700` — после прогона его нужно удалить тоже с полным доступом.
Чтобы он не появлялся в корне, можно задать `TEMP`/`TMP` внутри `.tmp/`:

```powershell
$env:TEMP = "$PWD\.tmp\pytest"; $env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
.venv\Scripts\python.exe -m pytest
```

### Запись в `docs/` из команд
Дочерним процессам (Python, PowerShell) каталог `docs/` недоступен на запись:
в его правах нет записи, которую песочница выдаёт рабочему каталогу. Создание и
правка файлов в `docs/` работают через файловые инструменты агента (write/edit),
а скрипт, который генерирует документацию, должен писать результат в `.tmp/` и
переноситься в `docs/` этими инструментами. Корень проекта и `.tmp/` доступны
на запись обычным образом.

## Git
- Штатный TLS-бэкенд git (schannel) в песочнице падает с
  `SEC_E_NO_CREDENTIALS`, поэтому в локальном конфиге репозитория выставлен
  `http.sslBackend=openssl` (в git не коммитится).
- `git push` требует полного доступа: git-credential-manager не работает,
  пока песочница запрещает pipes.
- Репозиторий: <https://github.com/Multiname/my-checklist>, ветка `main`.
  Первый коммит: `7fb36cf` «Первый коммит: каркас проекта Flet».
