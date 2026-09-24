"""Numerical reliability checks and paper comparison for a solved iteration."""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .case_contracts import (
    AuditRecord,
    CheckResult,
    CheckStatus,
    IR,
    IterationState,
    append_event,
)
from .contracts import ContractError


RULE_VERSION = "papersim.numeric-audit.v1"


def _check(entity_id: str, check_id: str, passed: bool, reason: str = "", unknown: bool = False) -> CheckResult:
    return CheckResult(
        entity_id=entity_id,
        check_id=check_id,
        validator="numeric-audit",
        status=CheckStatus.PASS if passed else (CheckStatus.UNKNOWN if unknown else CheckStatus.FAIL),
        reason="" if passed else reason,
        rule_version=RULE_VERSION,
    )


def _get(metrics: Mapping[str, Any], dotted: str) -> Any:
    if dotted in metrics:
        return metrics[dotted]
    value: Any = metrics
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def criterion_pass(actual: Any, criterion: Mapping[str, Any]) -> tuple[bool, str]:
    operator = str(criterion.get("operator") or "")
    expected = criterion.get("expected")
    try:
        number = float(actual)
        if operator == "between":
            low, high = expected
            passed = float(low) <= number <= float(high)
        elif operator == "relative_error_le":
            tolerance = float(criterion.get("tolerance"))
            base = max(abs(float(expected)), 1e-30)
            passed = abs(number - float(expected)) / base <= tolerance
        elif operator == "<":
            passed = number < float(expected)
        elif operator == "<=":
            passed = number <= float(expected)
        elif operator == ">":
            passed = number > float(expected)
        elif operator == ">=":
            passed = number >= float(expected)
        elif operator == "==":
            passed = number == float(expected)
        else:
            return False, f"unsupported operator {operator}"
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        return False, f"invalid comparison: {exc}"
    return bool(passed), "pass" if passed else f"{number} {operator} {expected} is false"


def parse_tidy_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    required = {"case_id", "iteration", "stage", "source", "delta", "time", "metric", "value", "unit"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ContractError("results CSV must use the PaperSim tidy schema")
    rows: list[dict[str, Any]] = []
    for row in reader:
        parsed: dict[str, Any] = dict(row)
        for key in ("iteration",):
            parsed[key] = int(row[key])
        for key in ("delta", "time", "value"):
            parsed[key] = float(row[key])
        rows.append(parsed)
    return rows


def parse_comsol_table_csv(text: str) -> list[dict[str, Any]]:
    """Normalize a COMSOL table export into the PaperSim tidy schema."""

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ContractError("empty COMSOL CSV")
    header_index = None
    for index, line in enumerate(lines):
        stripped = line.lstrip("%").strip()
        if "," in stripped and not stripped.lower().startswith(("model", "version", "date", "dimension")):
            header_index = index
            break
    if header_index is None:
        raise ContractError("could not find a CSV header in the COMSOL export")
    reader = csv.reader(lines[header_index:], skipinitialspace=True)
    header = [item.strip() for item in next(reader)]
    rows = [dict(zip(header, row)) for row in reader if row]
    if "delta" not in header:
        raise ContractError("COMSOL export does not contain a delta parameter column")
    time_column = next((item for item in header if item.lower() in {"t", "time"}), None)
    if time_column is None:
        raise ContractError("COMSOL export does not contain a time column")
    metric_columns = [item for item in header if item not in {"delta", time_column}]
    tidy: list[dict[str, Any]] = []
    for row in rows:
        for metric in metric_columns:
            try:
                value = float(row[metric])
                delta = float(row["delta"])
                time = float(row[time_column])
            except (KeyError, TypeError, ValueError):
                continue
            tidy.append(
                {
                    "case_id": "",
                    "iteration": 0,
                    "stage": "solve",
                    "source": "comsol",
                    "delta": delta,
                    "time": time,
                    "metric": metric,
                    "value": value,
                    "unit": "",
                }
            )
    if not tidy:
        raise ContractError("COMSOL export did not yield any numeric rows")
    return tidy


def summarize_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    if not rows:
        raise ContractError("cannot summarize an empty result table")
    available = sorted(set(str(row["metric"]) for row in rows))
    summary: dict[str, Any] = {
        "results.available_metrics": available,
        "time.max": max(float(row["time"]) for row in rows),
        "time.min": min(float(row["time"]) for row in rows),
    }
    by_metric: dict[str, list[Any]] = {}
    for row in rows:
        by_metric.setdefault(str(row["metric"]), []).append(row["value"])
    for metric, values in by_metric.items():
        numbers = [float(value) for value in values]
        summary[f"results.{metric}.min"] = min(numbers)
        summary[f"results.{metric}.max"] = max(numbers)
        summary[f"results.{metric}.last"] = numbers[-1]
    for alias, source in (
        ("quality.p_min", "pMin"),
        ("quality.p_max", "pMax"),
        ("quality.max_relative_enthalpy_drift", "enthalpyRelativeDrift"),
        ("convergence.mesh_tip_relative_difference", "meshTipRelativeDifference"),
        ("convergence.timestep_tip_relative_difference", "timestepTipRelativeDifference"),
        ("convergence.seed_tip_relative_range", "seedTipRelativeRange"),
        ("paper_trend.delta050_to_delta000_tip_ratio", "delta050ToDelta000TipRatio"),
        ("paper_trend.delta050_vertical_to_horizontal_extent_ratio", "delta050DirectionalityRatio"),
        ("paper_figure.fig7_mean_iou", "fig7MeanIoU"),
        ("paper_figure.fig7_normalized_chamfer", "fig7NormalizedChamfer"),
    ):
        if source in by_metric:
            summary[alias] = by_metric[source][-1]
        elif f"results.{source}.last" in summary:
            summary[alias] = summary[f"results.{source}.last"]
    return summary


def audit_numeric(
    record: AuditRecord,
    ir: IR,
    *,
    metrics: Mapping[str, Any],
    solver_status: str,
    solver_exit_code: int | None,
    log_text: str,
    solved_mph_size: int,
) -> AuditRecord:
    if record.state not in {IterationState.SOLVED, IterationState.NUMERICAL_AUDITED}:
        raise ContractError("numeric audit requires a solved iteration")
    if solver_status != "complete" or solver_exit_code != 0:
        raise ContractError("numeric audit refuses a solver run that did not complete with exit code 0")

    checks: list[CheckResult] = [
        _check(ir.case_id, "solver_completed", True),
        _check(
            ir.case_id,
            "requested_endpoint",
            abs(float(metrics.get("time.max", -math.inf)) - float(ir.profile.solver.settings["tfinal"])) <= 1e-9,
            "results do not reach solver.settings.tfinal",
        ),
        _check(
            ir.case_id,
            "log_errors",
            not any(token in log_text.lower() for token in ("error", "exception", "fatal", "license failure")),
            "solver log contains a fatal diagnostic",
        ),
    ]
    evaluated_metrics = dict(metrics)
    evaluated_metrics["artifacts.final_mph_bytes"] = solved_mph_size
    evaluated_metrics["quality.comsol_error_count"] = sum(
        log_text.lower().count(token) for token in ("error", "exception", "fatal", "license failure")
    )
    criterion_checks: list[CheckResult] = []
    for criterion in ir.profile.acceptance:
        metric = criterion.metric
        if metric not in evaluated_metrics:
            passed = False
            message = f"missing metric {metric}"
            actual = None
        else:
            actual = evaluated_metrics[metric]
            passed, message = criterion_pass(actual, criterion.model_dump(mode="json"))
        criterion_checks.append(
            _check(
                criterion.id,
                f"acceptance:{criterion.id}",
                passed,
                f"{message}; actual={actual!r}; metric={metric}",
            )
        )
    all_checks = tuple(checks) + tuple(criterion_checks)
    failing = [item.check_id for item in all_checks if not item.passed]
    comparison = {
        "metrics": evaluated_metrics,
        "criteria": [item.model_dump(mode="json") for item in criterion_checks],
        "passed": not failing,
        "failing": failing,
    }
    updated = record.model_copy(
        update={
            "state": IterationState.NUMERICAL_AUDITED,
            "numerical_checks": all_checks,
            "comparison": comparison,
        }
    )
    return append_event(updated, actor="papersim", action="audit_numeric", stage="numeric", detail={"failing": failing})


def assess(record: AuditRecord, ir: IR) -> AuditRecord:
    if record.state != IterationState.NUMERICAL_AUDITED:
        raise ContractError("assessment requires a completed numerical audit")
    failed = [item.check_id for item in record.numerical_checks if not item.passed]
    uncertainty = [
        item for item in ir.profile.assumptions if "does not report" in item or "assumption" in item.lower()
    ]
    if failed:
        verdict = "not_reproduced"
        confidence = "low"
        scope = "declared model and tested conditions"
    elif uncertainty:
        verdict = "qualified"
        confidence = "high"
        scope = "Eqs. (3)-(5) and Fig. 7 under explicitly declared missing-paper assumptions"
    else:
        verdict = "supported"
        confidence = "high"
        scope = "Eqs. (3)-(5) and Fig. 7 under reported conditions"
    assessment = {
        "case_id": ir.case_id,
        "iteration": ir.iteration,
        "verdict": verdict,
        "confidence": confidence,
        "scope": scope,
        "failed_checks": failed,
        "unresolved_questions": list(ir.profile.open_gaps),
        "paper_evidence_confidence": "medium",
        "implementation_confidence": "high" if not any(
            item.validator == "comsol-readback" and not item.passed for item in record.checks
        ) else "low",
        "numerical_confidence": "low" if failed else "high",
    }
    updated = record.model_copy(update={"state": IterationState.ASSESSED, "assessment": assessment})
    return append_event(updated, actor="papersim", action="assess", stage="assessment", detail={"verdict": verdict})
