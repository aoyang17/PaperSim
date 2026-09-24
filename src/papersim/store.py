from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from .contracts import ContractError, Producer, StoreError

PAPERSIM_VERSION = "0.2.0"
SCHEMA_VERSION = "papersim.schemas.v1"
OBJECT_KINDS = ("case", "model", "run", "compare", "assess")
ARTIFACT_REQUIRED = ("name", "sha256", "size", "media_type", "path")


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": list(ARTIFACT_REQUIRED),
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "size": {"type": "integer", "minimum": 0},
            "media_type": {"type": "string", "minLength": 1},
            "path": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }


def _envelope(kind: str, properties: dict[str, Any], required: list[str], statuses: list[str]) -> dict[str, Any]:
    base_properties: dict[str, Any] = {
        "schema_version": {"type": "string", "enum": [f"papersim.{kind}.v1"]},
        "id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]*$"},
        "created_at": {"type": "string", "minLength": 1},
        "producer": {
            "type": "object",
            "required": ["papersim_version", "schema_version", "adapter_name", "adapter_version", "host_name"],
            "properties": {
                "papersim_version": {"type": "string", "minLength": 1},
                "schema_version": {"type": "string", "minLength": 1},
                "adapter_name": {"type": "string", "minLength": 1},
                "adapter_version": {"type": "string", "minLength": 1},
                "host_name": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "refs": {"type": "object", "additionalProperties": {"type": "string"}},
        "status": {"type": "string", "enum": statuses},
        "artifact_hashes": {
            "type": "object",
            "additionalProperties": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        },
    }
    base_properties.update(properties)
    return {
        "type": "object",
        "required": ["schema_version", "id", "created_at", "producer", "refs", "status", "artifact_hashes"] + required,
        "properties": base_properties,
        "additionalProperties": False,
    }


CASE_SCHEMA = _envelope(
    "case",
    {
        "paper": {
            "type": "object",
            "required": ["title"],
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "authors": {"type": "array", "items": {"type": "string"}},
                "year": {"type": ["integer", "null"]},
                "doi": {"type": ["string", "null"]},
                "bibkey": {"type": ["string", "null"]},
            },
            "additionalProperties": True,
        },
        "paper_ref": {
            "type": "object",
            "required": ["paper_id", "path", "filename", "sha256"],
            "properties": {
                "paper_id": {"type": "string", "minLength": 1},
                "path": {"type": "string", "minLength": 1},
                "filename": {"type": "string", "minLength": 1},
                "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "title": {"type": "string"},
                "authors": {"type": "array", "items": {"type": "string"}},
                "year": {"type": ["integer", "null"]},
                "doi": {"type": ["string", "null"]},
                "bibkey": {"type": ["string", "null"]},
                "added_at": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "reference_observations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "quantity", "value", "units", "source"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "quantity": {"type": "string", "minLength": 1},
                    "value": {},
                    "units": {"type": "string"},
                    "source": {"type": "string", "minLength": 1},
                    "condition": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
        },
        "model_ids": {"type": "array", "items": {"type": "string"}},
        "run_ids": {"type": "array", "items": {"type": "string"}},
        "compare_ids": {"type": "array", "items": {"type": "string"}},
        "assess_ids": {"type": "array", "items": {"type": "string"}},
    },
    ["paper", "paper_ref", "reference_observations", "model_ids", "run_ids", "compare_ids", "assess_ids"],
    ["open", "in_progress", "assessed"],
)

MODEL_SCHEMA = _envelope(
    "model",
    {
        "lineage_id": {"type": "string", "minLength": 1},
        "parent_id": {"type": ["string", "null"]},
        "case_id": {"type": "string", "minLength": 1},
        "compare_id": {"type": ["string", "null"]},
        "change_reason": {"type": "string", "minLength": 1},
        "created_by": {"type": "string", "minLength": 1},
        "model_md": _artifact_schema(),
        "model_spec": _artifact_schema(),
        "bundle": _artifact_schema(),
        "spec_status": {"type": "string", "enum": ["current", "stale"]},
        "spec_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    },
    ["lineage_id", "parent_id", "case_id", "compare_id", "change_reason", "created_by", "model_md", "model_spec", "bundle", "spec_status", "spec_digest"],
    ["current", "stale"],
)

RUN_SCHEMA = _envelope(
    "run",
    {
        "case_id": {"type": "string", "minLength": 1},
        "model_id": {"type": "string", "minLength": 1},
        "baseline": {"type": "boolean"},
        "solver": {"type": "string", "minLength": 1},
        "solver_version": {"type": "string", "minLength": 1},
        "environment": {"type": "object"},
        "status": {"type": "string", "enum": ["submitted", "running", "complete", "failed", "cancelled"]},
        "exit_code": {"type": ["integer", "null"]},
        "inputs": {"type": "array", "items": _artifact_schema()},
        "logs": {"type": "array", "items": _artifact_schema()},
        "artifacts": {"type": "array", "items": _artifact_schema()},
        "metrics": {"type": "object"},
        "started_at": {"type": "string"},
        "completed_at": {"type": ["string", "null"]},
        "remote": {"type": "object"},
        "remote_artifacts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "sha256", "size", "media_type", "remote_path"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "size": {"type": "integer", "minimum": 0},
                    "media_type": {"type": "string", "minLength": 1},
                    "remote_path": {"type": "string", "minLength": 1},
                },
                "additionalProperties": False,
            },
        },
    },
    ["case_id", "model_id", "baseline", "solver", "solver_version", "environment", "status", "exit_code", "inputs", "logs", "artifacts", "metrics", "started_at", "completed_at"],
    ["submitted", "running", "complete", "failed", "cancelled"],
)

COMPARE_SCHEMA = _envelope(
    "compare",
    {
        "case_id": {"type": "string", "minLength": 1},
        "model_id": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "minLength": 1},
        "observation_ids": {"type": "array", "items": {"type": "string"}},
        "observed": {"type": "object"},
        "simulated": {"type": "object"},
        "errors": {"type": "object"},
        "metrics": {"type": "object"},
        "mismatches": {"type": "array", "items": {"type": "object"}},
        "uncertainty": {"type": "array", "items": {"type": "object"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "interpretation": {"type": "string", "minLength": 1},
    },
    ["case_id", "model_id", "run_id", "observation_ids", "observed", "simulated", "errors", "metrics", "mismatches", "uncertainty", "evidence", "interpretation"],
    ["complete", "insufficient"],
)

ASSESS_SCHEMA = _envelope(
    "assess",
    {
        "case_id": {"type": "string", "minLength": 1},
        "baseline_run_id": {"type": "string", "minLength": 1},
        "model_ids": {"type": "array", "items": {"type": "string"}},
        "run_ids": {"type": "array", "items": {"type": "string"}},
        "compare_ids": {"type": "array", "items": {"type": "string"}},
        "acceptance": {"type": "array", "items": {"type": "object"}},
        "verdict": {
            "type": "string",
            "enum": ["supported", "qualified", "questioned", "not_reproduced", "underdetermined"],
        },
        "findings": {"type": "array", "items": {"type": "object"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "scope": {"type": "string", "minLength": 1},
        "unresolved_questions": {"type": "array", "items": {"type": "string"}},
    },
    ["case_id", "baseline_run_id", "model_ids", "run_ids", "compare_ids", "acceptance", "verdict", "findings", "confidence", "scope", "unresolved_questions"],
    ["final"],
)

SCHEMAS: dict[str, dict[str, Any]] = {
    "case": CASE_SCHEMA,
    "model": MODEL_SCHEMA,
    "run": RUN_SCHEMA,
    "compare": COMPARE_SCHEMA,
    "assess": ASSESS_SCHEMA,
}


def _type_matches(value: Any, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    return True


def validate_schema(value: Any, schema: Mapping[str, Any], path: str = "$") -> None:
    """Validate the JSON-Schema subset used by the five PaperSim contracts."""

    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, item) for item in expected_types):
            raise StoreError(f"{path}: expected {expected_types}, got {type(value).__name__}")
    if "enum" in schema and value not in schema["enum"]:
        raise StoreError(f"{path}: value {value!r} is not one of {schema['enum']!r}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise StoreError(f"{path}: string is shorter than {schema['minLength']}")
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            raise StoreError(f"{path}: string does not match {schema['pattern']!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise StoreError(f"{path}: value is below minimum {schema['minimum']}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise StoreError(f"{path}: missing required keys: {', '.join(missing)}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in properties:
                validate_schema(item, properties[key], child_path)
            elif additional is False:
                raise StoreError(f"{child_path}: additional property is not allowed")
            elif isinstance(additional, dict):
                validate_schema(item, additional, child_path)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_schema(item, schema["items"], f"{path}[{index}]")


def _validate_artifact(value: Mapping[str, Any], path: str) -> None:
    validate_schema(value, _artifact_schema(), path)
    actual = sha256_bytes(Path(value["path"]).read_bytes()) if Path(value["path"]).is_absolute() else None
    if actual is not None and actual != value["sha256"]:
        raise StoreError(f"{path}: artifact hash does not match file contents")


def validate_object(kind: str, data: Mapping[str, Any]) -> None:
    if kind not in SCHEMAS:
        raise StoreError(f"unknown object kind: {kind}")
    if not isinstance(data, dict):
        raise StoreError(f"{kind} object must be a JSON object")
    validate_schema(data, SCHEMAS[kind], f"$.{kind}")
    expected_schema = f"papersim.{kind}.v1"
    if data.get("schema_version") != expected_schema:
        raise StoreError(f"{kind}: schema_version must be {expected_schema}")
    if data["id"] != data["id"].strip():
        raise StoreError(f"{kind}.id must not have surrounding whitespace")
    if kind == "case":
        paper_ref = data["paper_ref"]
        if not paper_ref.get("path"):
            raise StoreError("case.paper_ref.path must not be empty")
    if kind == "model":
        for field in ("model_md", "model_spec"):
            artifact = data[field]
            if not isinstance(artifact, dict):
                raise StoreError(f"model.{field} must be an artifact reference")
            if Path(artifact["path"]).is_absolute():
                _validate_artifact(artifact, f"$.model.{field}")
    if kind == "run":
        for field in ("inputs", "logs", "artifacts"):
            for index, artifact in enumerate(data[field]):
                if Path(artifact["path"]).is_absolute():
                    _validate_artifact(artifact, f"$.run.{field}[{index}]")
    if kind in {"compare", "assess"} and not data["artifact_hashes"]:
        raise StoreError(f"{kind}.artifact_hashes must not be empty")


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"invalid JSON: {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise StoreError(f"JSON document must be an object: {source}")
    return value


def write_json(path: str | Path, value: Mapping[str, Any], *, replace: bool = True) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not replace:
        raise StoreError(f"canonical object already exists: {target}")
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)


def next_id(directory: Path, prefix: str, *, id_prefix: str | None = None) -> str:
    highest = 0
    if directory.exists():
        for item in directory.iterdir():
            if not item.is_file():
                raise StoreError(f"workspace directory contains a nested directory: {item}")
            if item.suffix != ".json":
                continue
            match = re.fullmatch(rf"{re.escape(prefix)}(\d+)\.json", item.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"{id_prefix or prefix}{highest + 1:04d}"


class Workspace:
    """The only writer for the canonical file-first workspace."""

    def __init__(self, root: str | Path, *, initialize: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        self.objects = self.root / "objects"
        self.artifacts = self.root / "artifacts"
        self.tmp = self.root / "tmp"
        if self.root.exists() and not self.root.is_dir():
            raise StoreError(f"workspace root is not a directory: {self.root}")
        if initialize:
            self.root.mkdir(parents=True, exist_ok=True)
            for directory in (self.objects, self.artifacts, self.tmp):
                directory.mkdir(exist_ok=True)
        self.validate_topology()

    def validate_topology(self) -> None:
        if not self.root.is_dir():
            raise StoreError(f"workspace does not exist: {self.root}")
        allowed = {self.objects.name, self.artifacts.name, self.tmp.name, "paper"}
        children = {item.name for item in self.root.iterdir()}
        extra = sorted(children - allowed)
        if extra:
            raise StoreError(f"workspace root may only contain objects, artifacts, tmp, and paper: {extra}")
        paper = self.root / "paper"
        if paper.exists():
            if not paper.is_dir():
                raise StoreError("workspace paper entry must be a directory")
            original = paper / "original"
            if original.exists():
                if not original.is_dir():
                    raise StoreError("workspace paper/original must be a directory")
                for item in original.iterdir():
                    if item.is_dir():
                        raise StoreError(f"workspace paper/original must be flat: {item}")
        for directory in (self.objects, self.artifacts, self.tmp):
            if not directory.is_dir():
                raise StoreError(f"workspace entry must be a directory: {directory}")
            for item in directory.iterdir():
                if item.is_dir():
                    raise StoreError(f"workspace directories must be flat: {item}")
        for item in self.objects.iterdir():
            if item.suffix != ".json":
                raise StoreError(f"objects directory contains a non-object file: {item.name}")
        for item in self.artifacts.iterdir():
            if not item.is_file():
                raise StoreError(f"artifacts directory contains a non-file: {item}")
        for item in self.tmp.iterdir():
            if not item.is_file():
                raise StoreError(f"tmp directory contains a nested directory: {item}")

    def next_id(self, kind: str, prefix: str) -> str:
        if kind not in OBJECT_KINDS:
            raise StoreError(f"unknown object kind: {kind}")
        file_prefix = {"case": "case_", "model": "model_m", "run": "run_r", "compare": "compare_c", "assess": "assess_a"}[kind]
        return next_id(self.objects, file_prefix, id_prefix=prefix)

    def object_path(self, kind: str, object_id: str) -> Path:
        if kind not in OBJECT_KINDS:
            raise StoreError(f"unknown object kind: {kind}")
        prefix = {"case": "case_", "model": "model_", "run": "run_", "compare": "compare_", "assess": "assess_"}[kind]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", object_id):
            raise StoreError(f"invalid object id: {object_id!r}")
        return self.objects / f"{prefix}{object_id}.json"

    def read_object(self, kind: str, object_id: str) -> dict[str, Any]:
        path = self.object_path(kind, object_id)
        if not path.is_file():
            raise StoreError(f"unknown {kind}: {object_id}")
        data = read_json(path)
        validate_object(kind, data)
        if data["id"] != object_id:
            raise StoreError(f"{kind} id mismatch: expected {object_id}, got {data['id']}")
        return data

    def write_object(self, kind: str, data: Mapping[str, Any], *, replace: bool = False) -> Path:
        validate_object(kind, data)
        path = self.object_path(kind, str(data["id"]))
        if path.exists() and not replace:
            raise StoreError(f"canonical {kind} already exists: {data['id']}")
        write_json(path, data, replace=replace)
        return path

    def put_artifact(
        self,
        source: str | Path | bytes,
        *,
        name: str | None = None,
        media_type: str = "application/octet-stream",
        replace: bool = False,
    ) -> dict[str, Any]:
        if isinstance(source, bytes):
            payload: bytes | None = source
            digest = sha256_bytes(payload)
            size = len(payload)
            source_path = None
        else:
            source_path = Path(source)
            if not source_path.is_file():
                raise StoreError(f"artifact source does not exist: {source_path}")
            payload = None
            digest = sha256(source_path)
            size = source_path.stat().st_size
        if name is None:
            destination_name = f"{digest}.bin"
        else:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
                raise StoreError(f"artifact name must be a flat filename: {name!r}")
            destination_name = name
        destination = self.artifacts / destination_name
        if destination.exists():
            if sha256(destination) != digest and not replace:
                raise StoreError(f"artifact name already has different content: {destination_name}")
        else:
            temporary = destination.with_name(destination.name + ".tmp")
            if payload is not None:
                temporary.write_bytes(payload)
            else:
                shutil.copy2(source_path, temporary)
            os.replace(temporary, destination)
        ref = {
            "name": destination_name if name else digest,
            "sha256": digest,
            "size": size,
            "media_type": media_type,
            "path": destination.name,
        }
        self._validate_artifact_ref(ref)
        return ref

    def register_local_artifact(self, path: str | Path, *, name: str | None = None, media_type: str = "application/octet-stream") -> dict[str, Any]:
        return self.put_artifact(path, name=name, media_type=media_type)

    def artifact_ref_path(self, ref: Mapping[str, Any]) -> Path:
        self._validate_artifact_ref(ref)
        raw = Path(str(ref["path"]))
        if raw.is_absolute():
            candidate = raw.resolve()
        else:
            candidate = (self.artifacts / raw.name).resolve()
        if candidate.parent != self.artifacts.resolve():
            raise StoreError(f"artifact is outside workspace artifacts: {raw}")
        if not candidate.is_file():
            raise StoreError(f"artifact does not exist: {candidate}")
        if sha256(candidate) != ref["sha256"]:
            raise StoreError(f"artifact hash mismatch: {candidate}")
        return candidate

    def _validate_artifact_ref(self, ref: Mapping[str, Any]) -> None:
        validate_schema(ref, _artifact_schema(), "$.artifact")
        raw = Path(str(ref["path"]))
        candidate = raw.resolve() if raw.is_absolute() else (self.artifacts / raw.name).resolve()
        if candidate.parent != self.artifacts.resolve():
            raise StoreError(f"artifact path must be a flat file in artifacts/: {ref['path']!r}")
        if candidate.exists() and sha256(candidate) != ref["sha256"]:
            raise StoreError(f"artifact hash mismatch: {candidate}")

    def validate_all(self) -> dict[str, int]:
        self.validate_topology()
        counts = {kind: 0 for kind in OBJECT_KINDS}
        artifact_files: dict[str, list[Path]] = {}
        for item in self.artifacts.iterdir():
            if item.is_file():
                artifact_files.setdefault(sha256(item), []).append(item)
        for path in sorted(self.objects.glob("*.json")):
            kind = path.stem.split("_", 1)[0]
            if kind not in counts:
                raise StoreError(f"unknown canonical object file: {path.name}")
            data = read_json(path)
            validate_object(kind, data)
            if data["id"] != path.stem.split("_", 1)[1]:
                raise StoreError(f"object file/id mismatch: {path.name}")
            for hash_value in data.get("artifact_hashes", {}).values():
                if kind == "case" and hash_value == data.get("paper_ref", {}).get("sha256"):
                    paper_path = Path(str(data["paper_ref"].get("path") or ""))
                    if not paper_path.is_file() or sha256(paper_path) != hash_value:
                        raise StoreError("case paper_ref hash does not match the canonical paper file")
                    continue
                if hash_value not in artifact_files:
                    raise StoreError(f"artifact hash is not present in workspace: {hash_value}")
            for artifact in self._artifact_values(data):
                raw = Path(str(artifact["path"]))
                candidate = raw.resolve() if raw.is_absolute() else (self.artifacts / raw.name).resolve()
                if candidate.parent != self.artifacts.resolve():
                    raise StoreError(f"artifact is outside workspace artifacts: {raw}")
                if not candidate.is_file():
                    raise StoreError(f"artifact does not exist: {candidate}")
                if artifact["sha256"] not in artifact_files:
                    raise StoreError(f"artifact hash is not present in workspace: {artifact['sha256']}")
            counts[kind] += 1
        return counts

    @staticmethod
    def _artifact_values(value: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(value, dict):
            if all(key in value for key in ARTIFACT_REQUIRED):
                yield value
            else:
                for child in value.values():
                    yield from Workspace._artifact_values(child)
        elif isinstance(value, list):
            for child in value:
                yield from Workspace._artifact_values(child)

    def append_case_ref(self, case_id: str, field: str, object_id: str) -> None:
        if field not in {"model_ids", "run_ids", "compare_ids", "assess_ids"}:
            raise StoreError(f"invalid case reference field: {field}")
        data = self.read_object("case", case_id)
        values = list(data[field])
        if object_id not in values:
            values.append(object_id)
        data[field] = values
        if field == "assess_ids":
            data["status"] = "assessed"
        elif data["status"] == "open":
            data["status"] = "in_progress"
        self.write_object("case", data, replace=True)


class PaperRepository:
    """Immutable canonical paper corpus with a JSON index."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        if not self.index_path.exists():
            write_json(self.index_path, {"schema_version": "papersim.paper_index.v1", "papers": []})
        self._validate_root()

    def _validate_root(self) -> None:
        for item in self.root.iterdir():
            if item.is_dir():
                raise StoreError(f"paper/original must be flat: {item}")
        data = read_json(self.index_path)
        if data.get("schema_version") != "papersim.paper_index.v1" or not isinstance(data.get("papers"), list):
            raise StoreError("invalid paper/original/index.json")
        seen_hashes: set[str] = set()
        for entry in data["papers"]:
            if not isinstance(entry, dict):
                raise StoreError("paper index entries must be objects")
            required = ("paper_id", "title", "filename", "sha256", "added_at")
            if any(not isinstance(entry.get(key), str) or not entry[key].strip() for key in required):
                raise StoreError(f"paper index entry is incomplete: {entry!r}")
            if re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) is None:
                raise StoreError(f"paper index has invalid sha256: {entry['paper_id']}")
            if entry["sha256"] in seen_hashes:
                raise StoreError(f"duplicate paper sha256 in index: {entry['sha256']}")
            seen_hashes.add(entry["sha256"])
            path = self.root / entry["filename"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise StoreError(f"paper index references missing or changed file: {entry['filename']}")

    def entries(self) -> list[dict[str, Any]]:
        return list(read_json(self.index_path)["papers"])

    def find(self, *, paper_id: str | None = None, sha256_value: str | None = None) -> dict[str, Any] | None:
        for entry in self.entries():
            if paper_id is not None and entry["paper_id"] == paper_id:
                return entry
            if sha256_value is not None and entry["sha256"] == sha256_value:
                return entry
        return None

    @staticmethod
    def _safe(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
        return safe or "paper"

    def register(self, source: str | Path, *, paper_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise StoreError(f"paper does not exist: {source_path}")
        digest = sha256(source_path)
        existing = self.find(sha256_value=digest)
        if existing is not None:
            return existing
        metadata = dict(metadata or {})
        title = str(metadata.get("title") or source_path.stem).strip()
        safe_id = self._safe(str(paper_id or metadata.get("paper_id") or source_path.stem))
        safe_title = self._safe(title)
        suffix = source_path.suffix.lower() or ".bin"
        filename = f"{safe_id}__{safe_title}{suffix}"
        target = self.root / filename
        if target.exists():
            if sha256(target) != digest:
                raise StoreError(f"paper filename is already occupied with different content: {filename}")
        else:
            shutil.copy2(source_path, target)
        entry = {
            "paper_id": safe_id,
            "title": title,
            "authors": list(metadata.get("authors") or []),
            "year": metadata.get("year"),
            "doi": metadata.get("doi"),
            "bibkey": metadata.get("bibkey"),
            "filename": filename,
            "sha256": digest,
            "added_at": utc_now(),
        }
        data = read_json(self.index_path)
        data["papers"].append(entry)
        write_json(self.index_path, data)
        return entry

    def ref(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        filename = str(entry["filename"])
        path = self.root / filename
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise StoreError(f"paper source is missing or changed: {filename}")
        result = dict(entry)
        result["path"] = str(path)
        return result

    def resolve(self, paper: str | Path | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(paper, Mapping):
            entry = dict(paper)
            filename = entry.get("filename")
            if not isinstance(filename, str):
                raise StoreError("paper_ref requires filename")
            path = self.root / filename
            if not path.is_file() or sha256(path) != entry.get("sha256"):
                raise StoreError(f"paper_ref does not match canonical file: {filename}")
            return self.ref(entry)
        path = Path(paper).expanduser().resolve()
        if not path.is_file():
            raise StoreError(f"paper does not exist: {path}")
        digest = sha256(path)
        existing = self.find(sha256_value=digest)
        if existing is not None:
            return self.ref(existing)
        # If the caller supplied a path in the canonical repository, register it
        # under its stable name without retaining the original spelling.
        return self.ref(self.register(path))
