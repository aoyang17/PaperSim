"""Case-directory layout and canonical JSON persistence for PaperSim."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterable, Mapping

from .case_contracts import (
    CASE_ID_RE,
    AuditRecord,
    CaseManifest,
    IR,
    IterationState,
    canonical_json_bytes,
    iteration_name,
    make_case_id,
    utc_now,
)
from .contracts import ContractError, StoreError
from .store import sha256


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json(path: Path, value: Mapping | object) -> Path:
    if hasattr(value, "model_dump"):
        payload = canonical_json_bytes(value.model_dump(mode="json"))
    else:
        payload = canonical_json_bytes(value)
    _atomic_write(path, payload)
    return path


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StoreError(f"canonical file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StoreError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StoreError(f"canonical JSON must be an object: {path}")
    return value


class CaseLayout:
    """Typed path helper for the only supported on-disk case layout."""

    def __init__(self, root: str | Path, case_id: str) -> None:
        if CASE_ID_RE.fullmatch(case_id) is None:
            raise ContractError(f"invalid case id: {case_id!r}")
        self.root = Path(root).expanduser().resolve()
        self.case_id = case_id
        self.directory = self.root / case_id

    @property
    def manifest(self) -> Path:
        return self.directory / "case.json"

    @property
    def paper(self) -> Path:
        return self.directory / f"{self.case_id}_paper.pdf"

    @property
    def report(self) -> Path:
        return self.directory / "report.html"

    def ir(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_ir.json"

    def audit(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_audit.json"

    def build_java(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_build.java"

    def solve_java(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_solve.java"

    def built_mph(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_built.mph"

    def solved_mph(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_solved.mph"

    def run_log(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_run.log"

    def results_csv(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_results.csv"

    def snapshot(self, iteration: int) -> Path:
        return self.directory / f"{iteration_name(iteration)}_snapshot.json"

    def assets(self, iteration: int) -> Path:
        return self.directory / f"{self.case_id}_{iteration_name(iteration)}_assets"

    def iteration_directories(self) -> Iterable[tuple[int, Path]]:
        for path in sorted(self.directory.glob("iter[0-9][0-9][0-9]_ir.json")):
            number = int(path.name[4:7])
            yield number, path

    def latest_iteration(self) -> int:
        numbers = [number for number, _ in self.iteration_directories()]
        return max(numbers, default=0)

    def core_files(self, iteration: int) -> tuple[Path, ...]:
        return (
            self.ir(iteration),
            self.audit(iteration),
            self.build_java(iteration),
            self.solve_java(iteration),
            self.built_mph(iteration),
            self.solved_mph(iteration),
            self.run_log(iteration),
            self.results_csv(iteration),
            self.snapshot(iteration),
        )


class CaseStore:
    """Canonical writer and reader for case directories."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def layout(self, case_id: str) -> CaseLayout:
        return CaseLayout(self.root, case_id)

    def list_cases(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and CASE_ID_RE.fullmatch(path.name) and (path / "case.json").is_file()
        )

    def create_case(
        self,
        *,
        surname: str,
        year: int,
        topic: str,
        paper: str | Path,
        title: str,
        goal: str,
    ) -> CaseManifest:
        case_id = make_case_id(surname, year, topic)
        layout = self.layout(case_id)
        source = Path(paper).expanduser().resolve()
        if not source.is_file():
            raise StoreError(f"paper does not exist: {source}")
        if layout.directory.exists():
            raise StoreError(f"case already exists: {case_id}")
        layout.directory.mkdir(parents=True)
        target = layout.paper
        try:
            shutil.copy2(source, target)
            manifest = CaseManifest(
                case_id=case_id,
                first_author_surname=surname.strip(),
                year=year,
                topic=topic.strip(),
                paper_filename=target.name,
                paper_sha256=sha256(target),
                title=title,
                goal=goal,
            )
            write_json(layout.manifest, manifest)
        except Exception:
            shutil.rmtree(layout.directory, ignore_errors=True)
            raise
        return manifest

    def require_case(self, case_id: str) -> tuple[CaseLayout, CaseManifest]:
        layout = self.layout(case_id)
        if not layout.manifest.is_file():
            raise StoreError(f"case is not registered: {case_id}")
        manifest = CaseManifest.model_validate(read_json(layout.manifest))
        if manifest.case_id != case_id:
            raise StoreError("case manifest id does not match directory")
        if not layout.paper.is_file() or sha256(layout.paper) != manifest.paper_sha256:
            raise StoreError(f"case paper is missing or changed: {layout.paper}")
        return layout, manifest

    def create_iteration(self, case_id: str, iteration: int) -> tuple[CaseLayout, AuditRecord]:
        layout, manifest = self.require_case(case_id)
        if layout.ir(iteration).exists() or layout.audit(iteration).exists():
            raise StoreError(f"iteration {iteration_name(iteration)} already exists")
        paper_hash = manifest.paper_sha256
        audit = AuditRecord(
            case_id=case_id,
            iteration=iteration,
            paper_sha256=paper_hash,
            profile_sha256="0" * 64,
            state=IterationState.CREATED,
        )
        write_json(layout.audit(iteration), audit)
        if iteration > manifest.latest_iteration:
            write_json(layout.manifest, manifest.model_copy(update={"latest_iteration": iteration, "state": "iteration_created"}))
        return layout, audit

    def write_ir(self, ir: IR) -> CaseLayout:
        layout, manifest = self.require_case(ir.case_id)
        if ir.paper_sha256 != manifest.paper_sha256:
            raise StoreError("IR paper hash does not match the current case paper")
        hashed = ir.with_hash()
        if not hashed.verify_hash():
            raise StoreError("IR hash could not be generated")
        write_json(layout.ir(ir.iteration), hashed)
        audit_path = layout.audit(ir.iteration)
        if audit_path.is_file():
            audit = AuditRecord.model_validate(read_json(audit_path))
        else:
            audit = AuditRecord(
                case_id=ir.case_id,
                iteration=ir.iteration,
                paper_sha256=ir.paper_sha256,
                profile_sha256=ir.profile_sha256,
                state=IterationState.CREATED,
            )
        audit = audit.model_copy(
            update={
                "state": IterationState.IR_EXTRACTED,
                "profile_sha256": ir.profile_sha256,
                "ir_sha256": hashed.ir_hash,
                "approval": None,
            }
        )
        write_json(audit_path, audit)
        return layout

    def load_ir(self, case_id: str, iteration: int) -> IR:
        layout, _ = self.require_case(case_id)
        ir = IR.model_validate(read_json(layout.ir(iteration)))
        if ir.case_id != case_id or ir.iteration != iteration:
            raise StoreError("IR identity does not match requested case/iteration")
        if not ir.verify_hash():
            raise StoreError("IR hash verification failed")
        return ir

    def load_audit(self, case_id: str, iteration: int) -> AuditRecord:
        layout, _ = self.require_case(case_id)
        return AuditRecord.model_validate(read_json(layout.audit(iteration)))

    def write_audit(self, audit: AuditRecord) -> CaseLayout:
        layout, _ = self.require_case(audit.case_id)
        write_json(layout.audit(audit.iteration), audit)
        return layout

    def discover_iteration(self, case_id: str, iteration: int | None = None) -> int:
        layout, manifest = self.require_case(case_id)
        selected = iteration or layout.latest_iteration()
        if selected < 1 or not layout.audit(selected).is_file():
            raise StoreError(f"case {case_id} has no iteration {selected}")
        if selected > manifest.latest_iteration:
            raise StoreError(f"iteration {selected} exceeds manifest latest iteration")
        return selected

    def mark_manifest_state(self, case_id: str, state: str) -> CaseManifest:
        layout, manifest = self.require_case(case_id)
        updated = manifest.model_copy(update={"state": state})
        write_json(layout.manifest, updated)
        return updated
