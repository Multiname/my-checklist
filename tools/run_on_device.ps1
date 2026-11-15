#Requires -Version 5.1
<#
.SYNOPSIS
    Запуск приложения на Android-смартфоне, подключённом по USB.

.DESCRIPTION
    Обёртка над `flet debug android`: flet собирает debug-APK, flutter через adb
    ставит его на устройство и запускает. Wi-Fi и приложение Flet из Play Store
    не нужны — всё идёт по USB.

    Скрипт делает то, чего не делает `flet debug`:

    1. Перенаправляет каталоги профиля пользователя в `.flet\home`. Flet,
       Flutter, JDK, Android SDK и Gradle пишут в `Path.home()`, а в песочнице
       DSH запись в настоящий профиль (`C:\Users\<user>`) запрещена.
    2. При первом запуске разворачивает toolchain: Flutter SDK, JDK 17,
       Android SDK с platform-tools (adb). Это несколько ГБ и десятки минут;
       повторные запуски toolchain не трогают.
       Flutter ставится вручную (`tar` вместо распаковщика flet): встроенный
       распаковщик падает на архиве Flutter, потому что путь получается длиннее
       ограничения Windows в 260 символов (см. docs\Project.md).
    3. Ждёт, пока устройство появится в `adb devices` в состоянии `device`
       (то есть отладка по USB разрешена на телефоне), и выбирает его.

    Если подключено несколько телефонов, нужный указывается через -DeviceId
    (ID берётся из `-SetupOnly`).

.PARAMETER DeviceId
    Идентификатор устройства из `adb devices` (например `RF8M123ABCD`).
    Если не указан и подключено ровно одно устройство — берётся оно.

.PARAMETER Release
    Собрать и запустить release-сборку вместо debug.

.PARAMETER SetupOnly
    Только подготовить toolchain и показать подключённые устройства.
    Ничего не собирает и не запускает.

.PARAMETER WaitSeconds
    Сколько секунд ждать появления авторизованного устройства (по умолчанию 180).

.PARAMETER Attach
    Оставить процесс подключённым к устройству (`flutter run`): логи и hot reload
    (`r`/`R`). По умолчанию скрипт завершается сразу после успешного запуска
    приложения и выходит с кодом 0.

.PARAMETER VerifySeconds
    Сколько секунд ждать появления процесса приложения на телефоне после
    завершения `flet debug` (по умолчанию 60).

.PARAMETER ExtraArgs
    Дополнительные аргументы `flet debug`, например `--route=/items`.

.EXAMPLE
    .\tools\run_on_device.ps1 -SetupOnly

.EXAMPLE
    .\tools\run_on_device.ps1

.EXAMPLE
    .\tools\run_on_device.ps1 -DeviceId RF8M123ABCD -Release

.EXAMPLE
    .\tools\run_on_device.ps1 -DeviceId RF8M123ABCD -Attach

.NOTES
    По умолчанию `flutter run` запускается с `--no-resident`: скрипт собирает APK,
    ставит его на телефон, дожидается запуска приложения (проверка по `pidof`)
    и завершается. Приложение на телефоне остаётся запущенным.

    С -Attach процесс остаётся подключённым к устройству (логи, hot reload);
    тогда завершать его нужно вручную (Ctrl+C или прервать фоновую задачу).
#>
[CmdletBinding()]
param(
    [string]$DeviceId,
    [switch]$Release,
    [switch]$SetupOnly,
    [switch]$Attach,
    [int]$WaitSeconds = 180,
    [int]$VerifySeconds = 60,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$FletExe = Join-Path $Root '.venv\Scripts\flet.exe'
$FletHome = Join-Path $Root '.flet\home'
$SdkDir = Join-Path $FletHome 'Android\sdk'
$AdbExe = Join-Path $SdkDir 'platform-tools\adb.exe'
$TmpDir = Join-Path $Root '.flet\tmp'

# Эталонные SHA256 скачиваемых артефактов toolchain. Версия Flutter берётся из
# flet, поэтому при обновлении flet нужно добавить сюда новую версию:
#   Flutter  — поле sha256 в releases_windows.json (storage.googleapis.com);
#   шаблон   — digest ассета flet-build-template.zip в GitHub Release.
# Неизвестная версия — ошибка, а не скачивание без проверки.
$FlutterSha256 = @{
    '3.47.9' = 'd8e2b5977e09082c6440f89dc1aa887b94c8fbcc3b39222797046295a3f68a9e'
}
$FletTemplateSha256 = @{
    '1.1.2' = 'ccd6ecabc2afbe14343be3bc51bb4b012672add25e0378be18758f9ddd4ca643'
}

function Test-FileSha256 {
    <#
    .SYNOPSIS
        Проверяет SHA256 файла без удаления при несовпадении.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    return $actual.Equals($Expected, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-FileSha256 {
    <#
    .SYNOPSIS
        Проверяет SHA256 и удаляет файл при несовпадении.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Label
    )
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if (-not $actual.Equals($Expected, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        throw "$Label`: SHA256 не совпал. Ожидался $Expected, получен $actual. Файл удалён."
    }
    return $actual
}

function Initialize-Environment {
    <#
    .SYNOPSIS
        Перенаправляет профиль пользователя и кэши инструментов в `.flet\`.
    #>
    $dirs = @(
        $FletHome,
        (Join-Path $FletHome 'appdata\roaming'),
        (Join-Path $FletHome 'appdata\local'),
        (Join-Path $FletHome '.pub-cache'),
        (Join-Path $FletHome '.gradle'),
        $TmpDir
    )
    foreach ($dir in $dirs) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }

    # Path.home() в Python/Dart/Flutter берётся отсюда, поэтому Flutter SDK
    # (~/flutter), JDK (~/java) и Android SDK (~/Android/sdk) попадают в проект.
    $env:USERPROFILE = $FletHome
    $env:HOME = $FletHome
    $env:APPDATA = Join-Path $FletHome 'appdata\roaming'
    $env:LOCALAPPDATA = Join-Path $FletHome 'appdata\local'
    $env:TEMP = $TmpDir
    $env:TMP = $TmpDir
    $env:TMPDIR = $TmpDir
    $env:PUB_CACHE = Join-Path $FletHome '.pub-cache'
    $env:GRADLE_USER_HOME = Join-Path $FletHome '.gradle'

    # JVM берёт user.home не из USERPROFILE, а из профиля Windows, поэтому без
    # этой строки sdkmanager и Gradle пишут в C:\Users\<user> (песочница
    # запрещает запись, а sdkmanager вообще перестаёт качать списки пакетов).
    if (-not $env:JAVA_TOOL_OPTIONS) {
        $env:JAVA_TOOL_OPTIONS = if ($FletHome -match '\s') {
            "-Duser.home=`"$FletHome`""
        } else {
            "-Duser.home=$FletHome"
        }
    }

    if (Test-Path $SdkDir) {
        $env:ANDROID_HOME = $SdkDir
        $env:ANDROID_SDK_ROOT = $SdkDir
    }

    # Вывод flet/pip идёт в консоль с кодировкой cp1251; flet печатает рамки и
    # эмодзи, и на них падает с UnicodeEncodeError, так и не начав сборку.
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8 = '1'
    # Сеть до pypi.flet.dev нестабильна: pip должен пережить таймауты.
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PIP_RETRIES = '10'
    $env:PIP_DEFAULT_TIMEOUT = '60'
}

function Initialize-ReleaseSigning {
    <#
    .SYNOPSIS
        Подставляет ключ подписи release-сборки из `.secrets\key.properties`.

    .DESCRIPTION
        Release-сборка, которую отдают пользователям, не должна подписываться
        отладочным ключом Android. flet читает параметры подписи из переменных
        окружения `FLET_ANDROID_SIGNING_KEY_*`; здесь они берутся из локального
        файла `.secrets\key.properties` (каталог в git не попадает).

        Путь `storeFile` в этом файле может быть относительным — он считается
        от корня проекта. Если ключа нет, release-сборка останавливается: молча
        подписать её debug-ключом хуже, чем не собрать.
    #>
    if (-not $Release) {
        return
    }
    if ($env:FLET_ANDROID_SIGNING_KEY_STORE) {
        return
    }

    $propsFile = Join-Path $Root '.secrets\key.properties'
    if (-not (Test-Path -LiteralPath $propsFile)) {
        throw "Для release-сборки нет ключа подписи: $propsFile. Создайте release-keystore и key.properties (см. docs\Environment.md, «Подпись release-сборки»)."
    }

    $props = @{}
    foreach ($line in Get-Content -LiteralPath $propsFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        $separator = $trimmed.IndexOf('=')
        if ($separator -lt 1) {
            continue
        }
        $props[$trimmed.Substring(0, $separator).Trim()] = $trimmed.Substring($separator + 1).Trim()
    }

    foreach ($name in @('storeFile', 'keyAlias', 'storePassword', 'keyPassword')) {
        if (-not $props[$name]) {
            throw "В $propsFile нет поля $name."
        }
    }

    $store = $props['storeFile']
    if (-not [System.IO.Path]::IsPathRooted($store)) {
        $store = Join-Path $Root $store
    }
    $store = [System.IO.Path]::GetFullPath($store)
    if (-not (Test-Path -LiteralPath $store)) {
        throw "Ключ подписи не найден: $store (поле storeFile в $propsFile)."
    }

    $env:FLET_ANDROID_SIGNING_KEY_STORE = $store
    $env:FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD = $props['storePassword']
    $env:FLET_ANDROID_SIGNING_KEY_PASSWORD = $props['keyPassword']
    $env:FLET_ANDROID_SIGNING_KEY_ALIAS = $props['keyAlias']
    Write-Host "Release подписывается ключом: $store (alias $($props['keyAlias']))" -ForegroundColor Cyan
}

function Get-RequiredFlutterVersion {
    <#
    .SYNOPSIS
        Возвращает версию Flutter, с которой собран установленный flet.
    #>
    $version = & $VenvPython -c 'import flet.version; print(flet.version.flutter_version)' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось определить версию Flutter из flet: $version"
    }
    return ($version | Out-String).Trim()
}

function Install-FlutterSdk {
    <#
    .SYNOPSIS
        Ставит Flutter SDK в `.flet\home\flutter\<version>`.

    .DESCRIPTION
        flet ставит Flutter сам, но его распаковщик (Python zipfile) не умеет
        пути длиннее MAX_PATH: в архиве Flutter есть файлы, которые вместе с
        каталогом проекта дают 262 символа. Поэтому архив качается curl'ом,
        распаковывается `tar` (он длинные пути поддерживает) и переносится
        на место, где flet его ищет.
    #>
    param([Parameter(Mandatory)][string]$Version)

    $sdkDir = Join-Path $FletHome "flutter\$Version"
    $flutterBat = Join-Path $sdkDir 'bin\flutter.bat'
    if (Test-Path $flutterBat) {
        return $sdkDir
    }

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if (-not $curl -or -not $tar) {
        throw 'Нужны curl.exe и tar.exe (есть в Windows 10 1803+): без них toolchain не поставить.'
    }

    $expected = $FlutterSha256[$Version]
    if (-not $expected) {
        throw "Нет эталонного SHA256 для Flutter $Version. Добавьте версию в `$FlutterSha256` в tools\run_on_device.ps1 (значение — из releases_windows.json)."
    }

    $url = "https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_$Version-stable.zip"
    $archive = Join-Path $FletHome "flutter_windows_$Version-stable.zip"
    $staging = Join-Path $TmpDir 'flutter_extract'

    if ((Test-Path $archive) -and -not (Test-FileSha256 -Path $archive -Expected $expected)) {
        Write-Warning "Архив Flutter не совпал с эталонным SHA256 — скачиваю заново."
        Remove-Item -LiteralPath $archive -Force
    }

    if (-not (Test-Path $archive)) {
        # Скачиваем во временный файл: недокачанный архив не должен выглядеть
        # готовым при следующем запуске.
        $download = "$archive.part"
        Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
        Write-Host "Скачиваю Flutter $Version (~2 ГБ): $url" -ForegroundColor Cyan
        & $curl.Source -L --fail --show-error --output $download $url
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
            throw "Не удалось скачать Flutter ($LASTEXITCODE): $url"
        }
        Assert-FileSha256 -Path $download -Expected $expected -Label 'Flutter' | Out-Null
        Move-Item -LiteralPath $download -Destination $archive -Force
    }

    Write-Host 'Распаковываю Flutter...' -ForegroundColor Cyan
    Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    & $tar.Source -xf $archive -C $staging
    if ($LASTEXITCODE -ne 0) {
        throw "tar не смог распаковать $archive (код $LASTEXITCODE)"
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $sdkDir) | Out-Null
    Move-Item (Join-Path $staging 'flutter') $sdkDir
    Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
    Remove-Item -Force $archive -ErrorAction SilentlyContinue

    if (-not (Test-Path $flutterBat)) {
        throw "Flutter распакован, но $flutterBat не найден."
    }
    return $sdkDir
}

function Ensure-AndroidSdk {
    <#
    .SYNOPSIS
        Ставит JDK 17 и Android SDK (вместе с adb), если их ещё нет.
    #>
    if (Test-Path $AdbExe) {
        return
    }

    Write-Host 'Ставлю JDK 17 и Android SDK (adb, platform 35, build-tools)...' -ForegroundColor Cyan
    Push-Location $Root
    try {
        # `flet devices` — самый короткий путь, который заставляет flet
        # развернуть JDK и Android SDK в перенаправленный профиль.
        & $FletExe devices --yes --log-format plain
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0 -or -not (Test-Path $AdbExe)) {
        throw "Не удалось установить Android SDK (код $code). Ожидался adb: $AdbExe"
    }
}

function Repair-BuildTemplate {
    <#
    .SYNOPSIS
        Готовит шаблон Flutter-проекта: только Android, без RECORD_AUDIO.

    .DESCRIPTION
        Шаблон `flet-build-template` содержит каталоги `windows/` и `linux/`.
        Заметив их, Flutter при сборке создаёт симлинки на плагины, а окружение
        агента (пониженные права Windows) не может создавать симлинки:
        `Building with plugins requires symlink support` / `WinError 1314`.
        Проект Android-only, desktop-платформы не нужны, поэтому каталоги
        вырезаются из кэша шаблона до того, как flet развернёт из него
        Flutter-проект.

        В debug/profile-манифестах шаблона также лежит RECORD_AUDIO — он нужен
        шаблону, но не приложению, поэтому строка удаляется.

        Скачанный архив сверяется с эталонным SHA256. Оригинал хранится рядом
        (`flet-build-template.orig.zip`), а flet читает уже исправленную копию.
        Маркер `android-only-v2.marker` содержит SHA256 исправленного архива и
        позволяет не пересобирать кэш на каждом запуске.

        Каталог кэша совпадает с тем, что использует flet:
        `~/.flet/cache/build-template/v<версия>/` (здесь `~` — `.flet\home`).
    #>
    param([Parameter(Mandatory)][string]$FletVersion)

    $expected = $FletTemplateSha256[$FletVersion]
    if (-not $expected) {
        throw "Нет эталонного SHA256 для шаблона flet $FletVersion. Добавьте версию в `$FletTemplateSha256` в tools\run_on_device.ps1 (значение — digest ассета flet-build-template.zip)."
    }

    $cacheDir = Join-Path $FletHome ".flet\cache\build-template\v$FletVersion"
    $templateZip = Join-Path $cacheDir 'flet-build-template.zip'
    $originalZip = Join-Path $cacheDir 'flet-build-template.orig.zip'
    $backupZip = Join-Path $cacheDir 'flet-build-template.zip.bak'
    $marker = Join-Path $cacheDir 'android-only-v2.marker'

    if (Test-Path $marker) {
        $repairedHash = (Get-Content -Raw -Path $marker).Trim()
        if ((Test-Path $templateZip) -and (Test-FileSha256 -Path $templateZip -Expected $repairedHash)) {
            return
        }
        Write-Warning 'Кэш шаблона изменён или отсутствует — восстанавливаю из проверенного оригинала.'
        Remove-Item -LiteralPath $marker -Force
    }

    # Ищем уже проверенный оригинал: .orig после прошлого запуска, старый .bak
    # или нетронутый zip. Повреждённые/исправленные копии не подходят.
    $original = $null
    foreach ($candidate in @($originalZip, $backupZip, $templateZip)) {
        if (Test-FileSha256 -Path $candidate -Expected $expected) {
            $original = $candidate
            break
        }
    }

    if (-not $original) {
        $url = "https://github.com/flet-dev/flet/releases/download/v$FletVersion/flet-build-template.zip"
        $download = "$originalZip.part"
        New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
        Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
        Write-Host "Скачиваю шаблон Flutter-проекта: $url" -ForegroundColor Cyan
        & curl.exe -L --fail --show-error --output $download $url
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
            throw "Не удалось скачать шаблон ($LASTEXITCODE): $url"
        }
        Assert-FileSha256 -Path $download -Expected $expected -Label 'Шаблон flet' | Out-Null
        Move-Item -LiteralPath $download -Destination $originalZip -Force
        $original = $originalZip
    }

    if ($original -ne $originalZip) {
        Copy-Item -LiteralPath $original -Destination $originalZip -Force
    }
    Copy-Item -LiteralPath $originalZip -Destination $templateZip -Force

    $code = @'
import os, re, sys, zipfile

src = sys.argv[1]
tmp = src + '.tmp'
dropped = 0
audio = 0
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        name = item.filename
        if '/windows/' in name or '/linux/' in name:
            dropped += 1
            continue
        data = zin.read(name)
        if name.endswith('/AndroidManifest.xml'):
            text = data.decode('utf-8')
            # Шаблон добавляет RECORD_AUDIO только в debug/profile; в main его нет.
            new_text, removed = re.subn(
                r'(?m)^[ \t]*<uses-permission android:name="android\.permission\.RECORD_AUDIO" />[ \t]*\r?\n?',
                '',
                text,
            )
            if removed:
                audio += removed
                data = new_text.encode('utf-8')
            if 'RECORD_AUDIO' in new_text:
                raise SystemExit(f'RECORD_AUDIO остался в {name}')
        zout.writestr(item, data)
os.replace(tmp, src)
print(f'убрано desktop-файлов: {dropped}, RECORD_AUDIO: {audio}')
'@
    # Код передаётся файлом, а не через `-c`: в нём есть двойные кавычки, и
    # командная строка Windows PowerShell искажает их при передаче аргумента.
    $patchScript = Join-Path $TmpDir 'patch_flet_template.py'
    [System.IO.File]::WriteAllText($patchScript, $code, (New-Object System.Text.UTF8Encoding($false)))
    & $VenvPython $patchScript $templateZip
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось подготовить шаблон Flutter-проекта (код $LASTEXITCODE)"
    }
    Remove-Item -LiteralPath $patchScript -Force -ErrorAction SilentlyContinue

    $repairedHash = (Get-FileHash -LiteralPath $templateZip -Algorithm SHA256).Hash
    Set-Content -LiteralPath $marker -Value $repairedHash -Encoding Ascii
}

function Repair-GeneratedAndroidPermissions {
    <#
    .SYNOPSIS
        Убирает лишние разрешения из уже сгенерированного Flutter-проекта.

    .DESCRIPTION
        `flet` может переиспользовать `build/flutter`, не пересоздавая его из
        шаблона. На этот случай чистим готовый проект: RECORD_AUDIO из
        debug/profile-манифестов (его добавляет шаблон) и INTERNET из main.
        В release debug/profile-манифесты не участвуют, поэтому INTERNET туда
        не вернётся; в debug его снова добавит debug-манифест для hot reload.
    #>
    $srcDir = Join-Path $Root 'build\flutter\android\app\src'
    if (-not (Test-Path $srcDir)) {
        return
    }

    $changed = 0
    $permissionPattern = '(?m)^[ \t]*<uses-permission android:name="android\.permission\.{0}" />[ \t]*\r?\n?'

    foreach ($variant in @('debug', 'profile')) {
        $file = Join-Path $srcDir "$variant\AndroidManifest.xml"
        if (-not (Test-Path $file)) {
            continue
        }
        $text = Get-Content -Raw -Path $file
        $new = [regex]::Replace($text, ($permissionPattern -f 'RECORD_AUDIO'), '')
        if ($new -ne $text) {
            [System.IO.File]::WriteAllText($file, $new, (New-Object System.Text.UTF8Encoding($false)))
            $changed += 1
        }
    }

    $mainFile = Join-Path $srcDir 'main\AndroidManifest.xml'
    if (Test-Path $mainFile) {
        $text = Get-Content -Raw -Path $mainFile
        $new = [regex]::Replace($text, ($permissionPattern -f 'INTERNET'), '')
        if ($new -ne $text) {
            [System.IO.File]::WriteAllText($mainFile, $new, (New-Object System.Text.UTF8Encoding($false)))
            $changed += 1
        }
    }

    if ($changed -gt 0) {
        Write-Host "Убраны лишние разрешения из build\flutter (файлов: $changed)." -ForegroundColor Cyan
    }
}

function Repair-PythonDistCache {
    <#
    .SYNOPSIS
        Заставляет сборку брать архивы Python для Android из локального кэша.

    .DESCRIPTION
        Плагин `serious_python_android` на каждом запуске сверяет архивы
        python-build с GitHub (`downloadDistArchive_<abi>`, ETag-запрос) и падает,
        если GitHub отвечает 502 — даже когда архивы уже лежат в
        `.flet\home\.flet\cache\python-build`. Патч добавляет в задачу проверку:
        если файл уже скачан, в сеть не ходим (StopExecutionException).
        Патч идемпотентен и применяется к кэшу pub, который в git не попадает.
    #>
    $pubCache = Join-Path $FletHome '.pub-cache\hosted\pub.dev'
    if (-not (Test-Path $pubCache)) {
        return
    }

    $patched = 0
    foreach ($dir in Get-ChildItem -Path $pubCache -Directory -Filter 'serious_python_android-*') {
        $file = Join-Path $dir.FullName 'android\build.gradle.kts'
        if (-not (Test-Path $file)) {
            continue
        }
        $text = Get-Content -Raw -Path $file
        if ($text -match 'DSH-OFFLINE') {
            continue
        }

        $old = "        doFirst { distFile.parentFile.mkdirs() }"
        if (-not $text.Contains($old)) {
            Write-Host "Не удалось перевести архивы Python на локальный кэш: $file" -ForegroundColor Yellow
            continue
        }
        $new = @"
        doFirst {
            distFile.parentFile.mkdirs()
            // DSH-OFFLINE: архив уже скачан — не ходим на GitHub за ETag.
            if (distFile.exists() && distFile.length() > 0L) {
                throw org.gradle.api.tasks.StopExecutionException()
            }
        }
"@
        $text = $text.Replace($old, $new)
        [System.IO.File]::WriteAllText($file, $text, (New-Object System.Text.UTF8Encoding($false)))
        $patched += 1
    }

    if ($patched -gt 0) {
        Write-Host "Архивы Python для Android берутся из локального кэша (файлов: $patched)." -ForegroundColor Cyan
    }
}

function Get-AdbDevices {
    <#
    .SYNOPSIS
        Возвращает список устройств из вывода `adb devices -l`.
    #>
    param([Parameter(Mandatory)][string]$Adb)

    $lines = & $Adb devices -l 2>&1
    $devices = @()
    foreach ($line in $lines) {
        if ($line -notmatch '^(?<id>\S+)\s+(?<state>device|unauthorized|offline|no permissions)\b') {
            continue
        }
        $id = $Matches['id']
        $state = $Matches['state']
        $model = ''
        if ($line -match 'model:(?<model>\S+)') {
            $model = $Matches['model'].Replace('_', ' ')
        }
        $devices += [pscustomobject]@{ Id = $id; State = $state; Model = $model }
    }
    return $devices
}

function Write-DeviceHint {
    <#
    .SYNOPSIS
        Печатает памятку, если телефон не виден в adb или не авторизован.
    #>
    param($Devices)

    $unauthorized = @($Devices | Where-Object { $_.State -eq 'unauthorized' })
    if ($unauthorized.Count -gt 0) {
        Write-Host 'Телефон виден, но отладка по USB не авторизована:' -ForegroundColor Yellow
        Write-Host '  разблокируйте телефон и нажмите "Разрешить" в запросе'
        Write-Host '  "Разрешить отладку по USB?" (лучше с "Всегда разрешать").'
        return
    }
    Write-Host 'Устройство не найдено. Проверьте:' -ForegroundColor Yellow
    Write-Host '  1. телефон подключён кабелем, который передаёт данные (не только зарядка);'
    Write-Host '  2. в настройках разработчика включена "Отладка по USB";'
    Write-Host '  3. на телефоне подтверждён запрос "Разрешить отладку по USB?".'
}

function Get-AppPackage {
    <#
    .SYNOPSIS
        Возвращает Android-идентификатор приложения (applicationId).
    #>
    param([Parameter(Mandatory)][string]$ProjectRoot)

    $gradleDir = Join-Path $ProjectRoot 'build\flutter\android\app'
    foreach ($fileName in @('build.gradle.kts', 'build.gradle')) {
        $gradleFile = Join-Path $gradleDir $fileName
        if (-not (Test-Path $gradleFile)) {
            continue
        }
        $text = Get-Content -Raw -Path $gradleFile
        if ($text -match 'namespace\s*[= ]\s*"(?<pkg>[^"]+)"') {
            return $Matches['pkg']
        }
        if ($text -match 'applicationId\s*[= ]\s*"?(?<pkg>[\w.]+)"?') {
            return $Matches['pkg']
        }
    }

    # Проект ещё не генерировался — собираем идентификатор так же, как flet:
    # org из [tool.flet] и имя проекта с недопустимыми символами, заменёнными на `_`.
    $pyproject = Get-Content -Raw -Path (Join-Path $ProjectRoot 'pyproject.toml')
    if ($pyproject -notmatch '(?m)^\s*org\s*=\s*"(?<org>[^"]+)"') {
        throw 'Не удалось определить org приложения: нет namespace в build.gradle и org в pyproject.toml.'
    }
    $org = $Matches['org']
    if ($pyproject -notmatch '(?m)^\s*name\s*=\s*"(?<name>[^"]+)"') {
        throw 'Не удалось определить имя приложения: нет name в pyproject.toml.'
    }
    $safeName = ($Matches['name'].ToLowerInvariant() -replace '[^0-9a-z_]', '_')
    return "$org.$safeName"
}

function Wait-AppRunning {
    <#
    .SYNOPSIS
        Ждёт, пока на устройстве появится процесс приложения, и возвращает его PID.
    #>
    param(
        [Parameter(Mandatory)][string]$Adb,
        [Parameter(Mandatory)][string]$Package,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $pids = (& $Adb shell pidof $Package 2>$null | Out-String).Trim()
        if ($pids -match '^\d+') {
            return ($pids -split '\s+')[0]
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Resolve-DeviceId {
    <#
    .SYNOPSIS
        Ждёт авторизованное устройство и возвращает его ID.
    #>
    param(
        [Parameter(Mandatory)][string]$Adb,
        [string]$RequestedId,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $hintShown = $false
    while ($true) {
        $devices = Get-AdbDevices -Adb $Adb
        $ready = @($devices | Where-Object { $_.State -eq 'device' })

        if ($RequestedId) {
            $match = $ready | Where-Object { $_.Id -eq $RequestedId } | Select-Object -First 1
            if ($match) {
                return $match.Id
            }
        } elseif ($ready.Count -eq 1) {
            return $ready[0].Id
        } elseif ($ready.Count -gt 1) {
            $ids = ($ready | ForEach-Object { $_.Id }) -join ', '
            throw "Подключено несколько устройств ($ids). Укажите нужное через -DeviceId."
        }

        if ((Get-Date) -ge $deadline) {
            $found = if (@($devices).Count -gt 0) {
                'найдены: ' + (($devices | ForEach-Object { "$($_.Id)=$($_.State)" }) -join ', ')
            } else {
                'не найдено ни одного устройства'
            }
            throw "За $TimeoutSeconds с устройство не готово ($found)."
        }

        if (-not $hintShown) {
            Write-DeviceHint -Devices $devices
            $hintShown = $true
        }
        Start-Sleep -Seconds 2
    }
}

# --- 1. Окружение -----------------------------------------------------------
Initialize-Environment
Initialize-ReleaseSigning

if (-not (Test-Path $FletExe)) {
    throw "Не найден flet: $FletExe. Активируйте окружение: .venv\Scripts\Activate.ps1"
}

# --- 2. Toolchain -----------------------------------------------------------
$flutterVersion = Get-RequiredFlutterVersion
$flutterDir = Install-FlutterSdk -Version $flutterVersion
Ensure-AndroidSdk
$fletVersion = (& $VenvPython -c 'import flet.version; print(flet.version.flet_version)' | Out-String).Trim()
Repair-BuildTemplate -FletVersion $fletVersion
Repair-GeneratedAndroidPermissions
Repair-PythonDistCache
& $AdbExe start-server | Out-Null

# --- 3. Устройство ----------------------------------------------------------
$resolvedId = Resolve-DeviceId -Adb $AdbExe -RequestedId $DeviceId -TimeoutSeconds $WaitSeconds

if ($SetupOnly) {
    Write-Host ''
    Write-Host 'Toolchain готов:' -ForegroundColor Green
    Write-Host "  Flutter:     $flutterDir"
    Write-Host "  Android SDK: $SdkDir"
    Write-Host ''
    Write-Host 'Подключённые устройства:'
    & $AdbExe devices -l
    Write-Host ''
    Write-Host "Выбранное устройство: $resolvedId"
    Write-Host "Запуск: .\tools\run_on_device.cmd -DeviceId $resolvedId"
    exit 0
}

# --- 4. Сборка и запуск -----------------------------------------------------
$fletArgs = @(
    'debug', 'android', '.',
    '--device-id', $resolvedId,
    '--yes',
    '--log-format', 'plain',
    '-v'
)
if ($Release) {
    $fletArgs += '--release'
}
if ($ExtraArgs) {
    $fletArgs += $ExtraArgs
}

# Без -Attach flet запускает `flutter run` с `--no-resident`: сборка, установка,
# запуск приложения и выход. Аргументы после `--` flet передаёт в flutter run.
# Приложение при этом остаётся запущенным.
if (-not $Attach -and -not ($fletArgs -contains '--')) {
    $fletArgs += @('--', '--no-resident')
}

$modeText = if ($Attach) { 'с подключением к устройству (Ctrl+C — выход)' } else { 'и выход после запуска' }
Write-Host "Сборка и запуск на устройстве $resolvedId (первая сборка долгая), $modeText..." -ForegroundColor Cyan

Push-Location $Root
try {
    & $FletExe @fletArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($code -ne 0) {
    Write-Host "flet debug завершился с кодом $code." -ForegroundColor Red
    exit $code
}

if ($Attach) {
    exit 0
}

# --- 5. Проверка запуска ----------------------------------------------------
$package = Get-AppPackage -ProjectRoot $Root
$appPid = Wait-AppRunning -Adb $AdbExe -Package $package -TimeoutSeconds $VerifySeconds
if (-not $appPid) {
    Write-Host "APK собран и установлен, но процесс $package не появился за $VerifySeconds с." -ForegroundColor Red
    Write-Host 'Проверьте телефон: возможно, приложение упало при старте (adb logcat).' -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host "Готово: $package собран, установлен и запущен на $resolvedId (pid $appPid)." -ForegroundColor Green
Write-Host "Приложение можно закрыть: adb shell am force-stop $package"
exit 0
