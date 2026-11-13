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

    $url = "https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_$Version-stable.zip"
    $archive = Join-Path $FletHome "flutter_windows_$Version-stable.zip"
    $staging = Join-Path $TmpDir 'flutter_extract'

    if (-not (Test-Path $archive)) {
        Write-Host "Скачиваю Flutter $Version (~2 ГБ): $url" -ForegroundColor Cyan
        & $curl.Source -L --fail --show-error --output $archive $url
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось скачать Flutter ($LASTEXITCODE): $url"
        }
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
        Оставляет в шаблоне Flutter-проекта только Android.

    .DESCRIPTION
        Шаблон `flet-build-template` содержит каталоги `windows/` и `linux/`.
        Заметив их, Flutter при сборке создаёт симлинки на плагины, а окружение
        агента (пониженные права Windows) не может создавать симлинки:
        `Building with plugins requires symlink support` / `WinError 1314`.
        Проект Android-only, desktop-платформы не нужны, поэтому каталоги
        вырезаются из кэша шаблона один раз — до того, как flet развернёт из
        него Flutter-проект.

        Каталог кэша совпадает с тем, что использует flet:
        `~/.flet/cache/build-template/v<версия>/` (здесь `~` — `.flet\home`).
    #>
    param([Parameter(Mandatory)][string]$FletVersion)

    $cacheDir = Join-Path $FletHome ".flet\cache\build-template\v$FletVersion"
    $templateZip = Join-Path $cacheDir 'flet-build-template.zip'
    $marker = Join-Path $cacheDir 'android-only.marker'
    if (Test-Path $marker) {
        return
    }

    if (-not (Test-Path $templateZip)) {
        $url = "https://github.com/flet-dev/flet/releases/download/v$FletVersion/flet-build-template.zip"
        Write-Host "Скачиваю шаблон Flutter-проекта: $url" -ForegroundColor Cyan
        New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
        & curl.exe -L --fail --show-error --output $templateZip $url
        if ($LASTEXITCODE -ne 0) {
            throw "Не удалось скачать шаблон ($LASTEXITCODE): $url"
        }
    }

    $code = @'
import os, sys, zipfile

src = sys.argv[1]
tmp = src + '.tmp'
dropped = 0
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        name = item.filename
        if '/windows/' in name or '/linux/' in name:
            dropped += 1
            continue
        zout.writestr(item, zin.read(name))
os.replace(tmp, src)
print(f'убрано desktop-файлов: {dropped}')
'@
    & $VenvPython -c $code $templateZip
    if ($LASTEXITCODE -ne 0) {
        throw 'Не удалось подготовить шаблон Flutter-проекта'
    }
    New-Item -ItemType File -Force -Path $marker | Out-Null
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

if (-not (Test-Path $FletExe)) {
    throw "Не найден flet: $FletExe. Активируйте окружение: .venv\Scripts\Activate.ps1"
}

# --- 2. Toolchain -----------------------------------------------------------
$flutterVersion = Get-RequiredFlutterVersion
$flutterDir = Install-FlutterSdk -Version $flutterVersion
Ensure-AndroidSdk
$fletVersion = (& $VenvPython -c 'import flet.version; print(flet.version.flet_version)' | Out-String).Trim()
Repair-BuildTemplate -FletVersion $fletVersion
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
