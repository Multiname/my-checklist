"""Статистика кадров прокрутки по выводу `dumpsys SurfaceFlinger --latency`.

Вызывается из `tools/measure_scroll.ps1`: аргументы — префикс файлов
`.tmp/latency-<префикс>-<N>.txt` и число проходов. Проход, в котором успело
показаться меньше 20 кадров (жест не сработал или флинг сразу упёрся в край
списка), в статистику не идёт.

Формат файла: строка с периодом обновления (нс), затем до 128 строк
`desiredPresentTime actualPresentTime frameReadyTime` (нс); нули — пустые слоты.
Строки в буфере кольцевые, порядок не гарантирован — сортируем по времени показа.

«Поздний» кадр — интервал больше полутора периодов: экран во время прокрутки
работает на 120 Гц (8,3 мс), и такой интервал виден как рывок.
"""

from __future__ import annotations

import glob
import statistics
import sys
from pathlib import Path


def read_frames(path: Path) -> list[int]:
    """Моменты показа кадров (actualPresentTime) из файла latency, нс."""
    raw = path.read_bytes()
    text = raw.decode("utf-16") if b"\x00" in raw[:200] else raw.decode("utf-8", "replace")
    moments: list[int] = []
    for line in text.lstrip("\ufeff").splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        actual = int(parts[1])
        if actual:
            moments.append(actual)
    moments.sort()
    return moments


def main() -> int:
    prefix = sys.argv[1]
    period_ns = 16_666_667
    runs: list[tuple[Path, list[int]]] = []
    skipped: list[tuple[Path, int]] = []
    for name in sorted(glob.glob(f".tmp/latency-{prefix}-*.txt")):
        path = Path(name)
        frames = read_frames(path)
        if len(frames) < 20:
            skipped.append((path, len(frames)))
            continue
        runs.append((path, frames))

    if not runs:
        print("нет ни одного прохода с кадрами: жест не сработал?")
        return 1

    intervals = [
        (frames[i + 1] - frames[i]) / 1e6
        for _, frames in runs
        for i in range(len(frames) - 1)
    ]
    total_frames = sum(len(frames) for _, frames in runs)
    span_ms = sum((frames[-1] - frames[0]) / 1e6 for _, frames in runs)
    ordered = sorted(intervals)
    median = statistics.median(intervals)
    # Экран во время прокрутки работает на 120 Гц: «гладкий» интервал — 8,3 мс.
    refresh = min(median, period_ns / 1e6)
    late = sum(1 for value in intervals if value > refresh * 1.5)

    used = f"{len(runs)} из {len(runs) + len(skipped)}"
    if skipped:
        missed = ", ".join(f"{path.stem.rsplit('-', 1)[-1]}={count}" for path, count in skipped)
        used += f" (пропущены: {missed})"
    print(f"прогонов: {used}")
    print(f"кадров: {total_frames} за {span_ms:.0f} мс -> {total_frames / (span_ms / 1000):.1f} кадр/с")
    print(
        f"интервалы: p50 {median:.1f} мс, p90 {ordered[int(len(ordered) * 0.9)]:.1f} мс, "
        f"p99 {ordered[int(len(ordered) * 0.99)]:.1f} мс, max {max(intervals):.1f} мс"
    )
    print(
        f"поздние кадры: >{refresh * 1.5:.1f} мс {late} ({100 * late / len(intervals):.0f}%), "
        f">33 мс {sum(1 for value in intervals if value > 33)}, "
        f">50 мс {sum(1 for value in intervals if value > 50)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
