from __future__ import annotations

from pathlib import Path

import pytest

from papersim.case_store import CaseStore
from papersim.contracts import StoreError


def test_create_case_uses_only_canonical_names(tmp_path: Path):
    paper = tmp_path / "input.pdf"
    paper.write_bytes(b"%PDF-1.4 synthetic")
    store = CaseStore(tmp_path / "workspace")
    manifest = store.create_case(
        surname="Kobayashi",
        year=1993,
        topic="dendrite",
        paper=paper,
        title="title",
        goal="goal",
    )
    case_dir = tmp_path / "workspace" / manifest.case_id
    assert case_dir.name == "kobayashi1993_dendrite"
    assert (case_dir / "case.json").is_file()
    assert (case_dir / "kobayashi1993_dendrite_paper.pdf").is_file()
    assert manifest.paper_filename == "kobayashi1993_dendrite_paper.pdf"


def test_duplicate_or_tampered_case_fails(tmp_path: Path):
    paper = tmp_path / "input.pdf"
    paper.write_bytes(b"%PDF-1.4 synthetic")
    store = CaseStore(tmp_path / "workspace")
    manifest = store.create_case(surname="Kobayashi", year=1993, topic="dendrite", paper=paper, title="title", goal="goal")
    with pytest.raises(StoreError):
        store.create_case(surname="Kobayashi", year=1993, topic="dendrite", paper=paper, title="title", goal="goal")
    target = tmp_path / "workspace" / manifest.case_id / manifest.paper_filename
    target.write_bytes(b"changed")
    with pytest.raises(StoreError):
        store.require_case(manifest.case_id)
