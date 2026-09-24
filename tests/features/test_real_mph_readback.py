from __future__ import annotations

import os
from pathlib import Path

import pytest

from papersim.case_implementation import audit_implementation
from papersim.case_mph import read_mph_snapshot
from papersim.case_store import CaseStore


@pytest.mark.comsol
def test_real_kobayashi_mph_readback(tmp_path: Path):
    workspace = os.environ.get("PAPERSIM_KOBAYASHI_WORKSPACE")
    if not workspace:
        pytest.skip("set PAPERSIM_KOBAYASHI_WORKSPACE to run real MPH readback")
    store = CaseStore(workspace)
    layout, _ = store.require_case("kobayashi1993_dendrite")
    ir = store.load_ir("kobayashi1993_dendrite", 1)
    record = store.load_audit("kobayashi1993_dendrite", 1)
    snapshot = read_mph_snapshot(layout.built_mph(1))
    updated = audit_implementation(
        record,
        ir,
        snapshot,
        build_source=layout.build_java(1).read_text(encoding="utf-8"),
        solve_source=layout.solve_java(1).read_text(encoding="utf-8"),
    )
    implementation = [item for item in updated.checks if item.validator == "comsol-readback"]
    assert implementation and all(item.passed for item in implementation)
