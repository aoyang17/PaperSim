from __future__ import annotations

from tests.conftest import snapshot_for

from papersim.case_contracts import IterationState
from papersim.case_implementation import audit_implementation


def test_implementation_snapshot_matches_ir(synthetic_case):
    _, layout, _, audit, ir = synthetic_case
    built_audit = audit.model_copy(update={"state": IterationState.BUILT})
    updated = audit_implementation(
        built_audit,
        ir,
        snapshot_for(ir),
        build_source=layout.build_java(1).read_text(encoding="utf-8") if layout.build_java(1).exists() else "m.save(\"built.mph\");",
        solve_source="model.study(\"std1\").run(); model.save(\"solved.mph\");",
    )
    implementation = [item for item in updated.checks if item.validator == "comsol-readback"]
    assert implementation and all(item.passed for item in implementation)


def test_implementation_detects_changed_variable(synthetic_case):
    _, layout, _, audit, ir = synthetic_case
    snapshot = snapshot_for(ir)
    first_group = next(iter(snapshot["variables"]))
    first_name = next(iter(snapshot["variables"][first_group]))
    snapshot["variables"][first_group][first_name]["expression"] = "tampered"
    built_audit = audit.model_copy(update={"state": IterationState.BUILT})
    updated = audit_implementation(
        built_audit,
        ir,
        snapshot,
        build_source="m.save(\"built.mph\");",
        solve_source="model.study(\"std1\").run(); model.save(\"solved.mph\");",
    )
    implementation = [item for item in updated.checks if item.validator == "comsol-readback"]
    assert any(not item.passed for item in implementation)
