"""Command-line interface for the canonical PaperSim case workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from .case_contracts import CaseManifest
from .case_migration import apply_profile_migration, apply_workspace_migration, plan_profile_migration, plan_workspace_migration
from .case_workflow import CaseWorkflow
from .contracts import PaperSimError


def _json(value: Any) -> str:
    def default(item: Any) -> Any:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"not JSON serializable: {type(item).__name__}")
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=default)


def _read_json_argument(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("JSON argument must be an object")
    return parsed


def _read_text(path: str | None) -> str:
    if path is None:
        return ""
    return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")


def _workflow(args: argparse.Namespace) -> CaseWorkflow:
    if not args.workspace:
        raise PaperSimError("--workspace is required")
    return CaseWorkflow(args.workspace)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="papersim", description="Auditable paper-simulation reproduction")
    parser.add_argument("--workspace", help="root containing canonical Case directories")
    sub = parser.add_subparsers(dest="command", required=True)

    case = sub.add_parser("case", help="create or inspect cases")
    case_sub = case.add_subparsers(dest="case_command", required=True)
    init = case_sub.add_parser("init", help="create a canonical Case directory")
    init.add_argument("--surname", required=True)
    init.add_argument("--year", required=True, type=int)
    init.add_argument("--topic", required=True)
    init.add_argument("--paper", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--goal", required=True)
    case_sub.add_parser("list", help="list canonical cases")

    iteration = sub.add_parser("iteration", help="create an immutable case iteration")
    iteration.add_argument("case_id")
    iteration.add_argument("--iteration", type=int, required=True)

    extract = sub.add_parser("extract", help="audit PDF evidence and write iterNNN_ir.json")
    extract.add_argument("case_id")
    extract.add_argument("--iteration", type=int, required=True)
    extract.add_argument("--profile", required=True)

    approve = sub.add_parser("approve", help="record human approval of an audited IR")
    approve.add_argument("case_id")
    approve.add_argument("--iteration", type=int, required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--reason", required=True)
    approve.add_argument("--test-only", action="store_true")

    build = sub.add_parser("build", help="generate build/solve Java and optionally record a completed build")
    build.add_argument("case_id")
    build.add_argument("--iteration", type=int, required=True)
    build.add_argument("--mph")
    build.add_argument("--status", default="complete")
    build.add_argument("--exit-code", type=int, default=0)
    build.add_argument("--log-file")

    implementation = sub.add_parser("audit-implementation", help="audit a COMSOL readback snapshot against the IR")
    implementation.add_argument("case_id")
    implementation.add_argument("--iteration", type=int, required=True)
    implementation.add_argument("--snapshot")
    implementation.add_argument("--from-mph", action="store_true")

    solve = sub.add_parser("solve", help="record a completed independent solve and export")
    solve.add_argument("case_id")
    solve.add_argument("--iteration", type=int, required=True)
    solve.add_argument("--mph", required=True)
    solve.add_argument("--status", default="complete")
    solve.add_argument("--exit-code", type=int, default=0)
    solve.add_argument("--log-file")

    numeric = sub.add_parser("audit-numeric", help="normalize results and run numerical acceptance")
    numeric.add_argument("case_id")
    numeric.add_argument("--iteration", type=int, required=True)
    numeric.add_argument("--raw-csv", required=True)
    numeric.add_argument("--metrics-json")
    numeric.add_argument("--log-file")

    assess = sub.add_parser("assess", help="derive the scoped verdict from recorded evidence")
    assess.add_argument("case_id")
    assess.add_argument("--iteration", type=int, required=True)

    report = sub.add_parser("report", help="generate self-contained offline report.html")
    report.add_argument("case_id")
    report.add_argument("--iteration", type=int, required=True)

    schemas = sub.add_parser("schemas", help="export canonical JSON Schema files")
    schemas.add_argument("directory")

    migrate = sub.add_parser("migrate", help="plan or apply canonical case/profile renames")
    migrate.add_argument("--profile-dir", default="profiles")
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--workspace-only", action="store_true")
    migrate.add_argument("--profiles-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "case":
            workflow = _workflow(args)
            if args.case_command == "list":
                result = {"cases": workflow.store.list_cases()}
            else:
                manifest = workflow.create_case(
                    surname=args.surname,
                    year=args.year,
                    topic=args.topic,
                    paper=args.paper,
                    title=args.title,
                    goal=args.goal,
                )
                result = manifest
        elif args.command == "iteration":
            layout, audit = _workflow(args).create_iteration(args.case_id, args.iteration)
            result = {"case_id": args.case_id, "iteration": args.iteration, "audit_path": str(layout.audit(args.iteration)), "state": audit.state}
        elif args.command == "extract":
            result = _workflow(args).extract_ir(args.case_id, args.iteration, args.profile)
        elif args.command == "approve":
            result = _workflow(args).approve_ir(
                args.case_id,
                args.iteration,
                approved_by=args.approved_by,
                reason=args.reason,
                test_only=args.test_only,
            )
        elif args.command == "build":
            workflow = _workflow(args)
            build_path, solve_path = workflow.generate_java(args.case_id, args.iteration)
            result: Any = {"build_java": str(build_path), "solve_java": str(solve_path), "built": False}
            if args.mph:
                audit = workflow.record_build(
                    args.case_id,
                    args.iteration,
                    mph_path=args.mph,
                    status=args.status,
                    exit_code=args.exit_code,
                    log_text=_read_text(args.log_file),
                )
                result.update({"built": True, "audit": audit})
        elif args.command == "audit-implementation":
            workflow = _workflow(args)
            if args.from_mph:
                result = workflow.audit_implementation_from_mph(args.case_id, args.iteration)
            elif args.snapshot:
                result = workflow.audit_implementation(args.case_id, args.iteration, args.snapshot)
            else:
                raise PaperSimError("audit-implementation requires --snapshot or --from-mph")
        elif args.command == "solve":
            result = _workflow(args).record_solve(
                args.case_id,
                args.iteration,
                mph_path=args.mph,
                status=args.status,
                exit_code=args.exit_code,
                log_text=_read_text(args.log_file),
            )
        elif args.command == "audit-numeric":
            workflow = _workflow(args)
            metrics = workflow.normalize_results(
                args.case_id,
                args.iteration,
                raw_csv_path=args.raw_csv,
                extra_metrics=_read_json_argument(args.metrics_json),
            )
            result = workflow.audit_numeric(
                args.case_id,
                args.iteration,
                metrics=metrics,
                log_text=_read_text(args.log_file) if args.log_file else None,
            )
        elif args.command == "assess":
            result = _workflow(args).assess(args.case_id, args.iteration)
        elif args.command == "report":
            result = {"report": str(_workflow(args).report(args.case_id, args.iteration))}
        elif args.command == "schemas":
            from .schemas import export_schemas

            result = export_schemas(args.directory)
        elif args.command == "migrate":
            records: dict[str, Any] = {}
            if not args.profiles_only:
                func = apply_workspace_migration if args.apply else plan_workspace_migration
                records["workspace"] = [item.as_dict() if hasattr(item, "as_dict") else item for item in (func(args.workspace) if args.apply else func(args.workspace))]
            if not args.workspace_only:
                func = apply_profile_migration if args.apply else plan_profile_migration
                records["profiles"] = [item.as_dict() if hasattr(item, "as_dict") else item for item in (func(args.profile_dir, dry_run=False) if args.apply else func(args.profile_dir))]
            result = records
        else:
            raise PaperSimError(f"unsupported command: {args.command}")
    except Exception as exc:
        print(f"papersim: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
