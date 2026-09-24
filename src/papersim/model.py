from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .contracts import ContractError


REQUIRED_MODEL_SECTIONS = (
    "Scope",
    "Variables",
    "Governing Equations",
    "Constitutive Equations",
    "Parameters",
    "Initial Conditions",
    "Boundary Conditions",
    "Assumptions",
    "Solver Mapping",
    "Outputs",
    "Evidence",
    "Open Gaps",
    "Change Log",
)

REQUIRED_SPEC_KEYS = (
    "scope",
    "variables",
    "governing_equations",
    "constitutive_equations",
    "parameters",
    "initial_conditions",
    "boundary_conditions",
    "assumptions",
    "solver",
    "outputs",
    "acceptance",
    "evidence",
    "open_gaps",
    "assessment",
    "unresolved_questions",
)

_SOURCES = {"paper", "extracted", "inference", "assumption", "gap"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _heading_set(markdown: str) -> set[str]:
    return {match.group(1).strip() for match in re.finditer(r"(?m)^##\s+(.+?)\s*$", markdown)}


def validate_model_markdown(markdown: str) -> None:
    if not markdown.strip():
        raise ContractError("model.md must not be empty")
    headings = _heading_set(markdown)
    missing = [section for section in REQUIRED_MODEL_SECTIONS if section not in headings]
    if missing:
        raise ContractError("model.md is missing required sections: " + ", ".join(missing))
    if "# Model" not in markdown:
        raise ContractError("model.md must contain the '# Model' title")


def _require_list(spec: Mapping[str, Any], key: str) -> list[Any]:
    value = spec.get(key)
    if not isinstance(value, list):
        raise ContractError(f"model.spec.json.{key} must be a list")
    return value


def _evidence_refs(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"model.spec.json.{field} must be a list of evidence strings")
    return value


def _validate_entries(entries: list[Any], field: str, required: tuple[str, ...], *, string_fields: tuple[str, ...] = ()) -> None:
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ContractError(f"model.spec.json.{field}[{index}] must be an object")
        for key in required:
            value = entry.get(key)
            if key in string_fields:
                if not isinstance(value, str) or not value.strip():
                    raise ContractError(f"model.spec.json.{field}[{index}].{key} must be a non-empty string")
            elif value is None:
                raise ContractError(f"model.spec.json.{field}[{index}].{key} must not be null")
        source = entry.get("source")
        if source not in _SOURCES:
            raise ContractError(f"model.spec.json.{field}[{index}].source must be one of {sorted(_SOURCES)}")
        _evidence_refs(entry.get("evidence", []), f"{field}[{index}].evidence")


def validate_model_spec(spec: Mapping[str, Any]) -> None:
    if not isinstance(spec, dict):
        raise ContractError("model.spec.json must be a JSON object")
    missing = [key for key in REQUIRED_SPEC_KEYS if key not in spec]
    if missing:
        raise ContractError("model.spec.json is missing required keys: " + ", ".join(missing))

    scope = spec["scope"]
    if not isinstance(scope, str) or not scope.strip():
        raise ContractError("model.spec.json.scope must be a non-empty string")

    variables = _require_list(spec, "variables")
    _validate_entries(variables, "variables", ("id", "symbol", "meaning"), string_fields=("id", "symbol", "meaning"))
    equations = _require_list(spec, "governing_equations")
    _validate_entries(equations, "governing_equations", ("id", "expression"), string_fields=("id", "expression"))
    constitutive = _require_list(spec, "constitutive_equations")
    _validate_entries(constitutive, "constitutive_equations", ("id", "expression"), string_fields=("id", "expression"))
    parameters = _require_list(spec, "parameters")
    _validate_entries(parameters, "parameters", ("id", "name", "value", "units"), string_fields=("id", "name", "units"))
    initial = _require_list(spec, "initial_conditions")
    _validate_entries(initial, "initial_conditions", ("id", "variable", "value"), string_fields=("id", "variable"))
    boundary = _require_list(spec, "boundary_conditions")
    _validate_entries(boundary, "boundary_conditions", ("id", "variable", "condition"), string_fields=("id", "variable", "condition"))
    assumptions = _require_list(spec, "assumptions")
    _validate_entries(assumptions, "assumptions", ("id", "statement"), string_fields=("id", "statement"))
    gaps = _require_list(spec, "open_gaps")
    for index, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            raise ContractError(f"model.spec.json.open_gaps[{index}] must be an object")
        if not isinstance(gap.get("id"), str) or not gap["id"].strip():
            raise ContractError(f"model.spec.json.open_gaps[{index}].id must be a non-empty string")
        if not isinstance(gap.get("description"), str) or not gap["description"].strip():
            raise ContractError(f"model.spec.json.open_gaps[{index}].description must be a non-empty string")
        if gap.get("source") not in {"paper", "extracted", "inference", "assumption", "gap"}:
            raise ContractError(f"model.spec.json.open_gaps[{index}].source is invalid")
        _evidence_refs(gap.get("evidence", []), f"open_gaps[{index}].evidence")

    solver = spec["solver"]
    if not isinstance(solver, dict) or not isinstance(solver.get("backend"), str) or not solver["backend"].strip():
        raise ContractError("model.spec.json.solver requires a non-empty backend")
    outputs = _require_list(spec, "outputs")
    if not outputs:
        raise ContractError("model.spec.json.outputs must contain at least one output")
    for index, output in enumerate(outputs):
        if not isinstance(output, dict) or not all(
            isinstance(output.get(key), str) and output[key].strip() for key in ("id", "name", "units")
        ):
            raise ContractError(f"model.spec.json.outputs[{index}] requires id, name, units")
    acceptance = _require_list(spec, "acceptance")
    if not acceptance:
        raise ContractError("model.spec.json.acceptance must contain at least one criterion")
    for index, criterion in enumerate(acceptance):
        if not isinstance(criterion, dict):
            raise ContractError(f"model.spec.json.acceptance[{index}] must be an object")
        for key in ("id", "metric", "operator"):
            if not isinstance(criterion.get(key), str) or not criterion[key].strip():
                raise ContractError(f"model.spec.json.acceptance[{index}].{key} must be non-empty")
        if criterion["operator"] not in {"<", "<=", ">", ">=", "==", "relative_error_le", "between"}:
            raise ContractError(f"unsupported acceptance operator at index {index}")
        if criterion["operator"] == "relative_error_le":
            if "expected" not in criterion or "tolerance" not in criterion:
                raise ContractError("relative_error_le acceptance requires expected and tolerance")
        elif criterion["operator"] == "between":
            expected = criterion.get("expected")
            if not isinstance(expected, list) or len(expected) != 2:
                raise ContractError("between acceptance requires a two-element expected list")
        elif "expected" not in criterion:
            raise ContractError(f"acceptance criterion {criterion['id']} requires expected")
    _evidence_refs(spec["evidence"], "evidence")
    assessment = spec["assessment"]
    if not isinstance(assessment, dict):
        raise ContractError("model.spec.json.assessment must be an object")
    for key in ("verdict_on_pass", "verdict_on_fail"):
        if assessment.get(key) not in {"supported", "qualified", "questioned", "not_reproduced", "underdetermined"}:
            raise ContractError(f"model.spec.json.assessment.{key} is invalid")
    questions = spec["unresolved_questions"]
    if not isinstance(questions, list) or not all(isinstance(item, str) for item in questions):
        raise ContractError("model.spec.json.unresolved_questions must be a list of strings")


def canonical_spec(spec: Mapping[str, Any], markdown: str) -> dict[str, Any]:
    value = dict(spec)
    value["source_md_sha256"] = sha256_bytes(markdown.encode("utf-8"))
    return value


def model_spec_digest(spec: Mapping[str, Any]) -> str:
    payload = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def draft_from_dir(directory: str | Path) -> tuple[str, dict[str, Any]]:
    root = Path(directory).expanduser().resolve()
    markdown_path = root / "model.md"
    spec_path = root / "model.spec.json"
    if not markdown_path.is_file():
        raise ContractError("model draft requires model.md")
    if not spec_path.is_file():
        raise ContractError("model draft requires model.spec.json")
    markdown = markdown_path.read_text(encoding="utf-8")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid model.spec.json: {exc}") from exc
    if not isinstance(spec, dict):
        raise ContractError("model.spec.json must be an object")
    validate_model_markdown(markdown)
    validate_model_spec(spec)
    return markdown, spec


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
