from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import ContractError, SolverBackend


def flatten_metrics(metrics: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in metrics.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flattened.update(flatten_metrics(value, path))
        else:
            flattened[path] = value
    return flattened


def first_metric(metrics: Mapping[str, Any], candidates: list[str]) -> Any:
    flattened = flatten_metrics(metrics)
    for candidate in candidates:
        if candidate in flattened:
            return flattened[candidate]
    return None


class FakeSolver:
    """Deterministic local solver used to prove the core contract without COMSOL."""

    adapter_name = "fake"
    adapter_version = "1.0"

    def __init__(self, *, metrics: Mapping[str, Any] | None = None, fail: bool = False) -> None:
        self.metrics = dict(metrics or {})
        self.fail = fail
        self._submissions: dict[str, dict[str, Any]] = {}

    def validate(self, model: Any) -> None:
        spec = model.data.get("model_spec", {}) if hasattr(model, "data") else {}
        if spec.get("solver", {}).get("backend") not in {None, "fake"}:
            # A fake backend is intentionally allowed to stand in for any
            # declared backend in contract tests; the declaration is still
            # carried into the canonical Run.
            return None

    def _derived_metrics(self, model: Any) -> dict[str, Any]:
        if self.metrics:
            return dict(self.metrics)
        spec = model.data.get("model_spec", {}) if hasattr(model, "data") else {}
        configured = spec.get("solver", {}).get("fake_metrics") if isinstance(spec.get("solver"), Mapping) else None
        if isinstance(configured, Mapping):
            return dict(configured)
        values: dict[str, Any] = {}
        for parameter in spec.get("parameters", []):
            if isinstance(parameter, dict):
                values[str(parameter.get("id"))] = parameter.get("value")
        simulated = values.get("simulated_value")
        if simulated is None:
            simulated = values.get("value")
        if simulated is None:
            simulated = 0.0
        outputs = spec.get("outputs", [])
        metric_name = "simulation.value"
        if outputs and isinstance(outputs[0], dict):
            first = outputs[0]
            metric_name = str(first.get("metric") or first.get("id") or metric_name)
        return {
            "simulation": {
                "value": simulated,
                "status": 0 if self.fail else 1,
            },
            metric_name: simulated,
        }

    def build(self, model: Any, run_id: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "model_id": model.id,
            "model_bundle": model.data.get("model_spec", {}),
        }

    def submit(self, model: Any, run_id: str) -> dict[str, Any]:
        metrics = self._derived_metrics(model)
        result = {
            "status": "failed" if self.fail else "complete",
            "exit_code": 1 if self.fail else 0,
            "solver": self.adapter_name,
            "solver_version": self.adapter_version,
            "environment": {"kind": "local", "executable": "fake"},
            "metrics": metrics,
        }
        self._submissions[run_id] = result
        return result

    def status(self, run_id: str) -> dict[str, Any]:
        return dict(self._submissions.get(run_id, {"status": "unknown", "exit_code": None}))

    def collect(self, run_id: str) -> dict[str, Any]:
        result = dict(self._submissions.get(run_id, {}))
        result.setdefault("artifacts", [])
        result.setdefault("logs", ["fake solver completed"])
        return result


def validate_run_backend(backend: Any) -> SolverBackend:
    required = ("validate", "build", "submit", "status", "collect")
    missing = [name for name in required if not callable(getattr(backend, name, None))]
    if missing:
        raise ContractError("solver backend is missing methods: " + ", ".join(missing))
    return backend


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    exit_code: int | None
    metrics: Mapping[str, Any]
