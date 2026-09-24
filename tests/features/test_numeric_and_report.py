from __future__ import annotations

from pathlib import Path

from papersim.case_numeric import assess, audit_numeric, criterion_pass, parse_tidy_csv, summarize_rows
from papersim.case_report import generate_report
from papersim.case_contracts import IterationState


def _passing_metrics():
    return {
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


def test_criterion_evaluation_and_tidy_csv():
    assert criterion_pass(0.0, {"operator": "==", "expected": 0})[0]
    assert criterion_pass(1.85, {"operator": ">", "expected": 1.02})[0]
    text = "case_id,iteration,stage,source,delta,time,metric,value,unit\nkobayashi1993_dendrite,1,solve,comsol,0,1.4,tipY,4.8,m\n"
    rows = parse_tidy_csv(text)
    assert rows[0]["metric"] == "tipY"
    summary = summarize_rows(rows)
    assert summary["time.max"] == 1.4


def test_numeric_audit_and_assessment(synthetic_case):
    _, layout, _, audit, ir = synthetic_case
    solved = audit.model_copy(update={"state": IterationState.SOLVED})
    layout.solved_mph(1).write_bytes(b"x" * 2_000_000)
    updated = audit_numeric(
        solved,
        ir,
        metrics=_passing_metrics(),
        solver_status="complete",
        solver_exit_code=0,
        log_text="COMSOL completed",
        solved_mph_size=layout.solved_mph(1).stat().st_size,
    )
    assert all(item.passed for item in updated.numerical_checks)
    assessed = assess(updated, ir)
    assert assessed.assessment["verdict"] == "qualified"


def test_report_is_offline_and_contains_required_sections(synthetic_case, tmp_path: Path):
    _, _, manifest, audit, ir = synthetic_case
    output = tmp_path / "report.html"
    generate_report(manifest, ir, audit, output=output)
    text = output.read_text(encoding="utf-8")
    assert "equation-to-feature" in text.lower() or "COMSOL feature" in text
    assert "模型审计清单" in text
    assert "Nomenclature" in text
    assert "MathJax" not in text
    assert "https://" not in text
    assert "$$" not in text
