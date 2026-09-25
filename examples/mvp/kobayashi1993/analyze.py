#!/usr/bin/env python3
"""Build Kobayashi 1993 numerical metrics from COMSOL and Fig. 7 evidence."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageDraw


DELTA_TAGS = {
    0.0: "delta000",
    0.005: "delta005",
    0.01: "delta010",
    0.02: "delta020",
    0.05: "delta050",
}
SENSITIVITY_CASES = ("control_delta020", "mesh_fine", "timestep_fine", "seed_small", "seed_large")


def _tokens(line: str) -> list[str]:
    return [item.strip() for item in next(csv.reader([line.lstrip("% ")]))]


def read_comsol_csv(path: Path) -> tuple[list[str], list[list[float]]]:
    headers: list[list[str]] = []
    rows: list[list[float]] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%"):
            candidate = _tokens(line)
            if len(candidate) >= 2:
                headers.append(candidate)
            continue
        values = [float(item.strip()) for item in next(csv.reader([line]))]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"non-finite value in {path}")
        rows.append(values)
    if not rows:
        raise ValueError(f"no numeric data in {path}")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError(f"ragged COMSOL CSV: {path}")
    matching = [header for header in headers if len(header) == width]
    if not matching:
        raise ValueError(f"no full-width commented header in {path}")
    return matching[-1], rows


def _column(header: list[str], *names: str) -> int:
    compact = [re.sub(r"\s+", "", item).lower() for item in header]
    for name in names:
        target = re.sub(r"\s+", "", name).lower()
        matches = [i for i, item in enumerate(compact) if item == target or item.startswith(target + "(")]
        if len(matches) == 1:
            return matches[0]
    raise ValueError(f"missing unique column {names}; available={header}")


def _history(header: list[str], rows: list[list[float]]) -> dict[str, Any]:
    columns = {
        "time": _column(header, "Time", "Time(s)", "t"),
        "enthalpy": _column(header, "enthalpyInvariant", "post-processing enthalpy invariant"),
        "tip": _column(header, "tipY", "maximum vertical solid coordinate"),
        "half_width": _column(header, "halfWidth", "maximum horizontal solid coordinate"),
        "p_min": _column(header, "pMin", "minimum phase-field value"),
        "p_max": _column(header, "pMax", "maximum phase-field value"),
    }
    initial = rows[0][columns["enthalpy"]]
    scale = max(abs(initial), 1e-12)
    return {
        "rows": rows,
        "columns": columns,
        "p_min": min(row[columns["p_min"]] for row in rows),
        "p_max": max(row[columns["p_max"]] for row in rows),
        "max_relative_enthalpy_drift": max(abs(row[columns["enthalpy"]] - initial) / scale for row in rows),
    }


def history(path: Path) -> dict[str, Any]:
    return _history(*read_comsol_csv(path))


def split_history(path: Path) -> dict[float, dict[str, Any]]:
    header, rows = read_comsol_csv(path)
    delta_index = _column(header, "delta")
    grouped: dict[float, list[list[float]]] = {}
    for row in rows:
        grouped.setdefault(float(row[delta_index]), []).append(row)
    expected = set(DELTA_TAGS)
    if set(grouped) != expected:
        raise ValueError(f"combined history deltas {sorted(grouped)} do not match {sorted(expected)}")
    return {delta: _history(header, grouped[delta]) for delta in sorted(grouped)}


def interpolate(hist: dict[str, Any], metric: str, target: float) -> float:
    rows = hist["rows"]
    ti = hist["columns"]["time"]
    yi = hist["columns"][metric]
    if target < rows[0][ti] - 1e-12 or target > rows[-1][ti] + 1e-12:
        raise ValueError(f"target time {target} outside [{rows[0][ti]}, {rows[-1][ti]}]")
    for left, right in zip(rows, rows[1:]):
        if left[ti] <= target <= right[ti]:
            if abs(right[ti] - left[ti]) <= 1e-15:
                return left[yi]
            weight = (target - left[ti]) / (right[ti] - left[ti])
            return left[yi] + weight * (right[yi] - left[yi])
    return rows[-1][yi]


def _relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(right), 1e-12)


def _phase_columns(header: list[str]) -> dict[tuple[float, float], int]:
    result: dict[tuple[float, float], int] = {}
    for index, value in enumerate(header):
        if not re.match(r"^(?:comp1\.)?p(?:\s|\(|@|$)", value.strip(), re.IGNORECASE):
            continue
        time_match = re.search(r"@\s*t\s*=\s*([-+0-9.eE]+)", value)
        delta_match = re.search(r"delta\s*=\s*([-+0-9.eE]+)", value)
        if not time_match or not delta_match:
            raise ValueError(f"phase column lacks time/delta annotation: {value}")
        key = (float(delta_match.group(1)), float(time_match.group(1)))
        if key in result:
            raise ValueError(f"duplicate phase column {key}")
        result[key] = index
    if not result:
        raise ValueError("no phase-field columns")
    return result


def field_masks(path: Path, output: Path) -> dict[tuple[float, float], Path]:
    header, rows = read_comsol_csv(path)
    xi = _column(header, "X")
    yi = _column(header, "Y")
    phase = _phase_columns(header)
    xs = sorted({row[xi] for row in rows})
    ys = sorted({row[yi] for row in rows})
    if len(rows) != len(xs) * len(ys) or len(xs) < 2 or len(ys) < 2:
        raise ValueError(f"incomplete regular grid in {path}")
    xmap = {value: i for i, value in enumerate(xs)}
    ymap = {value: i for i, value in enumerate(ys)}
    output.mkdir(parents=True, exist_ok=True)
    result: dict[tuple[float, float], Path] = {}
    for (delta, time_value), column in sorted(phase.items()):
        image = Image.new("L", (len(xs), len(ys)), 0)
        pixels = image.load()
        seen: set[tuple[int, int]] = set()
        for row in rows:
            point = (xmap[row[xi]], len(ys) - 1 - ymap[row[yi]])
            if point in seen:
                raise ValueError(f"duplicate grid point in {path}: {point}")
            seen.add(point)
            pixels[point] = 255 if row[column] >= 0.5 else 0
        tag = DELTA_TAGS[delta]
        filename = output / f"sim_{tag}_t{str(time_value).replace('.', 'p')}_mask.png"
        image.resize((192, 192), Image.Resampling.NEAREST).save(filename)
        result[(delta, time_value)] = filename
    return result


def _mask(path: Path) -> list[list[bool]]:
    image = Image.open(path).convert("L").resize((192, 192), Image.Resampling.NEAREST)
    pixels = image.load()
    return [[pixels[x, y] >= 128 for x in range(192)] for y in range(192)]


def _contour(mask: list[list[bool]]) -> list[tuple[int, int]]:
    points = []
    for y in range(192):
        for x in range(192):
            if mask[y][x] and any(
                xx < 0 or yy < 0 or xx >= 192 or yy >= 192 or not mask[yy][xx]
                for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            ):
                points.append((x, y))
    return points


def _distance_map(points: list[tuple[int, int]]) -> list[list[float]]:
    distance = [[float("inf")] * 192 for _ in range(192)]
    for x, y in points:
        distance[y][x] = 0.0
    diagonal = math.sqrt(2.0)
    for y in range(192):
        for x in range(192):
            value = distance[y][x]
            if x:
                value = min(value, distance[y][x - 1] + 1)
            if y:
                value = min(value, distance[y - 1][x] + 1)
                if x:
                    value = min(value, distance[y - 1][x - 1] + diagonal)
                if x < 191:
                    value = min(value, distance[y - 1][x + 1] + diagonal)
            distance[y][x] = value
    for y in range(191, -1, -1):
        for x in range(191, -1, -1):
            value = distance[y][x]
            if x < 191:
                value = min(value, distance[y][x + 1] + 1)
            if y < 191:
                value = min(value, distance[y + 1][x] + 1)
                if x:
                    value = min(value, distance[y + 1][x - 1] + diagonal)
                if x < 191:
                    value = min(value, distance[y + 1][x + 1] + diagonal)
            distance[y][x] = value
    return distance


def compare_masks(reference: Path, simulation: Path) -> dict[str, float]:
    ref = _mask(reference)
    sim = _mask(simulation)
    intersection = sum(ref[y][x] and sim[y][x] for y in range(192) for x in range(192))
    union = sum(ref[y][x] or sim[y][x] for y in range(192) for x in range(192))
    ref_contour, sim_contour = _contour(ref), _contour(sim)
    if not union or not ref_contour or not sim_contour:
        raise ValueError(f"empty comparison mask: {reference}, {simulation}")
    rd, sd = _distance_map(ref_contour), _distance_map(sim_contour)
    chamfer = 0.5 * (
        sum(rd[y][x] for x, y in sim_contour) / len(sim_contour)
        + sum(sd[y][x] for x, y in ref_contour) / len(ref_contour)
    )
    return {"iou": intersection / union, "normalized_chamfer": chamfer / 192.0}


def comparison_figure(masks: dict[tuple[float, float], Path], reference_dir: Path, output: Path) -> None:
    panel = 192
    label_height = 22
    times = (0.2, 0.8, 1.4)
    canvas = Image.new("RGB", (len(times) * 2 * panel, len(DELTA_TAGS) * (panel + label_height)), "white")
    draw = ImageDraw.Draw(canvas)
    for row, (delta, tag) in enumerate(DELTA_TAGS.items()):
        for column, time_value in enumerate(times):
            time_tag = str(time_value).replace(".", "p")
            reference_path = reference_dir / f"ref_{tag}_t{time_tag}_mask.png"
            simulation_path = masks[(delta, time_value)]
            reference = Image.open(reference_path).convert("RGB").resize((panel, panel), Image.Resampling.NEAREST)
            simulation = Image.open(simulation_path).convert("RGB").resize((panel, panel), Image.Resampling.NEAREST)
            x = 2 * column * panel
            y = row * (panel + label_height) + label_height
            canvas.paste(reference, (x, y))
            canvas.paste(simulation, (x + panel, y))
            draw.text((x + 4, y - label_height + 4), f"paper delta={delta:g}, t={time_value:g}", fill="black")
            draw.text((x + panel + 4, y - label_height + 4), "COMSOL p>=0.5", fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)


def fig7_metrics(fields_csv: Path, reference_dir: Path, mask_dir: Path) -> dict[str, Any]:
    masks = field_masks(fields_csv, mask_dir)
    panels = []
    for (delta, time_value), simulation in sorted(masks.items()):
        tag = DELTA_TAGS[delta]
        time_tag = str(time_value).replace(".", "p")
        reference = reference_dir / f"ref_{tag}_t{time_tag}_mask.png"
        if not reference.is_file():
            raise FileNotFoundError(reference)
        panels.append({"delta": delta, "time": time_value, **compare_masks(reference, simulation)})
    comparison_figure(masks, reference_dir, mask_dir / "fig7_paper_vs_comsol.png")
    return {
        "mean_iou": sum(item["iou"] for item in panels) / len(panels),
        "normalized_chamfer": sum(item["normalized_chamfer"] for item in panels) / len(panels),
        "panels": panels,
    }


def sensitivity_history(root: Path, case: str) -> dict[str, Any]:
    return history(root / case / "results" / f"{case}_global.csv")


def build_metrics(global_csv: Path, fields_csv: Path, reference_dir: Path, sensitivity_root: Path, masks_dir: Path) -> dict[str, Any]:
    baselines = split_history(global_csv)
    sensitivities = {case: sensitivity_history(sensitivity_root, case) for case in SENSITIVITY_CASES}
    all_histories = list(baselines.values()) + list(sensitivities.values())

    baseline = sensitivities["control_delta020"]
    seed_values = [
        interpolate(sensitivities["seed_small"], "tip", 0.8),
        interpolate(baseline, "tip", 0.8),
        interpolate(sensitivities["seed_large"], "tip", 0.8),
    ]
    delta000_tip = interpolate(baselines[0.0], "tip", 1.4)
    delta050_tip = interpolate(baselines[0.05], "tip", 1.4)
    delta050_half_width = interpolate(baselines[0.05], "half_width", 1.4)
    figure = fig7_metrics(fields_csv, reference_dir, masks_dir)

    return {
        "time.max": max(row[baselines[0.0]["columns"]["time"]] for row in baselines[0.0]["rows"]),
        "quality.p_min": min(item["p_min"] for item in all_histories),
        "quality.p_max": max(item["p_max"] for item in all_histories),
        "quality.max_relative_enthalpy_drift": max(item["max_relative_enthalpy_drift"] for item in all_histories),
        "convergence.mesh_tip_relative_difference": _relative(
            interpolate(baseline, "tip", 0.8),
            interpolate(sensitivities["mesh_fine"], "tip", 0.8),
        ),
        "convergence.timestep_tip_relative_difference": _relative(
            interpolate(baseline, "tip", 0.8),
            interpolate(sensitivities["timestep_fine"], "tip", 0.8),
        ),
        "convergence.seed_tip_relative_range": (max(seed_values) - min(seed_values))
        / max(abs(seed_values[1]), 1e-12),
        "paper_trend.delta050_to_delta000_tip_ratio": delta050_tip / max(abs(delta000_tip), 1e-12),
        "paper_trend.delta050_vertical_to_horizontal_extent_ratio": delta050_tip
        / max(abs(delta050_half_width), 1e-12),
        "paper_figure.fig7_mean_iou": figure["mean_iou"],
        "paper_figure.fig7_normalized_chamfer": figure["normalized_chamfer"],
        "fig7_panels": figure["panels"],
        "baseline_history_metrics": {
            str(delta): {
                "p_min": item["p_min"],
                "p_max": item["p_max"],
                "max_relative_enthalpy_drift": item["max_relative_enthalpy_drift"],
                "tip_final": interpolate(item, "tip", 1.4),
                "half_width_final": interpolate(item, "half_width", 1.4),
            }
            for delta, item in baselines.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--global-csv", type=Path, required=True)
    parser.add_argument("--fields-csv", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--sensitivity-root", type=Path, required=True)
    parser.add_argument("--masks-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metrics = build_metrics(
        args.global_csv,
        args.fields_csv,
        args.reference_dir,
        args.sensitivity_root,
        args.masks_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
