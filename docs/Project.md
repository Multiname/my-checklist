# Project.md

## Структура проекта
| Путь | Назначение |
|---|---|
| `pyproject.toml` | метаданные проекта, зависимости, настройки pytest и Flet |
| `src/main.py` | точка входа приложения (`ft.run(main)`); каталог приложения задан в `[tool.flet.app] path = "src"` |
| `tests/` | тесты (`pytest`, `pythonpath = ["src"]`) |
| `tools/run_on_device.ps1` | запуск приложения на телефоне по USB: toolchain, adb, `flet debug android` |
| `tools/run_on_device.cmd` | обёртка для обхода политики запуска сценариев PowerShell |
| `.agents/skills/run-on-device/SKILL.md` | скилл агента: как запускать приложение на телефоне |
| `docs/` | документация проекта |
| `README.md` | краткое описание и команды запуска |

Сейчас приложение показывает только заглушку «Чеклист» — экран будет заменён
на этапе 2.

`org = "com.example"` в `[tool.flet]` — заглушка для Android-идентификатора
приложения; её нужно заменить до сборки APK.

## Команды
- Запуск на десктопе (обычный терминал): `.venv\Scripts\flet.exe run` из корня проекта
- Тесты: `.venv\Scripts\python.exe -m pytest`

### Запуск внутри песочницы DSH
Программы, запускаемые из папки проекта, не могут писать в профиль пользователя,
а Flet кэширует десктопный клиент в `~/.flet`. Поэтому профиль подменяется
на каталог проекта:

```powershell
$env:USERPROFILE = "$PWD\.flet\home"
.venv\Scripts\flet.exe run
```

Первый такой запуск скачивает клиент Flet (~100 МБ) в `.flet/home`; каталог
`.flet/` в git не попадает. Проверено: окно приложения открывается.

## Запуск на смартфоне по USB

Инструмент — `tools\run_on_device.cmd` (обёртка над `tools\run_on_device.ps1`),
внутри — `flet debug android`: сборка debug-APK, установка на телефон через adb
и запуск. Wi-Fi и приложение Flet из Play Store не нужны.

```powershell
# toolchain и список подключённых устройств
cmd /c "tools\run_on_device.cmd -SetupOnly"

# сборка и запуск (ID устройства — из вывода выше)
cmd /c "tools\run_on_device.cmd -DeviceId 3B161E00W5600000"
```

Запускать нужно с полным доступом (`danger-full-access`): Flutter и Gradle
создают дочерние процессы (adb, java, git) с пайпами, а ограниченная песочница
это запрещает — сборка падает с `CreateFile failed 5` или
`ProcessException: Отказано в доступе`.

Проверено на CPH2747 (Android 16, arm64-v8a): первый запуск с нуля — около
40 минут (≈10 минут toolchain и ≈27 минут `assembleDebug`: NDK, CMake и
недостающие пакеты SDK доезжают в процессе). Пакет приложения —
`com.example.my_checklist` (из заглушки `org = "com.example"`; её надо заменить
до сборки релизного APK).

Процесс не завершается: `flutter run` остаётся подключённым к телефону и печатает
его логи. Остановка — прервать процесс; приложение на телефоне закрывается через
`adb shell am force-stop <package>`.

### Toolchain
Первый запуск разворачивает всё в `.flet\home` (а не в профиль пользователя —
туда песочница писать не даёт):

| Компонент | Путь | Версия |
|---|---|---|
| Flutter SDK | `.flet\home\flutter\3.47.9` | 3.47.9 (пин из flet) |
| JDK | `.flet\home\java\17.0.13+11` | 17.0.13 |
| Android SDK | `.flet\home\Android\sdk` | platform-tools, platforms;android-34/35/36, build-tools;34.0.0 и 35.0.0, CMake 3.22.1, NDK 28.2 (недостающие пакеты доставляет Gradle при первой сборке) |
| Кэши | `.flet\home\.gradle`, `.flet\home\.pub-cache` | — |

Особенности окружения, без которых сборка не идёт:

- **Flutter ставится не flet, а скриптом.** Встроенный распаковщик flet
  (Python `zipfile`) падает на архиве Flutter: в нём есть файлы, которые вместе
  с каталогом проекта дают 262 символа, а Windows ограничивает путь 260.
  Скрипт качает архив `curl.exe` и распаковывает `tar.exe` (длинные пути умеет),
  после чего flet находит SDK на месте и не переустанавливает его.
- **`JAVA_TOOL_OPTIONS=-Duser.home=<.flet\home>`.** JVM берёт `user.home` из
  профиля Windows, а не из `USERPROFILE`, поэтому без этого `sdkmanager` пишет
  в `C:\Users\<user>\.android` и не может скачать даже списки пакетов.
- **`PYTHONIOENCODING=utf-8`.** Иначе flet падает с `UnicodeEncodeError:
  'charmap' codec` на первом же выводе pip (консоль здесь cp1251).
- **Шаблон Flutter-проекта чистится от desktop-платформ.** В шаблоне
  `flet-build-template` есть `windows/` и `linux/`; Flutter создаёт для них
  симлинки на плагины, а окружение агента их создавать не может
  (`WinError 1314`; «Режим разработчика» Windows не помогает — процесс работает
  с пониженными правами). Проект Android-only, поэтому скрипт один раз вырезает
  эти каталоги из кэша шаблона
  (`.flet\home\.flet\cache\build-template\v1.1.2`) и ставит рядом маркер
  `android-only.marker`.

### Сеть
Для сборки нужен доступ к индексу колёс Flet `https://pypi.flet.dev`: для Android
единственная нативная зависимость Flet — `msgpack`, её Android-колесо есть только
там. Без VPN/прокси pip падает с `No matching distribution found for
msgpack>=1.1.0`.

### Артефакты сборки
| Путь | Что это |
|---|---|
| `build\flutter` | сгенерированный Flutter-проект |
| `build\flutter\build\app\outputs\flutter-apk\app-debug.apk` | собранный debug-APK (в логе путь печатается относительно `build\flutter`) |
| `build\python-app`, `build\site-packages\<abi>` | упакованный Python-код приложения и зависимости по ABI |

`build\` и `.flet\` в git не попадают.

## Репозиторий
- GitHub: <https://github.com/Multiname/my-checklist>, ветка `main`
- Первый коммит: `7fb36cf` «Первый коммит: каркас проекта Flet»

## Окружение разработки

### Python
- Версия: **3.12.16** (пин из [Stack.md](Stack.md))
- Системный Python 3.12 на машине отсутствовал, поэтому интерпретатор установлен
  переносимым в `.python/3.12` — сборка python-build-standalone
  (`cpython-3.12.16+20261110-x86_64-pc-windows-msvc-install_only`).
  `.python/` в git не попадает.
- Запуск Python: `.venv\Scripts\python.exe`

### Виртуальное окружение
- `.venv` создан из `.python/3.12\python.exe`
- Активация: `.venv\Scripts\Activate.ps1`
- Все команды проекта (`python`, `pip`, `pytest`, `flet`) выполняются из `.venv`

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

### Ограничения песочницы DSH (Windows)
В ограниченном режиме (workspace-write) каталоги, созданные с правами `0700`
(`tempfile.mkdtemp`, `Path.mkdir(mode=0o700)` внутри pytest), становятся
недоступны процессу. С полным доступом нужно выполнять:
- установку и обновление пакетов через pip;
- тесты, использующие `tmp_path` (простые тесты без временных каталогов
  проходят и в ограниченном режиме).

Отдельное ограничение действует даже при полном доступе: программы, запускаемые
из папки проекта (`.venv\Scripts\python.exe`, `.python\3.12\python.exe`),
не могут писать в профиль пользователя `C:\Users\MineF`. Поэтому `flet run`
запускается с подменённым `USERPROFILE` (см. «Команды»), а запуск на телефоне
подменяет все каталоги инструментов — см. «Запуск на смартфоне по USB».

Сборка под Android требует полного доступа и по другой причине: в ограниченном
режиме Dart (движок Flutter) не может запускать дочерние процессы через пайпы —
`git`, `java`, `adb` падают с `CreateFile failed 5` и
`ProcessException: Отказано в доступе`.

Из-за ограничения с `0700` в `pyproject.toml` отключён кэш pytest
(`addopts = "-p no:cacheprovider"`): иначе каждый запуск создаёт в корне
недоступные каталоги `pytest-cache-files-*`. Тесты без `tmp_path` идут
в обычном режиме.

### Git в песочнице DSH
- Штатный TLS-бэкенд git (schannel) в песочнице падает с
  `SEC_E_NO_CREDENTIALS`, поэтому в локальном конфиге репозитория выставлен
  `http.sslBackend=openssl` (в git не коммитится).
- `git push` требует полного доступа: git-credential-manager не работает,
  пока песочница запрещает pipes.
