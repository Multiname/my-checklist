<#
.SYNOPSIS
    Замер плавности инерционной прокрутки на подключённом Android-устройстве.

.DESCRIPTION
    Скрипт запускает установленное приложение, делает разогревающий проход
    (первая прокрутка компилирует JIT-ветки отрисовки строк в debug-сборке) и
    выполняет N одинаковых флингов вверх/вниз. После каждого флинга снимается
    `dumpsys SurfaceFlinger --latency` по слою SurfaceView приложения: это
    моменты показа кадров, по ним `tools/scroll_stats.py` считает частоту и
    «поздние» кадры.

    Данные для замера — длинный список (15 категорий по 5 пунктов):
    `tools/seed_checklist.py` создаёт seed-БД, её заливают на устройство через
    `adb push` + `run-as ... cp` (см. docs/Verification.md, «Замеры прокрутки»).

.PARAMETER Label
    Префикс файлов замера в .tmp: latency-<Label>-<N>.txt.

.PARAMETER FlingCount
    Сколько флингов сделать (по умолчанию 10).

.PARAMETER DeviceId
    ID устройства из `adb devices`. Необязателен, если телефон один.

.PARAMETER Package
    Пакет приложения (по умолчанию com.blackline.my_checklist).

.PARAMETER SettleMs
    Пауза после флинга перед снятием статистики, мс.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\measure_scroll.ps1 -Label before

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\measure_scroll.ps1 -Label after -FlingCount 12
#>
param(
    [string]$Label = "run",
    [int]$FlingCount = 10,
    [string]$DeviceId = "",
    [string]$Package = "com.blackline.my_checklist",
    [int]$SettleMs = 2600
)

$ErrorActionPreference = "Stop"
# Русский текст в консоли: без этого Windows PowerShell пишет его в cp1251,
# а вывод Python читает не в той кодировке, в которой он его получил.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Adb = Join-Path $Root ".flet\home\Android\sdk\platform-tools\adb.exe"
if (-not (Test-Path $Adb)) {
    throw "adb не найден: $Adb. Разверните toolchain: tools\run_on_device.cmd -SetupOnly"
}
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python не найден: $Python"
}
if (-not (Test-Path ".tmp")) {
    New-Item -ItemType Directory -Force ".tmp" | Out-Null
}

# --- Устройство и геометрия экрана -----------------------------------------
$devices = @(& $Adb devices | Select-Object -Skip 1 |
    Where-Object { $_ -match "\sdevice\s*$" } |
    ForEach-Object { ($_ -split "\s+")[0] })
if (-not $DeviceId) {
    if ($devices.Count -ne 1) {
        throw "Подключено устройств: $($devices.Count). Укажите -DeviceId (см. adb devices)."
    }
    $DeviceId = $devices[0]
}
$AdbDevice = @("-s", $DeviceId)

$size = (& $Adb @AdbDevice shell wm size | Select-Object -First 1) -replace ".*:\s*", ""
if ($size -notmatch "^(\d+)x(\d+)$") {
    throw "Не удалось определить размер экрана: '$size'"
}
$Width = [int]$Matches[1]
$Height = [int]$Matches[2]
$CenterX = [int]($Width / 2)
$SwipeFrom = [int]($Height * 0.72)
$SwipeTo = [int]($Height * 0.25)
$Swipe = {
    param($from, $to, $ms)
    & $Adb @AdbDevice shell input swipe $CenterX $from $CenterX $to $ms
}
Write-Host "Устройство: $DeviceId, экран: $Width x $Height" -ForegroundColor Cyan

# --- Запуск приложения и разогрев ------------------------------------------
& $Adb @AdbDevice shell am force-stop $Package | Out-Null
Start-Sleep -Milliseconds 500
& $Adb @AdbDevice shell am start -W -n "$Package/.MainActivity" | Out-Null
Start-Sleep -Seconds 10

# Первый проход компилирует JIT-ветки отрисовки строк (в debug-сборке это
# заметно), второй возвращает список к началу.
& $Swipe $SwipeFrom ([int]($Height * 0.29)) 300
Start-Sleep -Milliseconds 1500
& $Swipe ([int]($Height * 0.29)) ([int]($Height * 0.75)) 300
Start-Sleep -Milliseconds 1500

# --- Слой SurfaceView: в него Flutter рисует кадры -------------------------
# Слоёв с суффиксом (BLAST) может быть несколько (например, от прежнего
# экземпляра приложения), поэтому берём последний и проверяем, что в него
# действительно показываются кадры: у «мёртвого» слоя все отметки нулевые.
$layer = ""
for ($attempt = 1; $attempt -le 5; $attempt++) {
    $candidate = (& $Adb @AdbDevice shell "dumpsys SurfaceFlinger --list" 2>&1 |
        Select-String -Pattern "\(BLAST\)#" |
        ForEach-Object { ($_.Line -replace '^RequestedLayerState\{', '') -replace ' parentId=.*$', '' } |
        Select-Object -Last 1)
    if (-not $candidate) {
        Start-Sleep -Seconds 1
        continue
    }
    $probe = & $Adb @AdbDevice shell "dumpsys SurfaceFlinger --latency '$candidate'" 2>&1
    $frames = @($probe | Where-Object {
        $_ -match "^\d+\s+\d+\s+\d+$" -and $_ -notmatch "^0\s+0\s+0$"
    })
    if ($frames.Count -gt 0) {
        $layer = $candidate
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $layer) {
    throw "Не найден живой слой SurfaceView приложения: приложение не рисует кадры?"
}
Write-Host "Слой: $layer" -ForegroundColor Cyan

# --- Флинги ----------------------------------------------------------------
$scrollEvents = 0
for ($i = 1; $i -le $FlingCount; $i++) {
    $up = ($i % 2) -eq 1
    & $Adb @AdbDevice shell "dumpsys SurfaceFlinger --latency-clear '$layer'" | Out-Null
    & $Adb @AdbDevice logcat -c | Out-Null
    if ($up) {
        & $Swipe $SwipeFrom $SwipeTo 120
    } else {
        & $Swipe $SwipeTo $SwipeFrom 120
    }
    Start-Sleep -Milliseconds $SettleMs

    $tag = "$Label-$i"
    & $Adb @AdbDevice shell "dumpsys SurfaceFlinger --latency '$layer'" 2>&1 |
        Out-File -Encoding utf8 ".tmp\latency-$tag.txt"
    & $Adb @AdbDevice logcat -d 2>&1 | Out-File -Encoding utf8 ".tmp\logcat-$tag.txt"
    # В release-сборке отладочных логов нет — счётчик остаётся нулевым.
    $scrollEvents += (Select-String -Path ".tmp\logcat-$tag.txt" -Pattern "ScrollNotification" |
        Measure-Object).Count
    Start-Sleep -Milliseconds 700
}

Write-Host ""
Write-Host "Флингов: $FlingCount, событий прокрутки в логе: $scrollEvents (только debug)" -ForegroundColor Cyan
& $Python "tools\scroll_stats.py" $Label
