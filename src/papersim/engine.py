from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import time
from typing import Any, Mapping

from .assess import build_assessment
from .compare import calculate_compare
from .contracts import AgentAdapter, AgentResult, AgentTask, ContractError, Producer, SolverBackend
from .model import canonical_spec, draft_from_dir, model_spec_digest, validate_model_markdown, validate_model_spec
from .records import Assess, Case, Compare, Model, Run
from .run import FakeSolver, validate_run_backend
from .store import (
    PAPERSIM_VERSION,
    SCHEMA_VERSION,
    PaperRepository,
    StoreError,
    Workspace,
    read_json,
    sha256,
    sha256_bytes,
    utc_now,
    validate_object,
    write_json,
)


def _slug(value: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    if not slug:
        raise ContractError("identifier cannot be empty")
    return slug


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_host_profile(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    if not source.is_file():
        raise StoreError(f"host profile does not exist: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StoreError("host profile must be a JSON object")
    return data


class Engine:
    """PaperSim's canonical writer and five-operation API."""

    def __init__(
        self,
        root: str | Path,
        *,
        paper_root: str | Path | None = None,
        agents: Mapping[str, AgentAdapter] | None = None,
        solvers: Mapping[str, SolverBackend] | None = None,
        host_name: str = "local",
        host_profile: str | Path | None = None,
        initialize: bool = True,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        profile: dict[str, Any] = load_host_profile(host_profile) if host_profile else {}
        self.host_name = str(profile.get("host_name") or host_name)
        profile_paper_root = profile.get("paper_root")
        selected_paper_root = paper_root or profile_paper_root
        if selected_paper_root is None:
            selected_paper_root = self.root / "paper" / "original"
        self.paper_root = Path(selected_paper_root).expanduser().resolve()
        self.paper_repo = PaperRepository(self.paper_root)
        self.workspace = Workspace(self.root, initialize=initialize)
        self.agents: dict[str, AgentAdapter] = dict(agents or {})
        self.solvers: dict[str, SolverBackend] = dict(solvers or {})
        for name, adapter in self.agents.items():
            if not callable(getattr(adapter, "run", None)) or not callable(getattr(adapter, "capabilities", None)):
                raise ContractError(f"agent adapter '{name}' does not satisfy AgentAdapter")
        for name, solver in self.solvers.items():
            validate_run_backend(solver)
        # Existing canonical state is checked at startup; an empty workspace is
        # a valid first-start state.
        self.workspace.validate_all()
        self._validate_semantics()

    @classmethod
    def open(
        cls,
        root: str | Path,
        *,
        paper_root: str | Path | None = None,
        agents: Mapping[str, AgentAdapter] | None = None,
        solvers: Mapping[str, SolverBackend] | None = None,
        host_name: str = "local",
        host_profile: str | Path | None = None,
    ) -> "Engine":
        return cls(
            root,
            paper_root=paper_root,
            agents=agents,
            solvers=solvers,
            host_name=host_name,
            host_profile=host_profile,
        )

    def handshake(self, *, agent_name: str | None = None, capability: str | None = None) -> dict[str, Any]:
        """Verify the runtime boundary before an agent begins canonical work."""

        try:
            counts = self.workspace.validate_all()
            self._validate_semantics()
            self.paper_repo._validate_root()
        except Exception as exc:
            raise StoreError(f"PaperSim handshake failed: {exc}") from exc
        if agent_name is not None:
            adapter = self.agents.get(agent_name)
            if adapter is None:
                raise ContractError(f"agent adapter is not registered: {agent_name}")
            capabilities = set(adapter.capabilities())
            if capability is not None and capability not in capabilities:
                raise ContractError(f"agent '{agent_name}' does not provide capability '{capability}'")
        return {
            "papersim_version": PAPERSIM_VERSION,
            "schema_version": SCHEMA_VERSION,
            "host_name": self.host_name,
            "workspace": str(self.root),
            "paper_root": str(self.paper_root),
            "counts": counts,
            "agents": sorted(self.agents),
            "solvers": sorted(self.solvers),
        }

    def _producer(self, adapter_name: str = "engine", adapter_version: str = PAPERSIM_VERSION) -> dict[str, str]:
        return Producer(
            papersim_version=PAPERSIM_VERSION,
            schema_version=SCHEMA_VERSION,
            adapter_name=adapter_name,
            adapter_version=adapter_version,
            host_name=self.host_name,
        ).as_dict()

    @staticmethod
    def _envelope(
        schema_version: str,
        object_id: str,
        *,
        producer: Mapping[str, str],
        refs: Mapping[str, str],
        status: str,
        artifact_hashes: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": schema_version,
            "id": object_id,
            "created_at": utc_now(),
            "producer": dict(producer),
            "refs": dict(refs),
            "status": status,
            "artifact_hashes": dict(artifact_hashes or {}),
        }

    def case(
        self,
        paper: str | Path | Mapping[str, Any],
        *,
        case_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        observations: list[Mapping[str, Any]] | None = None,
        agent: str | AgentAdapter | None = None,
    ) -> Case:
        agent_name, agent_adapter = self._select_agent(agent, "case")
        if agent_adapter is not None:
            task = AgentTask(kind="case", inputs={"paper": str(paper)}, context={"host_name": self.host_name})
            result = self._run_agent(agent_adapter, task)
            outputs = dict(result.outputs)
            metadata = {**dict(metadata or {}), **dict(outputs.get("metadata") or {})}
            observations = list(observations or outputs.get("reference_observations") or [])
            case_id = str(outputs.get("case_id") or case_id) if (outputs.get("case_id") or case_id) else None

        paper_ref = self.paper_repo.resolve(paper)
        identifier = _slug(case_id or paper_ref["paper_id"])
        path = self.workspace.object_path("case", identifier)
        if path.exists():
            existing = self.workspace.read_object("case", identifier)
            if existing["paper_ref"]["sha256"] != paper_ref["sha256"]:
                raise StoreError(f"case already exists with a different paper: {identifier}")
            return Case(identifier, path, existing)

        merged_metadata = dict(paper_ref)
        merged_metadata.update(dict(metadata or {}))
        if not merged_metadata.get("title"):
            raise ContractError("case metadata requires title")
        normalized_observations: list[dict[str, Any]] = []
        for index, observation in enumerate(observations or []):
            if not isinstance(observation, Mapping):
                raise ContractError(f"reference observation {index} must be an object")
            item = dict(observation)
            item.setdefault("id", f"observation-{index + 1:04d}")
            item.setdefault("quantity", item.get("metric", "unknown"))
            item.setdefault("value", None)
            item.setdefault("units", "")
            item.setdefault("source", "paper")
            item.setdefault("evidence", [])
            if item["value"] is None:
                raise ContractError(f"reference observation {item['id']} requires a value")
            normalized_observations.append(item)
        data = self._envelope(
            "papersim.case.v1",
            identifier,
            producer=self._producer(agent_name or "engine"),
            refs={"paper": paper_ref["paper_id"], "paper_sha256": paper_ref["sha256"]},
            status="open",
            artifact_hashes={paper_ref["paper_id"]: paper_ref["sha256"]},
        )
        data.update(
            {
                "paper": {
                    "title": str(merged_metadata.get("title")),
                    "authors": list(merged_metadata.get("authors") or []),
                    "year": merged_metadata.get("year"),
                    "doi": merged_metadata.get("doi"),
                    "bibkey": merged_metadata.get("bibkey"),
                },
                "paper_ref": paper_ref,
                "reference_observations": normalized_observations,
                "model_ids": [],
                "run_ids": [],
                "compare_ids": [],
                "assess_ids": [],
            }
        )
        self.workspace.write_object("case", data)
        return Case(identifier, path, data)

    def model(
        self,
        case_id: str,
        *,
        source: str | Path | None = None,
        parent: str | None = None,
        compare: str | None = None,
        change_reason: str | None = None,
        agent: str | AgentAdapter | None = None,
        markdown: str | None = None,
        spec: Mapping[str, Any] | None = None,
    ) -> Model:
        case = self.workspace.read_object("case", case_id)
        agent_name, agent_adapter = self._select_agent(agent, "model")
        if source is not None and (markdown is not None or spec is not None):
            raise ContractError("model draft must be supplied as source or markdown/spec, not both")
        if agent_adapter is not None:
            task = AgentTask(
                kind="model",
                inputs={"case": case, "parent_id": parent, "compare_id": compare},
                context={"host_name": self.host_name, "paper_ref": case["paper_ref"]},
            )
            result = self._run_agent(agent_adapter, task)
            if markdown is None:
                markdown = result.outputs.get("markdown") or result.outputs.get("model_md")
            if spec is None:
                spec = result.outputs.get("spec") or result.outputs.get("model_spec")
            for artifact in result.artifacts:
                artifact_path = Path(str(artifact.path)).expanduser()
                if not artifact_path.is_file():
                    continue
                if markdown is None and artifact_path.suffix.lower() in {".md", ".markdown"}:
                    markdown = artifact_path.read_text(encoding="utf-8")
                if spec is None and artifact_path.suffix.lower() == ".json":
                    spec = json.loads(artifact_path.read_text(encoding="utf-8"))
        if source is not None:
            markdown, spec = draft_from_dir(source)
        if (markdown is None) != (spec is None):
            raise ContractError("model draft requires both markdown and spec")
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except json.JSONDecodeError as exc:
                raise ContractError(f"model spec output is not valid JSON: {exc}") from exc
        if markdown is None or spec is None:
            raise ContractError("model draft requires both markdown and spec")
        validate_model_markdown(markdown)
        validate_model_spec(spec)

        parent_data: dict[str, Any] | None = None
        if parent is not None:
            parent_data = self.workspace.read_object("model", parent)
            if parent_data["case_id"] != case_id:
                raise ContractError("parent model belongs to a different case")
            if compare is not None:
                compare_data = self.workspace.read_object("compare", compare)
                if compare_data["case_id"] != case_id or compare_data["model_id"] != parent:
                    raise ContractError("model revision compare must reference the parent model in the same case")
            if not change_reason or not change_reason.strip():
                raise ContractError("a model revision requires a non-empty change_reason")
            lineage_id = parent_data["lineage_id"]
        else:
            if compare is not None:
                raise ContractError("compare can only be supplied with parent")
            lineage_id = _slug(f"lineage-{case_id}")
        draft_spec = dict(spec)
        declared_md_hash = draft_spec.pop("source_md_sha256", None)
        spec_status = "current"
        if declared_md_hash is not None and declared_md_hash != sha256_bytes(markdown.encode("utf-8")):
            spec_status = "stale"
        if parent_data is not None:
            parent_md = self.workspace.artifact_ref_path(parent_data["model_md"]).read_text(encoding="utf-8")
            parent_spec = self._model_spec(parent_data)
            parent_spec = {key: value for key, value in parent_spec.items() if key != "source_md_sha256"}
            if markdown == parent_md and draft_spec == parent_spec:
                raise ContractError("a model revision must change model.md or model.spec.json")
            if markdown != parent_md and draft_spec == parent_spec:
                spec_status = "stale"
        spec = canonical_spec(draft_spec, markdown)
        validate_model_spec(spec)
        model_id = self.workspace.next_id("model", "m")
        staging_dir: Path | None = None
        solver_config = spec.get("solver", {})
        declared_staging = solver_config.get("staging_dir") if isinstance(solver_config, dict) else None
        if isinstance(declared_staging, str) and Path(declared_staging).expanduser().is_dir():
            staging_dir = Path(declared_staging).expanduser().resolve()
            solver_config["staging_dir"] = "solver"
            solver_config["staging_bundle"] = f"model_{model_id}__bundle.tar.gz"
        model_md = self.workspace.put_artifact(
            markdown.encode("utf-8"),
            name=f"model_{model_id}__model.md",
            media_type="text/markdown",
        )
        spec_bytes = _json_bytes(spec)
        model_spec = self.workspace.put_artifact(
            spec_bytes,
            name=f"model_{model_id}__spec.json",
            media_type="application/json",
        )
        bundle = self._make_model_bundle(model_id, markdown, spec_bytes, staging_dir=staging_dir)
        bundle_ref = self.workspace.put_artifact(
            bundle,
            name=f"model_{model_id}__bundle.tar.gz",
            media_type="application/gzip",
        )
        data = self._envelope(
            "papersim.model.v1",
            model_id,
            producer=self._producer(agent_name or "engine"),
            refs={"case": case_id, **({"parent": parent} if parent else {}), **({"compare": compare} if compare else {})},
            status=spec_status,
            artifact_hashes={
                "model_md": model_md["sha256"],
                "model_spec": model_spec["sha256"],
                "bundle": bundle_ref["sha256"],
            },
        )
        data.update(
            {
                "lineage_id": lineage_id,
                "parent_id": parent,
                "case_id": case_id,
                "compare_id": compare,
                "change_reason": str(change_reason or "initial model"),
                "created_by": agent_name or "engine",
                "model_md": model_md,
                "model_spec": model_spec,
                "bundle": bundle_ref,
                "spec_status": spec_status,
                "spec_digest": model_spec_digest(spec),
            }
        )
        self.workspace.write_object("model", data)
        self.workspace.append_case_ref(case_id, "model_ids", model_id)
        return Model(model_id, self.workspace.object_path("model", model_id), data)

    def _make_model_bundle(self, model_id: str, markdown: str, spec_bytes: bytes, *, staging_dir: Path | None = None) -> bytes:
        # The bundle is an in-memory deterministic tar so the canonical
        # workspace remains flat and the model remains independently movable.
        import io

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as handle:
            for name, payload in (("model.md", markdown.encode("utf-8")), ("model.spec.json", spec_bytes)):
                info = tarfile.TarInfo(name=name)
                info.size = len(payload)
                info.mtime = 0
                handle.addfile(info, io.BytesIO(payload))
            if staging_dir is not None:
                for source in sorted(staging_dir.rglob("*")):
                    if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
                        continue
                    relative = source.relative_to(staging_dir).as_posix()
                    payload = source.read_bytes()
                    info = tarfile.TarInfo(name=f"solver/{relative}")
                    info.size = len(payload)
                    info.mtime = 0
                    handle.addfile(info, io.BytesIO(payload))
        return buffer.getvalue()

    def run(
        self,
        model_id: str,
        *,
        backend: str = "comsol",
        solver: SolverBackend | None = None,
        config: str | Path | None = None,
        password_file: str | Path | None = None,
        remote_root: str | None = None,
        suite: str = "full",
        wait: bool = True,
        poll_seconds: float = 1.0,
        timeout_seconds: float = 7200.0,
    ) -> Run:
        model_record = self.workspace.read_object("model", model_id)
        if model_record.get("spec_status") != "current" or model_record.get("status") != "current":
            raise ContractError(f"model {model_id} has a stale spec and cannot be run")
        case = self.workspace.read_object("case", str(model_record["case_id"]))
        selected = solver or self.solvers.get(backend)
        if selected is None:
            if backend == "fake":
                selected = FakeSolver()
            elif backend == "comsol":
                from .comsol import ComsolBackend

                selected = ComsolBackend(
                    config=config,
                    password_file=password_file,
                    remote_root=remote_root,
                    suite=suite,
                )
            else:
                raise ContractError(f"no solver registered for backend '{backend}'")
        selected = validate_run_backend(selected)
        run_id = self.workspace.next_id("run", "r")
        model = Model(model_id, self.workspace.object_path("model", model_id), model_record)
        case_record = Case(case["id"], self.workspace.object_path("case", case["id"]), case)

        started_at = utc_now()
        try:
            selected.validate(model)
            build_result = self._call_solver(selected, "build", model, run_id)
            submit_result = self._call_solver(selected, "submit", model, run_id)
            status_result = submit_result
            if wait:
                deadline = time.monotonic() + timeout_seconds
                while True:
                    status_result = self._call_solver(selected, "status", run_id)
                    state = str(status_result.get("status") or "")
                    if state in {"complete", "failed", "cancelled", "error"}:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"solver run {run_id} did not finish within {timeout_seconds}s")
                    time.sleep(max(0.01, poll_seconds))
            collect_result = self._call_solver(selected, "collect", run_id) if wait else {}
        except Exception as exc:
            failure_log = f"{type(exc).__name__}: {exc}\n".encode("utf-8")
            log_ref = self.workspace.put_artifact(
                failure_log,
                name=f"run_{run_id}__error.log",
                media_type="text/plain",
            )
            input_ref = self.workspace.put_artifact(
                _json_bytes({"model_id": model_id, "backend": backend, "error": str(exc)}),
                name=f"run_{run_id}__input.json",
                media_type="application/json",
            )
            data = self._envelope(
                "papersim.run.v1",
                run_id,
                producer=self._producer(getattr(selected, "adapter_name", backend), getattr(selected, "adapter_version", PAPERSIM_VERSION)),
                refs={"case": case["id"], "model": model_id},
                status="failed",
                artifact_hashes={"input": input_ref["sha256"], "error_log": log_ref["sha256"]},
            )
            data.update(
                {
                    "case_id": case["id"],
                    "model_id": model_id,
                    "baseline": False,
                    "solver": backend,
                    "solver_version": str(getattr(selected, "adapter_version", "unknown")),
                    "environment": {},
                    "status": "failed",
                    "exit_code": None,
                    "inputs": [input_ref],
                    "logs": [log_ref],
                    "artifacts": [],
                    "metrics": {},
                    "started_at": started_at,
                    "completed_at": utc_now(),
                    "remote": {},
                    "remote_artifacts": [],
                }
            )
            self.workspace.write_object("run", data)
            self.workspace.append_case_ref(case["id"], "run_ids", run_id)
            raise ContractError(f"solver run {run_id} failed: {exc}") from exc

        build_json = dict(build_result or {})
        submit_json = dict(submit_result or {})
        status_json = dict(status_result or {})
        collect_json = dict(collect_result or {})
        status_value = str(collect_json.get("status") or status_json.get("status") or submit_json.get("status") or "complete")
        if status_value not in {"submitted", "running", "complete", "failed", "cancelled"}:
            status_value = "complete" if status_value in {"ok", "success"} else "failed"
        exit_code = collect_json.get("exit_code", status_json.get("exit_code", submit_json.get("exit_code", 0)))
        if isinstance(exit_code, bool):
            exit_code = int(exit_code)
        if exit_code is not None:
            exit_code = int(exit_code)
        metrics = collect_json.get("metrics") or submit_json.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {"value": metrics}
        environment = collect_json.get("environment") or submit_json.get("environment") or {"kind": "unknown"}
        if not isinstance(environment, dict):
            environment = {"value": environment}
        logs_payload = collect_json.get("logs") or submit_json.get("logs") or []
        if isinstance(logs_payload, str):
            logs_payload = [logs_payload]
        logs = "\n".join(str(item) for item in logs_payload if item is not None) or "solver completed without a log message"
        log_ref = self.workspace.put_artifact(
            logs.encode("utf-8"),
            name=f"run_{run_id}__solver.log",
            media_type="text/plain",
        )
        input_ref = self.workspace.put_artifact(
            _json_bytes({"model_id": model_id, "backend": backend, "build": build_json, "submit": submit_json}),
            name=f"run_{run_id}__input.json",
            media_type="application/json",
        )
        artifact_refs: list[dict[str, Any]] = []
        for index, artifact in enumerate(collect_json.get("artifacts") or []):
            if isinstance(artifact, Mapping):
                if "sha256" in artifact and "path" in artifact:
                    artifact_refs.append(dict(artifact))
                elif "path" in artifact:
                    artifact_refs.append(
                        self.workspace.put_artifact(
                            str(artifact["path"]),
                            name=str(artifact.get("name") or f"run_{run_id}__{index + 1}{Path(str(artifact['path'])).suffix or '.bin'}"),
                            media_type=str(artifact.get("media_type") or "application/octet-stream"),
                        )
                    )
                elif "bytes" in artifact:
                    artifact_refs.append(
                        self.workspace.put_artifact(
                            bytes(artifact["bytes"]),
                            name=str(artifact.get("name") or f"run_{run_id}__{index + 1}.bin"),
                            media_type=str(artifact.get("media_type") or "application/octet-stream"),
                        )
                    )
            elif isinstance(artifact, (str, Path)):
                path = Path(artifact)
                artifact_refs.append(
                    self.workspace.put_artifact(
                        path,
                        name=f"run_{run_id}__{index + 1}{path.suffix or '.bin'}",
                        media_type="application/octet-stream",
                    )
                )
        if not artifact_refs:
            artifact_refs.append(
                self.workspace.put_artifact(
                    _json_bytes(metrics),
                    name=f"run_{run_id}__metrics.json",
                    media_type="application/json",
                )
            )
        prior_complete = any(
            self.workspace.read_object("run", prior_id).get("status") == "complete"
            for prior_id in case.get("run_ids", [])
        )
        artifact_hashes = {
            "input": input_ref["sha256"],
            "log": log_ref["sha256"],
            **{f"artifact_{index + 1}": item["sha256"] for index, item in enumerate(artifact_refs)},
        }
        data = self._envelope(
            "papersim.run.v1",
            run_id,
            producer=self._producer(getattr(selected, "adapter_name", backend), getattr(selected, "adapter_version", PAPERSIM_VERSION)),
            refs={"case": case["id"], "model": model_id},
            status=status_value,
            artifact_hashes=artifact_hashes,
        )
        data.update(
            {
                "case_id": case["id"],
                "model_id": model_id,
                "baseline": bool(status_value == "complete" and not prior_complete),
                "solver": str(collect_json.get("solver") or submit_json.get("solver") or backend),
                "solver_version": str(collect_json.get("solver_version") or submit_json.get("solver_version") or getattr(selected, "adapter_version", "unknown")),
                "environment": environment,
                "status": status_value,
                "exit_code": exit_code,
                "inputs": [input_ref],
                "logs": [log_ref],
                "artifacts": artifact_refs,
                "metrics": metrics,
                "started_at": started_at,
                "completed_at": utc_now() if status_value in {"complete", "failed", "cancelled"} else None,
                "remote": dict(collect_json.get("remote") or {}),
                "remote_artifacts": list(collect_json.get("remote_artifacts") or []),
            }
        )
        self.workspace.write_object("run", data)
        self.workspace.append_case_ref(case["id"], "run_ids", run_id)
        if wait and (status_value != "complete" or exit_code not in (None, 0)):
            raise ContractError(f"solver run {run_id} did not complete successfully")
        return Run(run_id, self.workspace.object_path("run", run_id), data)

    @staticmethod
    def _call_solver(solver: SolverBackend, method: str, *args: Any, **kwargs: Any) -> Any:
        function = getattr(solver, method)
        try:
            return function(*args, **kwargs)
        except TypeError as exc:
            # Some host adapters implement the minimal ADR method signatures
            # without run_id/workdir arguments. Fall back to the model-only
            # form only when Python reports an argument-binding mismatch.
            if "positional argument" in str(exc) or "argument" in str(exc):
                try:
                    if method == "status":
                        return function(args[0])
                    if method in {"build", "submit", "collect"}:
                        return function(args[0])
                except TypeError:
                    pass
            raise

    def compare(
        self,
        run: str,
        case: str | None = None,
        *,
        metrics: Mapping[str, Any] | None = None,
        agent: str | AgentAdapter | None = None,
    ) -> Compare:
        run_data = self.workspace.read_object("run", run)
        case_id = case or str(run_data["case_id"])
        case_data = self.workspace.read_object("case", case_id)
        if case_data["id"] != run_data["case_id"]:
            raise ContractError("compare case does not own the run")
        model_data = self.workspace.read_object("model", str(run_data["model_id"]))
        if model_data.get("spec_status") != "current" or model_data.get("status") != "current":
            raise ContractError("compare requires a model with a current, non-stale spec")
        if run_data["status"] != "complete":
            raise ContractError("compare requires a complete run")
        agent_name, agent_adapter = self._select_agent(agent, "compare")
        if agent_adapter is not None:
            task = AgentTask(
                kind="compare",
                inputs={"case": case_data, "model": model_data, "run": run_data},
                context={"host_name": self.host_name},
            )
            result = self._run_agent(agent_adapter, task)
            output = dict(result.outputs)
            compare_data = {
                key: output[key]
                for key in ("observed", "simulated", "errors", "metrics", "mismatches", "uncertainty", "evidence", "interpretation", "observation_ids")
                if key in output
            }
            metrics = compare_data.get("metrics") if metrics is None else metrics
        else:
            compare_data = {}
        if not compare_data:
            compare_data = calculate_compare(
                case=case_data,
                model_id=model_data["id"],
                run_id=run_data["id"],
                model_spec=self._model_spec(model_data),
                metrics=dict(metrics or run_data.get("metrics") or {}),
            )
        compare_id = self.workspace.next_id("compare", "c")
        evidence_ref = self.workspace.put_artifact(
            _json_bytes(compare_data),
            name=f"compare_{compare_id}__evidence.json",
            media_type="application/json",
        )
        data = self._envelope(
            "papersim.compare.v1",
            compare_id,
            producer=self._producer(agent_name or "engine"),
            refs={"case": case_id, "model": model_data["id"], "run": run},
            status="complete" if compare_data.get("interpretation") else "insufficient",
            artifact_hashes={"evidence": evidence_ref["sha256"]},
        )
        data.update(
            {
                "case_id": case_id,
                "model_id": model_data["id"],
                "run_id": run,
                "observation_ids": list(compare_data.get("observation_ids") or [str(item["id"]) for item in case_data.get("reference_observations", [])]),
                "observed": dict(compare_data.get("observed") or {}),
                "simulated": dict(compare_data.get("simulated") or {}),
                "errors": dict(compare_data.get("errors") or {}),
                "metrics": dict(compare_data.get("metrics") or metrics or run_data.get("metrics") or {}),
                "mismatches": list(compare_data.get("mismatches") or []),
                "uncertainty": list(compare_data.get("uncertainty") or []),
                "evidence": list(compare_data.get("evidence") or []),
                "interpretation": str(compare_data.get("interpretation") or "comparison recorded"),
            }
        )
        self.workspace.write_object("compare", data)
        self.workspace.append_case_ref(case_id, "compare_ids", compare_id)
        return Compare(compare_id, self.workspace.object_path("compare", compare_id), data)

    def assess(
        self,
        case_id: str,
        *,
        agent: str | AgentAdapter | None = None,
        verdict: str | None = None,
        confidence: str | None = None,
        scope: str | None = None,
        unresolved_questions: list[str] | None = None,
    ) -> Assess:
        case = self.workspace.read_object("case", case_id)
        models = list(case.get("model_ids", []))
        runs = list(case.get("run_ids", []))
        compares = list(case.get("compare_ids", []))
        if not models or not runs or not compares:
            raise ContractError("assess requires a model, a run, and a compare")
        complete_runs = [run_id for run_id in runs if self.workspace.read_object("run", run_id).get("status") == "complete"]
        if not complete_runs:
            raise ContractError("assess requires at least one complete run")
        baseline_run_id = complete_runs[0]
        latest_model = self.workspace.read_object("model", models[-1])
        latest_compare = self.workspace.read_object("compare", compares[-1])
        if latest_compare["run_id"] not in complete_runs:
            raise ContractError("latest compare is not linked to a complete run")
        latest_run = self.workspace.read_object("run", latest_compare["run_id"])
        model_spec = self._model_spec(latest_model)
        agent_name, agent_adapter = self._select_agent(agent, "assess")
        if agent_adapter is not None:
            task = AgentTask(
                kind="assess",
                inputs={"case": case, "models": [self.workspace.read_object("model", item) for item in models], "runs": [self.workspace.read_object("run", item) for item in runs], "compares": [self.workspace.read_object("compare", item) for item in compares]},
                context={"host_name": self.host_name},
            )
            result = self._run_agent(agent_adapter, task)
            output = dict(result.outputs)
            assessment = {
                "verdict": output.get("verdict") or verdict,
                "confidence": output.get("confidence") or confidence or "medium",
                "scope": output.get("scope") or scope or str(model_spec.get("scope") or "declared model and tested conditions"),
                "findings": list(output.get("findings") or []),
                "unresolved_questions": list(output.get("unresolved_questions") or unresolved_questions or model_spec.get("unresolved_questions", [])),
            }
        else:
            assessment = build_assessment(
                case=case,
                model=latest_model,
                run=latest_run,
                compare=latest_compare,
                model_spec=model_spec,
            )
            if verdict is not None:
                assessment["verdict"] = verdict
            if confidence is not None:
                assessment["confidence"] = confidence
            if scope is not None:
                assessment["scope"] = scope
            if unresolved_questions is not None:
                assessment["unresolved_questions"] = list(unresolved_questions)
        if assessment["verdict"] not in {"supported", "qualified", "questioned", "not_reproduced", "underdetermined"}:
            raise ContractError(f"invalid assessment verdict: {assessment['verdict']}")
        if assessment["confidence"] not in {"low", "medium", "high"}:
            raise ContractError(f"invalid confidence: {assessment['confidence']}")
        assess_id = self.workspace.next_id("assess", "a")
        evidence_ref = self.workspace.put_artifact(
            _json_bytes(assessment),
            name=f"assess_{assess_id}__evidence.json",
            media_type="application/json",
        )
        data = self._envelope(
            "papersim.assess.v1",
            assess_id,
            producer=self._producer(agent_name or "engine"),
            refs={"case": case_id, "baseline_run": baseline_run_id, "latest_compare": compares[-1]},
            status="final",
            artifact_hashes={"evidence": evidence_ref["sha256"]},
        )
        data.update(
            {
                "case_id": case_id,
                "baseline_run_id": baseline_run_id,
                "model_ids": models,
                "run_ids": runs,
                "compare_ids": compares,
                "acceptance": list(model_spec.get("acceptance", [])),
                "verdict": assessment["verdict"],
                "findings": list(assessment["findings"]),
                "confidence": assessment["confidence"],
                "scope": str(assessment["scope"]),
                "unresolved_questions": list(assessment["unresolved_questions"]),
            }
        )
        self.workspace.write_object("assess", data)
        self.workspace.append_case_ref(case_id, "assess_ids", assess_id)
        return Assess(assess_id, self.workspace.object_path("assess", assess_id), data)

    def _validate_semantics(self) -> None:
        for path in sorted(self.workspace.objects.glob("model_*.json")):
            data = read_json(path)
            md = self.workspace.artifact_ref_path(data["model_md"]).read_text(encoding="utf-8")
            spec = read_json(self.workspace.artifact_ref_path(data["model_spec"]))
            validate_model_markdown(md)
            validate_model_spec(spec)
            if sha256_bytes(md.encode("utf-8")) != spec.get("source_md_sha256"):
                raise StoreError(f"model spec is stale for {data['id']}")
            if model_spec_digest(spec) != data.get("spec_digest"):
                raise StoreError(f"model spec digest mismatch for {data['id']}")
        for path in sorted(self.workspace.objects.glob("run_*.json")):
            data = read_json(path)
            if not self.workspace.object_path("model", data["model_id"]).is_file():
                raise StoreError(f"run {data['id']} references an unknown model")
            if not self.workspace.object_path("case", data["case_id"]).is_file():
                raise StoreError(f"run {data['id']} references an unknown case")
            if data.get("baseline") and data.get("status") != "complete":
                raise StoreError(f"failed run cannot be baseline: {data['id']}")
        for path in sorted(self.workspace.objects.glob("compare_*.json")):
            data = read_json(path)
            for kind, key in (("case", "case_id"), ("model", "model_id"), ("run", "run_id")):
                if not self.workspace.object_path(kind, data[key]).is_file():
                    raise StoreError(f"compare {data['id']} references unknown {kind}: {data[key]}")
        for path in sorted(self.workspace.objects.glob("assess_*.json")):
            data = read_json(path)
            if not self.workspace.object_path("case", data["case_id"]).is_file():
                raise StoreError(f"assess {data['id']} references an unknown case")
            if not self.workspace.object_path("run", data["baseline_run_id"]).is_file():
                raise StoreError(f"assess {data['id']} references an unknown baseline run")

    def _select_agent(self, agent: str | AgentAdapter | None, capability: str) -> tuple[str | None, AgentAdapter | None]:
        if agent is None:
            return None, None
        if isinstance(agent, str):
            selected = self.agents.get(agent)
            if selected is None:
                raise ContractError(f"agent adapter is not registered: {agent}")
            name = agent
        else:
            selected = agent
            name = str(getattr(selected, "adapter_name", selected.__class__.__name__))
        capabilities = set(selected.capabilities())
        if capability not in capabilities:
            raise ContractError(f"agent '{name}' does not provide capability '{capability}'")
        return name, selected

    @staticmethod
    def _run_agent(adapter: AgentAdapter, task: AgentTask) -> AgentResult:
        result = adapter.run(task)
        if not isinstance(result, AgentResult):
            raise ContractError("AgentAdapter.run must return AgentResult")
        if result.status != "ok":
            raise ContractError(f"agent task failed: {result.message or result.status}")
        if result.kind != task.kind:
            raise ContractError(f"agent result kind mismatch: expected {task.kind}, got {result.kind}")
        return result

    def _model_spec(self, model: Mapping[str, Any]) -> dict[str, Any]:
        path = self.workspace.artifact_ref_path(model["model_spec"])
        return read_json(path)

    def _load_model(self, model_id: str) -> Model:
        data = self.workspace.read_object("model", model_id)
        return Model(model_id, self.workspace.object_path("model", model_id), data)

    def _load_run(self, run_id: str) -> Run:
        data = self.workspace.read_object("run", run_id)
        return Run(run_id, self.workspace.object_path("run", run_id), data)

    def _load_compare(self, compare_id: str) -> Compare:
        data = self.workspace.read_object("compare", compare_id)
        return Compare(compare_id, self.workspace.object_path("compare", compare_id), data)

    def _load_case(self, case_id: str) -> Case:
        data = self.workspace.read_object("case", case_id)
        return Case(case_id, self.workspace.object_path("case", case_id), data)
