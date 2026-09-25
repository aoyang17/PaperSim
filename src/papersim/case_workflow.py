"""High-level Python workflow for case directories and fail-closed gates."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from .case_audit import PdfEvidenceVerifier, approve, audit_profile, build_ir, ensure_approved
from .case_contracts import (
    AuditRecord,
    CheckStatus,
    IR,
    IterationState,
    ProfileModel,
    append_event,
    canonical_json_bytes,
    sha256_bytes,
)
from .case_implementation import audit_implementation
from .case_java import generate_iteration_java
from .case_mph import read_mph_snapshot
from .case_numeric import assess, audit_numeric, parse_comsol_table_csv, parse_tidy_csv, summarize_rows
from .case_report import generate_report
from .case_store import CaseStore, write_json
from .contracts import ContractError, StoreError
from .documents import PdfDocument
from .store import sha256


class CaseWorkflow:
    def __init__(self, root: str | Path) -> None:
        self.store = CaseStore(root)

    def create_case(self, **kwargs: Any):
        return self.store.create_case(**kwargs)

    def create_iteration(self, case_id: str, iteration: int):
        return self.store.create_iteration(case_id, iteration)

    def extract_ir(self, case_id: str, iteration: int, profile_path: str | Path) -> IR:
        layout, manifest = self.store.require_case(case_id)
        if layout.ir(iteration).exists():
            raise StoreError(f"iteration {iteration:03d} already has an immutable IR")
        profile_file = Path(profile_path).expanduser().resolve()
        if not profile_file.is_file():
            raise StoreError(f"profile does not exist: {profile_file}")
        profile = ProfileModel.model_validate_json(profile_file.read_text(encoding="utf-8"))
        if profile.case_id != case_id:
            raise ContractError("profile case_id does not match requested case")
        profile_hash = sha256(profile_file)
        document = PdfDocument(layout.paper)
        try:
            if document.sha256 != manifest.paper_sha256:
                raise StoreError("case paper changed before extraction")
            audit, evidence = audit_profile(
                case_id=case_id,
                iteration=iteration,
                paper_sha256=manifest.paper_sha256,
                profile_sha256=profile_hash,
                profile=profile,
                verifier=PdfEvidenceVerifier(document),
            )
        finally:
            document.close()
        failing = [item.check_id for item in audit.checks if not item.passed]
        if failing:
            blocked = audit.model_copy(update={"state": IterationState.BLOCKED})
            blocked = append_event(blocked, actor="papersim", action="extract_ir_blocked", stage="ir", detail={"failing": failing})
            self.store.write_audit(blocked)
            raise ContractError(f"IR audit failed: {failing}")
        ir = build_ir(
            case_id=case_id,
            iteration=iteration,
            paper_filename=layout.paper.name,
            paper_sha256=manifest.paper_sha256,
            profile_sha256=profile_hash,
            profile=profile,
            audit=audit,
            evidence=evidence,
        )
        audit = audit.model_copy(update={"ir_sha256": ir.ir_hash})
        self.store.write_ir(ir)
        self.store.write_audit(audit)
        self.store.mark_manifest_state(case_id, "ir_audited")
        return ir

    def approve_ir(self, case_id: str, iteration: int, *, approved_by: str, reason: str, test_only: bool = False) -> AuditRecord:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        if record.ir_sha256 != ir.ir_hash:
            raise ContractError("audit does not belong to the current IR")
        updated = approve(record, approved_by=approved_by, reason=reason, test_only=test_only)
        self.store.write_audit(updated)
        self.store.mark_manifest_state(case_id, "approved")
        return updated

    def generate_java(self, case_id: str, iteration: int) -> tuple[Path, Path]:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        ensure_approved(record, ir)
        layout, _ = self.store.require_case(case_id)
        build, solve = generate_iteration_java(ir, layout)
        updated = record.model_copy(update={"state": IterationState.JAVA_GENERATED})
        updated = append_event(
            updated,
            actor="papersim",
            action="generate_java",
            stage="java",
            detail={"build_sha256": sha256(build), "solve_sha256": sha256(solve)},
        )
        self.store.write_audit(updated)
        self.store.mark_manifest_state(case_id, "java_generated")
        return build, solve

    def record_build(
        self,
        case_id: str,
        iteration: int,
        *,
        mph_path: str | Path,
        status: str,
        exit_code: int,
        log_text: str,
    ) -> AuditRecord:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        ensure_approved(record, ir)
        if record.state not in {IterationState.JAVA_GENERATED, IterationState.BUILT}:
            raise ContractError("build recording requires generated Java")
        if status != "complete" or exit_code != 0:
            raise ContractError("build did not complete successfully")
        layout, _ = self.store.require_case(case_id)
        source = Path(mph_path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise StoreError("build MPH is missing or empty")
        if source != layout.built_mph(iteration).resolve():
            shutil.copy2(source, layout.built_mph(iteration))
        layout.run_log(iteration).write_text(log_text, encoding="utf-8")
        updated = record.model_copy(update={"state": IterationState.BUILT})
        updated = append_event(
            updated,
            actor="solver",
            action="build",
            stage="build",
            detail={"mph_sha256": sha256(layout.built_mph(iteration)), "size": layout.built_mph(iteration).stat().st_size},
        )
        self.store.write_audit(updated)
        self.store.mark_manifest_state(case_id, "built")
        return updated

    def audit_implementation(self, case_id: str, iteration: int, snapshot_path: str | Path) -> AuditRecord:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        layout, _ = self.store.require_case(case_id)
        snapshot_file = Path(snapshot_path).expanduser().resolve()
        snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise ContractError("COMSOL snapshot must be a JSON object")
        build_source = layout.build_java(iteration).read_text(encoding="utf-8")
        solve_source = layout.solve_java(iteration).read_text(encoding="utf-8")
        updated = audit_implementation(record, ir, snapshot, build_source=build_source, solve_source=solve_source)
        new_failures = [item.check_id for item in updated.checks[len(record.checks):] if not item.passed]
        if new_failures:
            updated = updated.model_copy(update={"state": IterationState.BLOCKED})
        self.store.write_audit(updated)
        write_json(layout.snapshot(iteration), snapshot)
        if new_failures:
            raise ContractError(f"COMSOL implementation audit failed: {new_failures}")
        self.store.mark_manifest_state(case_id, "implementation_audited")
        return updated


    def audit_implementation_from_mph(self, case_id: str, iteration: int) -> AuditRecord:
        layout, _ = self.store.require_case(case_id)
        snapshot = read_mph_snapshot(layout.built_mph(iteration))
        write_json(layout.snapshot(iteration), snapshot)
        return self.audit_implementation(case_id, iteration, layout.snapshot(iteration))

    def record_solve(
        self,
        case_id: str,
        iteration: int,
        *,
        mph_path: str | Path,
        status: str,
        exit_code: int,
        log_text: str,
    ) -> AuditRecord:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        ensure_approved(record, ir)
        if record.state not in {IterationState.IMPLEMENTATION_AUDITED, IterationState.SOLVED}:
            raise ContractError("solve requires a passed implementation audit")
        if status != "complete" or exit_code != 0:
            raise ContractError("solve did not complete successfully")
        layout, _ = self.store.require_case(case_id)
        source = Path(mph_path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise StoreError("solved MPH is missing or empty")
        if source != layout.solved_mph(iteration).resolve():
            shutil.copy2(source, layout.solved_mph(iteration))
        existing = layout.run_log(iteration).read_text(encoding="utf-8") if layout.run_log(iteration).is_file() else ""
        layout.run_log(iteration).write_text(existing + "\n" + log_text, encoding="utf-8")
        updated = record.model_copy(update={"state": IterationState.SOLVED})
        updated = append_event(
            updated,
            actor="solver",
            action="solve",
            stage="solve",
            detail={"mph_sha256": sha256(layout.solved_mph(iteration)), "size": layout.solved_mph(iteration).stat().st_size},
        )
        self.store.write_audit(updated)
        self.store.mark_manifest_state(case_id, "solved")
        return updated

    def normalize_results(
        self,
        case_id: str,
        iteration: int,
        *,
        raw_csv_path: str | Path,
        extra_metrics: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ir = self.store.load_ir(case_id, iteration)
        layout, _ = self.store.require_case(case_id)
        raw_path = Path(raw_csv_path).expanduser().resolve()
        text = raw_path.read_text(encoding="utf-8", errors="replace")
        try:
            rows = parse_tidy_csv(text)
        except ContractError:
            rows = parse_comsol_table_csv(text)
        for row in rows:
            row["case_id"] = case_id
            row["iteration"] = iteration
        header = ["case_id", "iteration", "stage", "source", "delta", "time", "metric", "value", "unit"]
        output = [",".join(header)]
        for row in rows:
            output.append(
                ",".join(
                    str(row.get(column, "")).replace(",", ";")
                    for column in header
                )
            )
        layout.results_csv(iteration).write_text("\n".join(output) + "\n", encoding="utf-8")
        metrics = summarize_rows(rows)
        if extra_metrics:
            metrics.update(extra_metrics)
        return metrics

    def audit_numeric(
        self,
        case_id: str,
        iteration: int,
        *,
        metrics: Mapping[str, Any],
        solver_status: str = "complete",
        solver_exit_code: int = 0,
        log_text: str | None = None,
    ) -> AuditRecord:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        layout, _ = self.store.require_case(case_id)
        combined_log = log_text
        if combined_log is None:
            combined_log = layout.run_log(iteration).read_text(encoding="utf-8", errors="replace")
        updated = audit_numeric(
            record,
            ir,
            metrics=metrics,
            solver_status=solver_status,
            solver_exit_code=solver_exit_code,
            log_text=combined_log,
            solved_mph_size=layout.solved_mph(iteration).stat().st_size,
        )
        self.store.write_audit(updated)
        self.store.mark_manifest_state(case_id, "numerical_audited")
        return updated

    def assess(self, case_id: str, iteration: int) -> AuditRecord:
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        updated = assess(record, ir)
        self.store.write_audit(updated)
        self.store.mark_manifest_state(case_id, "assessed")
        return updated

    def report(self, case_id: str, iteration: int) -> Path:
        layout, manifest = self.store.require_case(case_id)
        ir = self.store.load_ir(case_id, iteration)
        record = self.store.load_audit(case_id, iteration)
        links = {
            "paper": layout.paper.name,
            "build Java": layout.build_java(iteration).name,
            "solve Java": layout.solve_java(iteration).name,
            "IR": layout.ir(iteration).name,
            "audit": layout.audit(iteration).name,
        }
        if layout.built_mph(iteration).is_file():
            links["built MPH"] = layout.built_mph(iteration).name
        if layout.solved_mph(iteration).is_file():
            links["solved MPH"] = layout.solved_mph(iteration).name
        assets = layout.assets(iteration)
        for label, path in (
            ("metrics", assets / "metrics.json"),
            ("global export", assets / "iter001_global_all.csv"),
            ("Fig. 7 comparison", assets / "fig7_masks" / "fig7_paper_vs_comsol.png"),
            ("Fig. 7 reference masks", assets / "fig7_reference"),
            ("evidence logs", assets / "iter001_evidence_logs.tar.gz"),
        ):
            if path.is_file() or path.is_dir():
                links[label] = path.relative_to(layout.directory).as_posix()
        return generate_report(manifest, ir, record, output=layout.report, artifact_links=links)
