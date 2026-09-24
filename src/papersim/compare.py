from __future__ import annotations

from typing import Any, Mapping

from .contracts import ContractError
from .run import flatten_metrics


def metric_value(metrics: Mapping[str, Any], dotted: str) -> Any:
    if dotted in metrics:
        return metrics[dotted]
    value: Any = metrics
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def _observation_value(observation: Mapping[str, Any]) -> Any:
    return observation.get("value")


def _metric_for_observation(observation: Mapping[str, Any], model_spec: Mapping[str, Any], metrics: Mapping[str, Any]) -> tuple[str, Any]:
    observation_id = str(observation["id"])
    candidates = [
        str(observation.get("metric") or ""),
        str(observation.get("simulated_metric") or ""),
        str(observation_id),
    ]
    outputs = model_spec.get("outputs", [])
    for output in outputs:
        if not isinstance(output, Mapping):
            continue
        if str(output.get("observation_id") or "") == observation_id:
            candidates.insert(0, str(output.get("metric") or output.get("id") or ""))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return candidate, metric_value(metrics, candidate)
        except KeyError:
            continue
    raise ContractError(f"no simulated metric found for observation {observation_id}")


def calculate_compare(
    *,
    case: Mapping[str, Any],
    model_id: str,
    run_id: str,
    model_spec: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    observations = case.get("reference_observations", [])
    if not observations:
        raise ContractError("compare requires reference observations on the Case")
    observed: dict[str, Any] = {}
    simulated: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    uncertainty: list[dict[str, Any]] = []
    evidence: list[str] = []

    criteria = [item for item in model_spec.get("acceptance", []) if isinstance(item, Mapping)]
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise ContractError("case reference observations must be objects")
        observation_id = str(observation.get("id") or "")
        if not observation_id:
            raise ContractError("reference observation requires an id")
        observed_value = _observation_value(observation)
        metric, simulated_value = _metric_for_observation(observation, model_spec, metrics)
        observed[observation_id] = observed_value
        simulated[observation_id] = simulated_value
        if isinstance(observed_value, (int, float)) and not isinstance(observed_value, bool) and isinstance(simulated_value, (int, float)) and not isinstance(simulated_value, bool):
            absolute_error = float(simulated_value) - float(observed_value)
            relative_error = abs(absolute_error) / max(abs(float(observed_value)), 1e-12)
        else:
            absolute_error = None
            relative_error = None
        errors[observation_id] = {
            "absolute": absolute_error,
            "relative": relative_error,
            "metric": metric,
        }
        criterion = next(
            (
                item
                for item in criteria
                if str(item.get("metric") or "") == metric
                or str(item.get("observation_id") or "") == observation_id
                or str(item.get("id") or "") == observation_id
            ),
            None,
        )
        criterion_passed = True
        criterion_evaluated = criterion is not None
        tolerance = None
        if criterion is not None:
            tolerance = criterion.get("tolerance")
            operator = str(criterion.get("operator") or "")
            expected = criterion.get("expected", observed_value)
            try:
                if operator == "between":
                    low, high = expected
                    criterion_passed = float(low) <= float(simulated_value) <= float(high)
                elif operator == "relative_error_le":
                    tolerance = float(tolerance if tolerance is not None else expected)
                    criterion_passed = relative_error is not None and relative_error <= tolerance
                elif operator == "<":
                    criterion_passed = simulated_value < expected
                elif operator == "<=":
                    criterion_passed = simulated_value <= expected
                elif operator == ">":
                    criterion_passed = simulated_value > expected
                elif operator == ">=":
                    criterion_passed = simulated_value >= expected
                elif operator == "==":
                    criterion_passed = simulated_value == expected
                else:
                    criterion_passed = False
            except (TypeError, ValueError, ZeroDivisionError):
                criterion_passed = False

        # A compare is not complete merely because a broad acceptance bound
        # passes: it must also account for the paper observation itself.
        observation_passed = criterion_passed
        if absolute_error is not None and criterion is not None:
            operator = str(criterion.get("operator") or "")
            if operator == "relative_error_le":
                observation_passed = relative_error is not None and relative_error <= float(tolerance)
            elif operator == "between":
                low, high = criterion.get("expected", (observed_value, observed_value))
                observation_passed = float(low) <= float(simulated_value) <= float(high)
            else:
                comparison_tolerance = float(tolerance if tolerance is not None else 1e-9)
                observation_passed = abs(absolute_error) <= comparison_tolerance
        passed = bool(criterion_passed and observation_passed)
        if not passed:
            reason = "simulated value does not satisfy the declared model acceptance criterion"
            if criterion_evaluated and criterion_passed and not observation_passed:
                reason = "simulated value passes the acceptance bound but differs from the paper observation beyond tolerance"
            elif not criterion_evaluated:
                reason = "simulated value differs from the paper observation and no acceptance criterion was supplied"
            mismatches.append(
                {
                    "id": f"mismatch-{observation_id}",
                    "observation_id": observation_id,
                    "metric": metric,
                    "observed": observed_value,
                    "simulated": simulated_value,
                    "error": errors[observation_id],
                    "criterion_id": criterion.get("id") if criterion else None,
                    "criterion_passed": criterion_passed if criterion_evaluated else None,
                    "tolerance": tolerance,
                    "reason": reason,
                }
            )
        uncertainty.append(
            {
                "id": f"uncertainty-{observation_id}",
                "observation_id": observation_id,
                "kind": observation.get("uncertainty_kind", "not_quantified"),
                "value": observation.get("uncertainty"),
                "note": observation.get("uncertainty_note", "not reported by the model spec"),
            }
        )
        evidence.append(observation_id)
    if not mismatches:
        interpretation = "all reference observations are within the declared model acceptance criteria"
    elif all(item.get("criterion_passed") is True for item in mismatches):
        interpretation = f"{len(mismatches)} reference observation(s) differ from the paper result even though the acceptance bounds pass"
    else:
        interpretation = f"{len(mismatches)} reference observation(s) do not satisfy the declared acceptance criteria"
    return {
        "case_id": case["id"],
        "model_id": model_id,
        "run_id": run_id,
        "observation_ids": [str(item["id"]) for item in observations],
        "observed": observed,
        "simulated": simulated,
        "errors": errors,
        "metrics": dict(metrics),
        "mismatches": mismatches,
        "uncertainty": uncertainty,
        "evidence": sorted(set(evidence)),
        "interpretation": interpretation,
    }
