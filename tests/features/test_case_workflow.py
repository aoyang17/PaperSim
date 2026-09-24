from __future__ import annotations

from tests.conftest import snapshot_for

from papersim.case_workflow import CaseWorkflow


def test_fake_end_to_end_case_workflow(synthetic_case, tmp_path):
    store, layout, manifest, _, _ = synthetic_case
    workflow = CaseWorkflow(store.root)
    import pytest
    from papersim.contracts import StoreError

    with pytest.raises(StoreError):
        workflow.extract_ir(manifest.case_id, 1, "profiles/kobayashi1993_dendrite.json")
    workflow.approve_ir(
        manifest.case_id,
        1,
        approved_by="test-only:reviewer",
        reason="synthetic end-to-end fixture",
        test_only=True,
    )
    build_java, solve_java = workflow.generate_java(manifest.case_id, 1)
    build_mph = tmp_path / "fake_built.mph"
    build_mph.write_bytes(b"built" * 100)
    workflow.record_build(
        manifest.case_id,
        1,
        mph_path=build_mph,
        status="complete",
        exit_code=0,
        log_text="build complete",
    )
    snapshot = tmp_path / "snapshot.json"
    import json

    snapshot.write_text(json.dumps(snapshot_for(workflow.store.load_ir(manifest.case_id, 1))), encoding="utf-8")
    workflow.audit_implementation(manifest.case_id, 1, snapshot)
    solved_mph = tmp_path / "fake_solved.mph"
    solved_mph.write_bytes(b"solved" * 1_000_000)
    workflow.record_solve(
        manifest.case_id,
        1,
        mph_path=solved_mph,
        status="complete",
        exit_code=0,
        log_text="solve complete",
    )
    metrics = {
        "time.max": 1.4,
        "quality.p_min": -3.0e-6,
        "quality.p_max": 1.000001,
        "quality.max_relative_enthalpy_drift": 2.1e-13,
        "convergence.mesh_tip_relative_difference": 0.0035,
        "convergence.timestep_tip_relative_difference": 0.0,
        "convergence.seed_tip_relative_range": 0.0021,
        "paper_trend.delta050_to_delta000_tip_ratio": 1.85,
        "paper_trend.delta050_vertical_to_horizontal_extent_ratio": 2.01,
        "paper_figure.fig7_mean_iou": 0.328,
        "paper_figure.fig7_normalized_chamfer": 0.026,
    }
    workflow.audit_numeric(manifest.case_id, 1, metrics=metrics, log_text="solve complete")
    assessed = workflow.assess(manifest.case_id, 1)
    assert assessed.assessment["verdict"] == "qualified"
    report = workflow.report(manifest.case_id, 1)
    assert report.is_file()
    assert build_java.is_file()
    assert solve_java.is_file()
