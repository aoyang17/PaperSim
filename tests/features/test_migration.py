from __future__ import annotations

from pathlib import Path

from papersim.case_migration import apply_workspace_migration, plan_workspace_migration


def test_migration_plan_uses_canonical_names(tmp_path: Path):
    old = tmp_path / "kobayashi1993"
    old.mkdir()
    (old / "Kobayashi1993_paper.pdf").write_bytes(b"paper")
    (old / "kobayashi1993.mph").write_bytes(b"mph")
    (old / "kobayashi1993_papersim_report.html").write_text("report")
    (old / "kobayashi1993_charts").mkdir()
    actions = plan_workspace_migration(tmp_path)
    kinds = [item.kind for item in actions]
    assert kinds == ["case_directory", "paper", "legacy_mph", "legacy_report", "legacy_assets"]


def test_migration_is_hash_preserving_and_idempotent(tmp_path: Path):
    old = tmp_path / "kobayashi1993"
    old.mkdir()
    (old / "Kobayashi1993_paper.pdf").write_bytes(b"paper")
    (old / "kobayashi1993.mph").write_bytes(b"mph")
    (old / "kobayashi1993_papersim_report.html").write_text("report")
    (old / "kobayashi1993_charts").mkdir()
    first = apply_workspace_migration(tmp_path)
    second = apply_workspace_migration(tmp_path)
    assert first
    assert second == []
    case = tmp_path / "kobayashi1993_dendrite"
    assert (case / "kobayashi1993_dendrite_paper.pdf").read_bytes() == b"paper"
    assert (case / "case.json").is_file()
