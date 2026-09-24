from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from papersim.case_audit import SyntheticEvidenceVerifier, audit_profile
from papersim.case_contracts import IR, ProfileModel
from papersim.case_store import CaseStore


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def kobayashi_profile(repo_root: Path) -> ProfileModel:
    return ProfileModel.model_validate_json(
        (repo_root / "profiles" / "kobayashi1993_dendrite.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def synthetic_case(tmp_path: Path, kobayashi_profile: ProfileModel):
    workspace = tmp_path / "workspace"
    paper = tmp_path / "source.pdf"
    paper.write_bytes(b"%PDF-1.4\nPaperSim synthetic fixture\n%%EOF\n")
    store = CaseStore(workspace)
    manifest = store.create_case(
        surname="Kobayashi",
        year=1993,
        topic="dendrite",
        paper=paper,
        title="Modeling and numerical simulations of dendritic crystal growth",
        goal="Contract fixture for case workflow tests.",
    )
    layout, _ = store.create_iteration(manifest.case_id, 1)
    audit, evidence = audit_profile(
        case_id=manifest.case_id,
        iteration=1,
        paper_sha256=manifest.paper_sha256,
        profile_sha256="a" * 64,
        profile=kobayashi_profile,
        verifier=SyntheticEvidenceVerifier(manifest.paper_sha256),
    )
    ir = IR(
        case_id=manifest.case_id,
        iteration=1,
        paper_filename=layout.paper.name,
        paper_sha256=manifest.paper_sha256,
        profile_sha256="a" * 64,
        scope=kobayashi_profile.scope,
        profile=kobayashi_profile,
        evidence=evidence,
    ).with_hash()
    store.write_ir(ir)
    store.write_audit(audit.model_copy(update={"ir_sha256": ir.ir_hash}))
    return store, layout, manifest, audit, ir


def snapshot_for(ir: IR) -> dict:
    return {
        "model_name": "Kobayashi1993Dendrite",
        "parameters": {item.comsol_name: item.expression or item.value for item in ir.profile.parameters},
        "variables": {
            group: {
                item.comsol_name: {"expression": item.expression, "description": item.description}
                for item in ir.profile.variables
                if item.group == group
            }
            for group in sorted({item.group for item in ir.profile.variables})
        },
        "physics": {
            feature: {
                "type": "GeneralFormPDE",
                "units": {"dependent_unit": "1", "source_unit": "1/s"},
            }
            for feature in {
                feature
                for equation in ir.profile.equations
                for feature in equation.comsol_features
            }
        },
        "boundary_conditions": [{"id": item.id, "type": "Zero Flux 1"} for item in ir.profile.boundary_conditions],
        "initial_conditions": [{"id": item.id, "type": "Initial Values 1"} for item in ir.profile.initial_conditions],
        "mesh": {"type": "Mapped", "elements_per_axis": 300},
        "study": {
            "parametric": {
                "parameter": "delta",
                "values": ir.profile.solver.settings["delta_values"],
            }
        },
        "solver": {
            "method": "bdf",
            "rtol": ir.profile.solver.settings["rtol"],
            "tfinal": ir.profile.solver.settings["tfinal"],
        },
    }
