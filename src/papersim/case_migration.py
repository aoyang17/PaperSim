"""One-time, hash-preserving migration to the canonical case layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Iterable

from .case_contracts import CaseManifest
from .case_store import write_json
from .contracts import StoreError
from .store import sha256


@dataclass(frozen=True)
class MigrationAction:
    source: Path
    target: Path
    kind: str

    def as_dict(self) -> dict[str, str]:
        return {"source": str(self.source), "target": str(self.target), "kind": self.kind}


CASE_RENAMES = {
    "kobayashi1993": "kobayashi1993_dendrite",
    "huang2013": "huang2013_lithiation",
    "chen2014": "chen2014_elastoplastic",
}

PROFILE_RENAMES = {
    "huang2013.json": "huang2013_lithiation.json",
    "chen2014.json": "chen2014_elastoplastic.json",
}


def _move_action(source: Path, target: Path, kind: str) -> MigrationAction | None:
    if not source.exists():
        if target.exists():
            return None
        raise StoreError(f"migration source is missing: {source}")
    if target.exists():
        raise StoreError(f"migration target already exists: {target}")
    return MigrationAction(source, target, kind)


def plan_workspace_migration(root: str | Path) -> list[MigrationAction]:
    root = Path(root).expanduser().resolve()
    actions: list[MigrationAction] = []
    for old, new in CASE_RENAMES.items():
        old_dir = root / old
        new_dir = root / new
        if not old_dir.exists():
            continue
        action = _move_action(old_dir, new_dir, "case_directory")
        if action:
            actions.append(action)
        working = old_dir if action else new_dir
        if old == "kobayashi1993":
            actions.extend(
                item
                for item in (
                    _move_action(working / "Kobayashi1993_paper.pdf", new_dir / f"{new}_paper.pdf", "paper"),
                    _move_action(working / "kobayashi1993.mph", new_dir / f"{new}_legacy_solved.mph", "legacy_mph"),
                    _move_action(working / "kobayashi1993_papersim_report.html", new_dir / f"{new}_legacy_report.html", "legacy_report"),
                    _move_action(working / "kobayashi1993_charts", new_dir / f"{new}_legacy_assets", "legacy_assets"),
                )
                if item is not None
            )
        else:
            old_paper = working / f"{old}_paper.pdf"
            actions.extend(
                item
                for item in (_move_action(old_paper, new_dir / f"{new}_paper.pdf", "paper"),)
                if item is not None
            )
    return actions


def plan_profile_migration(profile_dir: str | Path) -> list[MigrationAction]:
    root = Path(profile_dir).expanduser().resolve()
    actions: list[MigrationAction] = []
    for old, new in PROFILE_RENAMES.items():
        action = _move_action(root / old, root / new, "profile")
        if action:
            actions.append(action)
    return actions


def _apply(actions: Iterable[MigrationAction], *, dry_run: bool) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    queued = list(actions)
    index = 0
    renames: list[tuple[Path, Path]] = []
    while index < len(queued):
        action = queued[index]
        source = action.source
        target = action.target
        for old_prefix, new_prefix in renames:
            try:
                relative = source.relative_to(old_prefix)
                source = new_prefix / relative
            except ValueError:
                pass
            try:
                relative = target.relative_to(old_prefix)
                target = new_prefix / relative
            except ValueError:
                pass
        rewritten = MigrationAction(source, target, action.kind)
        if not dry_run:
            before = sha256(rewritten.source) if rewritten.source.is_file() else ""
            rewritten.source.rename(rewritten.target)
            if before and sha256(rewritten.target) != before:
                raise StoreError(f"hash changed during migration: {rewritten.source} -> {rewritten.target}")
            if rewritten.kind == "case_directory":
                renames.append((rewritten.source, rewritten.target))
        records.append(rewritten.as_dict())
        index += 1
    return records


def create_kobayashi_manifest(workspace_root: str | Path) -> CaseManifest:
    root = Path(workspace_root).expanduser().resolve()
    case_id = "kobayashi1993_dendrite"
    case_dir = root / case_id
    manifest_path = case_dir / "case.json"
    if manifest_path.exists():
        return CaseManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    paper = case_dir / f"{case_id}_paper.pdf"
    if not paper.is_file():
        raise StoreError(f"migrated Kobayashi paper is missing: {paper}")
    legacy = {}
    for key, filename in (
        ("solved_mph", f"{case_id}_legacy_solved.mph"),
        ("report", f"{case_id}_legacy_report.html"),
        ("assets", f"{case_id}_legacy_assets"),
    ):
        path = case_dir / filename
        if path.exists():
            legacy[key] = filename
    manifest = CaseManifest(
        case_id=case_id,
        first_author_surname="Kobayashi",
        year=1993,
        topic="dendrite",
        paper_filename=paper.name,
        paper_sha256=sha256(paper),
        title="Modeling and numerical simulations of dendritic crystal growth",
        goal="Reproduce Eqs. (3)-(5), the delta sweep in Fig. 7, and the declared numerical reliability checks.",
        state="migrated_legacy_only",
        legacy_artifacts=legacy,
    )
    write_json(manifest_path, manifest)
    return manifest


def apply_workspace_migration(workspace_root: str | Path, *, dry_run: bool = False) -> list[dict[str, str]]:
    actions = plan_workspace_migration(workspace_root)
    records = _apply(actions, dry_run=dry_run)
    if not dry_run:
        create_kobayashi_manifest(workspace_root)
    return records


def apply_profile_migration(profile_dir: str | Path, *, dry_run: bool = False) -> list[dict[str, str]]:
    return _apply(plan_profile_migration(profile_dir), dry_run=dry_run)
