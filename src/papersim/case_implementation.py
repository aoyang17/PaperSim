"""COMSOL implementation audit against the approved IR."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .case_contracts import (
    AuditRecord,
    CheckResult,
    CheckStatus,
    IR,
    IterationState,
    append_event,
)
from .contracts import ContractError


RULE_VERSION = "papersim.comsol-implementation.v1"


def _check(entity_id: str, check_id: str, passed: bool, reason: str = "", unknown: bool = False) -> CheckResult:
    status = CheckStatus.PASS if passed else (CheckStatus.UNKNOWN if unknown else CheckStatus.FAIL)
    return CheckResult(
        entity_id=entity_id,
        check_id=check_id,
        validator="comsol-readback",
        status=status,
        reason="" if passed else reason,
        rule_version=RULE_VERSION,
    )


def _norm(value: Any) -> str:
    if isinstance(value, str):
        return "".join(value.split())
    return "".join(str(value).split())


def _nested(snapshot: Mapping[str, Any], path: str) -> Any:
    value: Any = snapshot
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def audit_implementation(record: AuditRecord, ir: IR, snapshot: Mapping[str, Any], *, build_source: str, solve_source: str) -> AuditRecord:
    if record.state not in {IterationState.BUILT, IterationState.IMPLEMENTATION_AUDITED}:
        raise ContractError("implementation audit requires a completed build")
    if build_source.count(".save(") != 1 or ".runAll(" in build_source or ".study(\"std1\").run()" in build_source:
        raise ContractError("build source violates build-only separation")
    if ".study(\"std1\").run()" not in solve_source or ".param().set(" in solve_source or ".physics()" in solve_source:
        raise ContractError("solve source violates solve-only separation")

    checks: list[CheckResult] = []
    expected_params = {item.comsol_name: item for item in ir.profile.parameters}
    actual_params = snapshot.get("parameters")
    if not isinstance(actual_params, Mapping):
        checks.append(_check(ir.case_id, "parameters_persisted", False, "snapshot.parameters is missing", True))
    else:
        missing = sorted(set(expected_params) - set(actual_params))
        changed = [
            name
            for name, item in expected_params.items()
            if name in actual_params
            and item.value is not None
            and item.expression is None
            and not _norm(actual_params[name]).startswith(_norm(item.value))
        ]
        checks.append(
            _check(
                ir.case_id,
                "parameters_persisted",
                not missing and not changed,
                f"missing={missing}; changed={changed}",
            )
        )

    expected_variables = {item.comsol_name: item for item in ir.profile.variables}
    actual_variables = snapshot.get("variables")
    if not isinstance(actual_variables, Mapping):
        checks.append(_check(ir.case_id, "variables_persisted", False, "snapshot.variables is missing", True))
    else:
        flattened: dict[str, Mapping[str, Any]] = {}
        for group, entries in actual_variables.items():
            if isinstance(entries, Mapping):
                for name, detail in entries.items():
                    if isinstance(detail, Mapping):
                        flattened[str(name)] = detail
                    else:
                        flattened[str(name)] = {"expression": detail}
        missing_vars = sorted(set(expected_variables) - set(flattened))
        expression_changes = [
            name
            for name, item in expected_variables.items()
            if name in flattened and _norm(flattened[name].get("expression")) != _norm(item.expression)
        ]
        missing_descriptions = [
            name for name, item in expected_variables.items() if not str(flattened.get(name, {}).get("description") or "").strip()
        ]
        checks.append(
            _check(
                ir.case_id,
                "variables_persisted",
                not missing_vars and not expression_changes and not missing_descriptions,
                f"missing={missing_vars}; changed={expression_changes}; missing_descriptions={missing_descriptions}",
            )
        )

    physics = snapshot.get("physics")
    expected_features = {
        feature
        for equation in ir.profile.equations
        for feature in equation.comsol_features
    }
    if not isinstance(physics, Mapping):
        checks.append(_check(ir.case_id, "physics_persisted", False, "snapshot.physics is missing", True))
    else:
        missing_physics = sorted(expected_features - set(physics))
        unit_failures: list[str] = []
        for feature in expected_features:
            detail = physics.get(feature) or {}
            if not isinstance(detail, Mapping):
                unit_failures.append(feature)
                continue
            units = detail.get("units") or {}
            if not units.get("dependent_unit") or not units.get("source_unit"):
                unit_failures.append(feature)
        checks.append(
            _check(
                ir.case_id,
                "physics_persisted",
                not missing_physics and not unit_failures,
                f"missing={missing_physics}; unit_failures={unit_failures}",
            )
        )

    sweep = _nested(snapshot, "study.parametric")
    solver_settings = ir.profile.solver.settings
    expected_values = [float(value) for value in solver_settings.get("delta_values", [])]
    try:
        actual_values = [float(value) for value in sweep.get("values", [])] if isinstance(sweep, Mapping) else []
    except (TypeError, ValueError):
        actual_values = []
    sweep_ok = (
        isinstance(sweep, Mapping)
        and sweep.get("parameter") == "delta"
        and actual_values == expected_values
    )
    checks.append(_check(ir.case_id, "parametric_sweep", sweep_ok, "parametric delta sweep does not match IR"))

    expected_boundary_count = len(ir.profile.boundary_conditions)
    expected_initial_count = len(ir.profile.initial_conditions)
    persisted_boundaries = [item for item in snapshot.get("boundary_conditions", []) if isinstance(item, Mapping)]
    persisted_initials = [item for item in snapshot.get("initial_conditions", []) if isinstance(item, Mapping)]
    boundary_ok = len(persisted_boundaries) == expected_boundary_count and all(
        "zero flux" in str(item.get("type") or "").lower() for item in persisted_boundaries
    )
    initial_ok = len(persisted_initials) == expected_initial_count and all(
        "initial" in str(item.get("type") or "").lower() for item in persisted_initials
    )
    checks.append(
        _check(
            ir.case_id,
            "boundary_initial_persisted",
            boundary_ok and initial_ok,
            f"expected {expected_boundary_count} zero-flux boundaries and {expected_initial_count} initial-value features; got boundaries={len(persisted_boundaries)}, initials={len(persisted_initials)}",
        )
    )

    mesh = snapshot.get("mesh")
    mesh_ok = isinstance(mesh, Mapping) and str(mesh.get("type") or "").lower() in {"mapped", "map"}
    checks.append(_check(ir.case_id, "mesh_persisted", mesh_ok, "mapped mesh was not persisted"))

    solver = snapshot.get("solver")
    solver_ok = (
        isinstance(solver, Mapping)
        and _norm(solver.get("method")) == "bdf"
        and abs(float(solver.get("rtol", -1)) - float(solver_settings.get("rtol", -2))) <= 1e-12
        and abs(float(solver.get("tfinal", -1)) - float(solver_settings.get("tfinal", -2))) <= 1e-12
    )
    checks.append(_check(ir.case_id, "solver_persisted", solver_ok, "solver settings do not match IR"))

    updated = record.model_copy(
        update={
            "state": IterationState.IMPLEMENTATION_AUDITED,
            "comsol_snapshot": dict(snapshot),
        }
    )
    combined = tuple(item for item in record.checks if item.validator != "comsol-readback") + tuple(checks)
    updated = updated.model_copy(update={"checks": combined})
    updated = append_event(updated, actor="papersim", action="audit_implementation", stage="implementation", detail={"checks": len(checks)})
    return updated
