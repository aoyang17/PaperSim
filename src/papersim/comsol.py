from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import shlex
import tarfile
import tempfile
from typing import Any, Mapping

from .contracts import ContractError, RemoteExecutor, TranslationGap, UnsupportedModel
from .store import read_json, sha256


class ComsolError(ContractError):
    """Raised when a COMSOL model cannot be executed or collected."""


def _remote_path(value: str) -> str:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise ComsolError("invalid remote path")
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    return shlex.quote(value)


class ComsolBackend:
    adapter_name = "comsol"
    adapter_version = "1.0"

    def __init__(
        self,
        executor: RemoteExecutor,
        *,
        remote_root: str,
        suite: str = "full",
        solver_version: str | None = None,
    ) -> None:
        missing = [
            name
            for name in ("run", "upload", "download", "describe")
            if not callable(getattr(executor, name, None))
        ]
        if missing:
            raise ContractError("remote executor is missing methods: " + ", ".join(missing))
        if not str(remote_root or "").strip():
            raise ContractError("COMSOL backend requires a remote_root supplied by the caller")
        description = dict(executor.describe())
        self.executor = executor
        self.remote_root = str(remote_root)
        self.suite = suite
        self.solver_version = str(solver_version or description.get("solver_version") or "unknown")
        self._executor_description = description
        self._runs: dict[str, dict[str, Any]] = {}

    def _spec(self, model: Any) -> dict[str, Any]:
        ref = model.data["model_spec"]
        path = Path(str(ref["path"]))
        if not path.is_absolute():
            path = Path(model.path).parent.parent / "artifacts" / path.name
        return read_json(path)

    def validate(self, model: Any) -> None:
        spec = self._spec(model)
        solver = spec.get("solver")
        if not isinstance(solver, dict) or solver.get("backend") != "comsol":
            raise UnsupportedModel("COMSOL backend requires model.spec.json.solver.backend=comsol")
        if not isinstance(solver.get("entrypoint"), str) or not solver["entrypoint"].strip():
            raise TranslationGap("COMSOL model spec requires solver.entrypoint")
        suites = solver.get("suite")
        if not isinstance(suites, dict) or self.suite not in suites:
            raise TranslationGap(f"COMSOL model spec does not define solver suite '{self.suite}'")
        if not isinstance(suites[self.suite], list) or not suites[self.suite]:
            raise TranslationGap(f"COMSOL suite '{self.suite}' is empty")

    def build(self, model: Any, run_id: str) -> dict[str, Any]:
        spec = self._spec(model)
        solver = spec["solver"]
        staging_value = solver.get("staging_dir")
        staging: Path | None = None
        if isinstance(staging_value, str):
            candidate = Path(staging_value).expanduser()
            if candidate.is_dir():
                staging = candidate.resolve()
            elif candidate.parts == ("solver",) and model.data.get("bundle"):
                bundle_ref = model.data["bundle"]
                bundle_path = Path(str(bundle_ref["path"]))
                if not bundle_path.is_absolute():
                    bundle_path = Path(model.path).parent.parent / "artifacts" / bundle_path.name
                extract_root = Path(tempfile.mkdtemp(prefix=f"papersim_{run_id}_model_", dir=tempfile.gettempdir())).resolve()
                with tarfile.open(bundle_path, "r:gz") as handle:
                    for member in handle.getmembers():
                        target = (extract_root / member.name).resolve()
                        if extract_root != target and extract_root not in target.parents:
                            raise TranslationGap(f"model bundle contains an unsafe path: {member.name}")
                    handle.extractall(extract_root)
                staging = extract_root / "solver"
        if staging is None or not staging.is_dir():
            raise TranslationGap("COMSOL requires a bundled solver directory or a valid solver.staging_dir")
        archive = Path(tempfile.gettempdir()) / f"papersim_{run_id}_model.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(staging, arcname="solver")
        return {"archive": str(archive), "suite": self.suite, "entrypoint": solver["entrypoint"]}

    def submit(self, model: Any, run_id: str) -> dict[str, Any]:
        spec = self._spec(model)
        solver = spec["solver"]
        run_root = self.remote_root
        agent = self.executor
        remote_input = f"{run_root}/input"
        remote_suite = f"{run_root}/suite"
        result = agent.run(f"mkdir -p {_remote_path(remote_input)} {_remote_path(remote_suite)}", timeout=120)
        if not result.ok:
            raise ComsolError(f"cannot create remote run root: {result.output}")
        build_result = self.build(model, run_id)
        upload = agent.upload(Path(build_result["archive"]), f"{remote_input}/model.tar.gz", timeout=1800)
        if not upload.ok:
            raise ComsolError(f"model upload failed: {upload.output}")
        unpack = agent.run(f"cd {_remote_path(remote_input)} && rm -rf solver && tar -xzf model.tar.gz", timeout=600)
        if not unpack.ok:
            raise ComsolError(f"model unpack failed: {unpack.output}")
        case_specs = [str(item) for item in solver["suite"][self.suite]]
        cases = [Path(item).stem for item in case_specs]
        quoted_cases = " ".join(_remote_path(item) for item in case_specs)
        entrypoint = f"{remote_input}/solver/{solver['entrypoint']}"
        command = (
            f"cd {_remote_path(remote_input)} && "
            f"bash {_remote_path(entrypoint)} {_remote_path(remote_suite)} {quoted_cases}"
        )
        submitted = agent.run(command, timeout=600)
        if not submitted.ok:
            raise ComsolError(f"COMSOL submission failed: {submitted.output}")
        jobs: dict[str, str] = {}
        for prefix, job_id in re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)=(\d+)\s*$", submitted.output):
            jobs[prefix] = job_id
        if set(jobs) != set(cases):
            raise ComsolError(f"submitted jobs do not match suite: expected={cases}, got={sorted(jobs)}")
        data = {
            "status": "submitted",
            "exit_code": None,
            "solver": self.adapter_name,
            "solver_version": self.solver_version,
            "environment": dict(self._executor_description),
            "remote": {"root": run_root, "jobs": jobs},
            "jobs": jobs,
            "metrics": {},
        }
        data["artifact_policy"] = dict(solver.get("artifact_policy") or {})
        self._runs[run_id] = data
        return data

    def status(self, run_id: str) -> dict[str, Any]:
        data = self._runs.get(run_id)
        if data is None:
            return {"status": "unknown", "exit_code": None}
        agent = self.executor
        jobs = data.get("jobs", {})
        states: dict[str, Any] = {}
        terminal = True
        for name, job_id in jobs.items():
            result = agent.run(f"sacct -j {shlex.quote(str(job_id))} --format=JobID,State,ExitCode,Elapsed -n -P | awk 'NF {{print; exit}}'", timeout=120)
            line = result.output.strip().splitlines()[-1] if result.output.strip() else ""
            fields = line.split("|")
            if len(fields) < 4:
                states[name] = {"job_id": job_id, "state": "UNKNOWN", "raw": result.output}
                terminal = False
            else:
                states[name] = {"job_id": job_id, "state": fields[1], "exit_code": fields[2], "elapsed": fields[3]}
                if fields[1] not in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}:
                    terminal = False
        if terminal:
            failed = any(item.get("state") != "COMPLETED" or str(item.get("exit_code")) != "0:0" for item in states.values())
            data["status"] = "failed" if failed else "complete"
            data["exit_code"] = 1 if failed else 0
            data["job_status"] = states
        else:
            data["status"] = "running"
            data["exit_code"] = None
            data["job_status"] = states
        self._runs[run_id] = data
        return dict(data)

    def collect(self, run_id: str, workdir: Any = None) -> dict[str, Any]:
        data = self._runs.get(run_id)
        if data is None or data.get("status") != "complete":
            raise ComsolError(f"cannot collect incomplete COMSOL run: {run_id}")
        agent = self.executor
        remote_root = str(data["remote"]["root"])
        remote_archive = f"{remote_root}/results.tar.gz"
        result = agent.run(
            f"cd {_remote_path(remote_root)} && tar -czf results.tar.gz -C suite . && sha256sum results.tar.gz",
            timeout=1800,
        )
        if not result.ok:
            raise ComsolError(f"result packing failed: {result.output}")
        local_archive = Path(tempfile.gettempdir()) / f"papersim_{run_id}_results.tar.gz"
        remote_hashes = re.findall(r"\b[a-f0-9]{64}\b", result.output)
        if not remote_hashes:
            raise ComsolError("remote result archive did not return a SHA-256 hash")
        download = agent.download(remote_archive, local_archive, timeout=3600)
        if not download.ok and not (local_archive.is_file() and sha256(local_archive) == remote_hashes[-1]):
            raise ComsolError(f"result download failed: {download.output}")
        if sha256(local_archive) != remote_hashes[-1]:
            raise ComsolError("downloaded result archive SHA-256 does not match the remote archive")
        extract_root = Path(tempfile.mkdtemp(prefix=f"papersim_{run_id}_", dir=tempfile.gettempdir())).resolve()
        with tarfile.open(local_archive, "r:gz") as handle:
            for member in handle.getmembers():
                target = (extract_root / member.name).resolve()
                if extract_root != target and extract_root not in target.parents:
                    raise ComsolError(f"result archive contains an unsafe path: {member.name}")
            handle.extractall(extract_root)
        artifacts = [str(path) for path in sorted(extract_root.rglob("*")) if path.is_file()]
        required_artifacts = [item for item in artifacts if Path(item).suffix.lower() in {".mph", ".csv"}]
        if not required_artifacts or any(Path(item).stat().st_size == 0 for item in required_artifacts):
            raise ComsolError("COMSOL result archive is missing a nonempty MPH or CSV artifact")
        metrics = _collect_metrics(extract_root, data.get("metrics", {}))
        logs = _collect_logs(extract_root)
        for log_text in logs:
            if re.search(r"(?i)\b(error|exception|filenotfound|license error|failed)\b", log_text):
                raise ComsolError("COMSOL log contains a fatal diagnostic")

        policy = data.get("artifact_policy") or {}
        local_patterns = [str(item) for item in policy.get("local_globs", [])]
        authoritative_pattern = policy.get("authoritative_glob")
        local_paths: list[Path] = []
        for item in artifacts:
            path = Path(item)
            relative = path.relative_to(extract_root).as_posix()
            if not local_patterns or _matches_globs(relative, local_patterns) or (
                authoritative_pattern and _matches_globs(relative, [str(authoritative_pattern)])
            ):
                local_paths.append(path)
        if authoritative_pattern:
            matches = [
                path
                for path in local_paths
                if _matches_globs(path.relative_to(extract_root).as_posix(), [str(authoritative_pattern)])
            ]
            if len(matches) != 1:
                raise ComsolError(
                    f"artifact policy requires exactly one authoritative match, got {len(matches)}"
                )
        local_set = {path.resolve() for path in local_paths}
        remote_artifacts = [
            _remote_artifact_record(path, extract_root, str(remote_root))
            for path in map(Path, artifacts)
            if path.resolve() not in local_set
        ]
        return {
            "status": "complete",
            "exit_code": 0,
            "solver": self.adapter_name,
            "solver_version": self.solver_version,
            "environment": data.get("environment", {}),
            "metrics": metrics,
            "remote": data.get("remote", {}),
            "logs": ["COMSOL jobs completed; result archive SHA-256 matched remote hash"] + logs,
            "artifacts": [str(path) for path in local_paths],
            "remote_artifacts": remote_artifacts,
        }



def _matches_globs(relative: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatchcase

    return any(fnmatchcase(relative, pattern) for pattern in patterns)


def _remote_artifact_record(path: Path, root: Path, remote_root: str) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    suffix = path.suffix.lower()
    media_type = {
        ".mph": "application/vnd.comsol.mph",
        ".csv": "text/csv",
        ".log": "text/plain",
        ".out": "text/plain",
        ".err": "text/plain",
        ".sha256": "text/plain",
    }.get(suffix, "application/octet-stream")
    return {
        "name": relative,
        "sha256": sha256(path),
        "size": path.stat().st_size,
        "media_type": media_type,
        "remote_path": f"{remote_root.rstrip('/')}/{relative}",
    }


def _collect_metrics(root: Path, fallback: Mapping[str, Any]) -> dict[str, Any]:
    for path in sorted(root.rglob("metrics.json")):
        try:
            value = read_json(path)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    metrics: dict[str, Any] = dict(fallback)
    for path in sorted(root.rglob("*.csv")):
        try:
            lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
            header_index = None
            for index, line in enumerate(lines):
                stripped = line.strip()
                candidate = stripped[1:].strip() if stripped.startswith("%") else stripped
                lower = candidate.lower()
                if "," not in candidate:
                    continue
                if lower.startswith(("time", "x,y")) or not lower.startswith(("model", "version", "date", "table", "dimension", "nodes", "expressions", "description", "length unit")):
                    if index + 1 < len(lines):
                        header_index = index
                        break
            if header_index is None:
                continue
            reader = csv.reader(lines[header_index:], skipinitialspace=True)
            header = next(reader, None)
            if not header:
                continue
            rows = [row for row in reader if row]
            if not rows:
                continue
            for column, value in zip(header, rows[-1]):
                clean_column = re.sub(r"\s*\([^)]*\)\s*$", "", str(column)).strip()
                try:
                    metrics[f"{path.stem}.{clean_column}"] = float(value)
                except (TypeError, ValueError):
                    continue
        except OSError:
            continue
    return metrics


def _collect_logs(root: Path) -> list[str]:
    logs: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".log", ".out", ".err", ".txt"}:
            try:
                logs.append(path.read_text(encoding="utf-8", errors="replace")[-20000:])
            except OSError:
                continue
    return logs


class ComsolSuiteRunner(ComsolBackend):
    """Backward-compatible name for hosts that previously injected a runner."""

    pass
