from __future__ import annotations

from typing import Any, Mapping

from .compare import metric_value
from .contracts import ContractError

VERDICTS = {"supported", "qualified", "questioned", "not_reproduced", "underdetermined"}


def _criterion_pass(actual: Any, criterion: Mapping[str, Any]) -> tuple[bool, str]:
    operator = str(criterion.get("operator") or "")
    expected = criterion.get("expected")
    try:
        if operator == "between":
            low, high = expected
            passed = float(low) <= float(actual) <= float(high)
        elif operator == "relative_error_le":
            tolerance = float(criterion.get("tolerance", expected))
            passed = abs(float(actual) - float(expected)) / max(abs(float(expected)), 1e-12) <= tolerance
        elif operator == "<":
            passed = actual < expected
        elif operator == "<=":
            passed = actual <= expected
        elif operator == ">":
            passed = actual > expected
        elif operator == ">=":
            passed = actual >= expected
        elif operator == "==":
            passed = actual == expected
        else:
            return False, f"unsupported acceptance operator: {operator}"
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        return False, f"invalid acceptance criterion: {exc}"
    return bool(passed), "pass" if passed else "value does not satisfy criterion"


def build_assessment(
    *,
    case: Mapping[str, Any],
    model: Mapping[str, Any],
    run: Mapping[str, Any],
    compare: Mapping[str, Any],
    model_spec: Mapping[str, Any],
) -> dict[str, Any]:
    if run.get("status") != "complete" or run.get("exit_code") != 0:
        raise ContractError("assessment requires a complete run with exit_code 0")
    criteria = model_spec.get("acceptance", [])
    if not isinstance(criteria, list) or not criteria:
        raise ContractError("assessment requires at least one acceptance criterion")
    findings: list[dict[str, Any]] = []
    required: list[bool] = []
    for criterion in criteria:
        if not isinstance(criterion, Mapping):
            raise ContractError("acceptance criteria must be objects")
        actual = metric_value(compare.get("metrics", {}), str(criterion["metric"]))
        passed, message = _criterion_pass(actual, criterion)
        is_required = bool(criterion.get("required", True))
        if is_required:
            required.append(passed)
        findings.append(
            {
                "id": str(criterion["id"]),
                "criterion": dict(criterion),
                "metric": str(criterion["metric"]),
                "actual": actual,
                "passed": passed,
                "required": is_required,
                "message": message,
            }
        )
    mismatches = list(compare.get("mismatches", []))
    for mismatch in mismatches:
        findings.append(
            {
                "id": str(mismatch.get("id") or "mismatch"),
                "kind": "observation_mismatch",
                "metric": mismatch.get("metric"),
                "actual": mismatch.get("simulated"),
                "observed": mismatch.get("observed"),
                "passed": False,
                "required": True,
                "message": str(mismatch.get("reason") or "paper observation and simulation differ"),
            }
        )
    all_pass = bool(required) and all(required)
    if not required:
        verdict = "underdetermined"
    elif mismatches:
        verdict = "questioned" if all_pass else "not_reproduced"
    else:
        assessment = model_spec.get("assessment", {})
        verdict = str(assessment.get("verdict_on_pass" if all_pass else "verdict_on_fail") or ("qualified" if all_pass else "not_reproduced"))
    if verdict not in VERDICTS:
        raise ContractError(f"invalid assessment verdict: {verdict}")
    if mismatches or not findings:
        confidence = "low"
    elif any(not item["passed"] for item in findings):
        confidence = "medium"
    else:
        confidence = "high"
    unresolved = list(model_spec.get("unresolved_questions", []))
    for mismatch in mismatches:
        unresolved.append(f"mismatch {mismatch.get('id', 'unknown')}: {mismatch.get('reason', 'review required')}")
    return {
        "case_id": case["id"],
        "baseline_run_id": run["id"],
        "model_ids": list(case.get("model_ids", [])),
        "run_ids": list(case.get("run_ids", [])),
        "compare_ids": list(case.get("compare_ids", [])),
        "acceptance": [dict(item) for item in criteria],
        "verdict": verdict,
        "findings": findings,
        "confidence": confidence,
        "scope": str(model_spec.get("scope") or "declared model and tested conditions"),
        "unresolved_questions": sorted(set(str(item) for item in unresolved)),
        "model_id": model["id"],
        "run_id": run["id"],
        "compare_id": compare["id"],
        "interpretation": compare.get("interpretation", ""),
    }
