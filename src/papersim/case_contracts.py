"""Canonical, LLM-independent contracts for PaperSim case iterations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import ContractError


SCHEMA_VERSION = "papersim.case.v1"
CASE_ID_RE = re.compile(r"^[a-z][a-z0-9]*[0-9]{4}_[a-z][a-z0-9]*$")
ITERATION_RE = re.compile(r"^iter([0-9]{3,})$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
JAVA_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EquationClass(str, Enum):
    CONTROL = "control"
    CONSTITUTIVE = "constitutive"
    AUXILIARY = "auxiliary"
    BOUNDARY = "boundary"
    INITIAL = "initial"


class SourceKind(str, Enum):
    PAPER = "paper"
    EXTRACTED = "extracted"
    INFERENCE = "inference"
    ASSUMPTION = "assumption"
    GAP = "gap"
    NUMERICS = "numerics"
    REPRODUCED_OBSERVATION = "reproduced_observation"
    CONSTITUTIVE = "constitutive"
    AUXILIARY = "auxiliary"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class IterationState(str, Enum):
    CREATED = "created"
    IR_EXTRACTED = "ir_extracted"
    IR_AUDITED = "ir_audited"
    APPROVED = "approved"
    JAVA_GENERATED = "java_generated"
    BUILT = "built"
    IMPLEMENTATION_AUDITED = "implementation_audited"
    SOLVED = "solved"
    NUMERICAL_AUDITED = "numerical_audited"
    COMPARED = "compared"
    ASSESSED = "assessed"
    BLOCKED = "blocked"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def normalize_component(value: str, field: str) -> str:
    stripped = value.strip()
    if re.fullmatch(r"[A-Za-z0-9]+", stripped) is None:
        raise ContractError(f"{field} must contain only ASCII letters or digits")
    return stripped.lower()


def make_case_id(surname: str, year: int, topic: str) -> str:
    """Return the only accepted PaperSim case identifier format."""

    normalized_surname = normalize_component(surname, "first-author surname")
    if not normalized_surname:
        raise ContractError("first-author surname is empty")
    if year < 1000 or year > 9999:
        raise ContractError("year must be a four-digit integer")
    normalized_topic = normalize_component(topic, "topic word")
    if not normalized_topic:
        raise ContractError("topic word is empty")
    identifier = f"{normalized_surname}{year}_{normalized_topic}"
    if CASE_ID_RE.fullmatch(identifier) is None:
        raise ContractError(f"generated case id is invalid: {identifier!r}")
    return identifier


def java_class_name(case_id: str, suffix: str) -> str:
    if CASE_ID_RE.fullmatch(case_id) is None:
        raise ContractError(f"invalid case id: {case_id!r}")
    if not JAVA_IDENTIFIER_RE.fullmatch(suffix):
        raise ContractError(f"invalid Java class suffix: {suffix!r}")
    words = re.split(r"[_]+", case_id)
    base = "".join(word[:1].upper() + word[1:] for word in words)
    name = f"{base}{suffix}"
    if JAVA_IDENTIFIER_RE.fullmatch(name) is None:
        raise ContractError(f"invalid generated Java class name: {name!r}")
    return name


def validate_iteration(iteration: int) -> int:
    if iteration < 1 or iteration > 9999:
        raise ContractError("iteration must be between 1 and 9999")
    return iteration


def iteration_name(iteration: int) -> str:
    return f"iter{validate_iteration(iteration):03d}"


class EvidenceSpec(StrictModel):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)
    bbox: tuple[float, float, float, float] | None = None
    source_hash: str | None = None
    label: str = ""

    @field_validator("source_hash")
    @classmethod
    def source_hash_format(cls, value: str | None) -> str | None:
        if value is not None and SHA256_RE.fullmatch(value) is None:
            raise ValueError("source_hash must be a SHA-256 hex digest")
        return value


class Evidence(StrictModel):
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    quote: str = Field(min_length=1)
    quote_sha256: str
    source_sha256: str
    label: str = ""

    @field_validator("quote_sha256", "source_sha256")
    @classmethod
    def digest_format(cls, value: str) -> str:
        if SHA256_RE.fullmatch(value) is None:
            raise ValueError("evidence hashes must be SHA-256 hex digests")
        return value


class ParameterSpec(StrictModel):
    id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    comsol_name: str = Field(min_length=1)
    value: float | int | None = None
    expression: str | None = None
    units: str = "1"
    meaning: str = Field(min_length=1)
    source: SourceKind
    evidence_ids: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def value_or_expression(self) -> "ParameterSpec":
        if self.value is None and not self.expression:
            raise ValueError(f"parameter {self.id} requires value or expression")
        return self


class VariableSpec(StrictModel):
    id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    group: str = Field(min_length=1)
    comsol_name: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    units: str = "1"
    description: str = Field(min_length=1)
    source: SourceKind
    evidence_ids: tuple[str, ...] = ()


class EquationSpec(StrictModel):
    id: str = Field(min_length=1)
    number: int | None = None
    classification: EquationClass
    latex: str = Field(min_length=1)
    canonical: str = Field(min_length=1)
    dependent_variables: tuple[str, ...] = ()
    referenced_symbols: tuple[str, ...] = ()
    comsol_features: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class BoundaryConditionSpec(StrictModel):
    id: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    selection: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    source: SourceKind
    evidence_ids: tuple[str, ...] = ()


class InitialConditionSpec(StrictModel):
    id: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    source: SourceKind
    evidence_ids: tuple[str, ...] = ()


class GeometrySpec(StrictModel):
    id: str = Field(min_length=1)
    dimension: int = Field(ge=1, le=3)
    description: str = Field(min_length=1)
    parameters: tuple[str, ...] = ()
    source: SourceKind
    evidence_ids: tuple[str, ...] = ()


class MeshSpec(StrictModel):
    id: str = Field(default="mesh1")
    description: str = Field(min_length=1)
    settings: dict[str, Any]
    source: SourceKind = SourceKind.NUMERICS
    evidence_ids: tuple[str, ...] = ()


class SolverSpec(StrictModel):
    id: str = Field(default="solver1")
    backend: str = Field(min_length=1)
    version: str = Field(min_length=1)
    settings: dict[str, Any]
    source: SourceKind = SourceKind.NUMERICS
    evidence_ids: tuple[str, ...] = ()


class OutputSpec(StrictModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    units: str = Field(min_length=1)
    condition: str = ""
    source: SourceKind
    evidence_ids: tuple[str, ...] = ()


class ObservationSpec(StrictModel):
    id: str = Field(min_length=1)
    quantity: str = Field(min_length=1)
    value: float | int
    units: str = Field(min_length=1)
    condition: str = ""
    source: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = ()


class AcceptanceCriterion(StrictModel):
    id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: Literal["<", "<=", ">", ">=", "==", "relative_error_le", "between"]
    expected: float | int | list[float | int] | None = None
    tolerance: float | None = None
    required: bool = True

    @model_validator(mode="after")
    def operator_shape(self) -> "AcceptanceCriterion":
        if self.operator == "relative_error_le":
            if self.expected is None or self.tolerance is None:
                raise ValueError("relative_error_le requires expected and tolerance")
        elif self.operator == "between":
            if not isinstance(self.expected, list) or len(self.expected) != 2:
                raise ValueError("between requires two expected values")
        elif self.expected is None:
            raise ValueError(f"{self.operator} requires expected")
        return self


class ProfileModel(StrictModel):
    schema_version: Literal["papersim.profile.v1"] = "papersim.profile.v1"
    case_id: str
    paper_title: str = Field(min_length=1)
    first_author_surname: str = Field(min_length=1)
    year: int
    topic: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    dependent_variables: tuple[str, ...] = ()
    evidence: tuple[EvidenceSpec, ...]
    parameters: tuple[ParameterSpec, ...]
    variables: tuple[VariableSpec, ...]
    equations: tuple[EquationSpec, ...]
    boundary_conditions: tuple[BoundaryConditionSpec, ...]
    initial_conditions: tuple[InitialConditionSpec, ...]
    geometry: tuple[GeometrySpec, ...]
    mesh: MeshSpec
    solver: SolverSpec
    outputs: tuple[OutputSpec, ...]
    observations: tuple[ObservationSpec, ...]
    acceptance: tuple[AcceptanceCriterion, ...]
    assumptions: tuple[str, ...] = ()
    open_gaps: tuple[str, ...] = ()
    comsol_templates: dict[str, str] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def case_id_format(cls, value: str) -> str:
        if CASE_ID_RE.fullmatch(value) is None:
            raise ValueError("case_id must match lowercase surname+year_topic")
        return value

    @model_validator(mode="after")
    def validate_refs(self) -> "ProfileModel":
        if self.case_id != make_case_id(self.first_author_surname, self.year, self.topic):
            raise ValueError("case_id is not derived from surname, year and topic")
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("profile evidence ids must be unique")
        known = set(evidence_ids)
        for collection_name in (
            "parameters",
            "variables",
            "equations",
            "boundary_conditions",
            "initial_conditions",
            "geometry",
            "outputs",
            "observations",
        ):
            for item in getattr(self, collection_name):
                unknown = set(item.evidence_ids) - known
                if unknown:
                    raise ValueError(f"{collection_name} {item.id} references unknown evidence: {sorted(unknown)}")
        parameter_ids = {item.id for item in self.parameters}
        for equation in self.equations:
            unknown = set(equation.dependent_variables) - parameter_ids - {item.id for item in self.variables} - set(self.dependent_variables)
            if unknown:
                raise ValueError(f"equation {equation.id} references unknown dependent variables: {sorted(unknown)}")
        return self


class IR(StrictModel):
    schema_version: Literal["papersim.ir.v1"] = "papersim.ir.v1"
    case_id: str
    iteration: int = Field(ge=1, le=9999)
    paper_filename: str = Field(min_length=1)
    paper_sha256: str
    profile_sha256: str
    scope: str = Field(min_length=1)
    profile: ProfileModel
    evidence: tuple[Evidence, ...]
    created_at: str = Field(default_factory=utc_now)
    ir_hash: str = ""

    @field_validator("paper_sha256", "profile_sha256")
    @classmethod
    def digest_format(cls, value: str) -> str:
        if SHA256_RE.fullmatch(value) is None:
            raise ValueError("IR hashes must be SHA-256 hex digests")
        return value

    @model_validator(mode="after")
    def validate_case(self) -> "IR":
        if self.case_id != self.profile.case_id:
            raise ValueError("IR case_id must match profile case_id")
        return self

    def with_hash(self) -> "IR":
        payload = self.model_dump(mode="json", exclude={"ir_hash"})
        return self.model_copy(update={"ir_hash": canonical_hash(payload)})

    def verify_hash(self) -> bool:
        return self.ir_hash == self.with_hash().ir_hash


class CheckResult(StrictModel):
    entity_id: str = Field(min_length=1)
    check_id: str = Field(min_length=1)
    validator: str = Field(min_length=1)
    status: CheckStatus
    evidence: tuple[str, ...] = ()
    reason: str = ""
    rule_version: str = SCHEMA_VERSION

    @property
    def passed(self) -> bool:
        return self.status in {CheckStatus.PASS, CheckStatus.NOT_APPLICABLE}


class AuditEvent(StrictModel):
    timestamp: str = Field(default_factory=utc_now)
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    previous_event_hash: str | None = None
    event_hash: str = ""

    def with_hash(self) -> "AuditEvent":
        payload = self.model_dump(mode="json", exclude={"event_hash"})
        return self.model_copy(update={"event_hash": canonical_hash(payload)})


class Approval(StrictModel):
    approved_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    approved_at: str = Field(default_factory=utc_now)
    case_id: str
    iteration: int = Field(ge=1)
    paper_sha256: str
    profile_sha256: str
    ir_sha256: str
    audit_sha256: str
    rule_version: str = SCHEMA_VERSION


class AuditRecord(StrictModel):
    schema_version: Literal["papersim.audit.v1"] = "papersim.audit.v1"
    case_id: str
    iteration: int = Field(ge=1, le=9999)
    state: IterationState = IterationState.CREATED
    paper_sha256: str
    profile_sha256: str
    ir_sha256: str = ""
    checks: tuple[CheckResult, ...] = ()
    approval: Approval | None = None
    events: tuple[AuditEvent, ...] = ()
    comsol_snapshot: dict[str, Any] = Field(default_factory=dict)
    numerical_checks: tuple[CheckResult, ...] = ()
    comparison: dict[str, Any] = Field(default_factory=dict)
    assessment: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def approval_matches(self) -> "AuditRecord":
        if self.approval is not None:
            if self.approval.case_id != self.case_id or self.approval.iteration != self.iteration:
                raise ValueError("approval case/iteration mismatch")
            values = (
                self.approval.paper_sha256 == self.paper_sha256,
                self.approval.profile_sha256 == self.profile_sha256,
                self.approval.ir_sha256 == self.ir_sha256,
            )
            if not all(values):
                raise ValueError("approval hashes do not match the current case, profile and IR")
        return self


class CaseManifest(StrictModel):
    schema_version: Literal["papersim.case_manifest.v1"] = "papersim.case_manifest.v1"
    case_id: str
    first_author_surname: str = Field(min_length=1)
    year: int
    topic: str = Field(min_length=1)
    paper_filename: str = Field(min_length=1)
    paper_sha256: str
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    created_at: str = Field(default_factory=utc_now)
    latest_iteration: int = Field(default=0, ge=0)
    state: str = "created"
    legacy_artifacts: dict[str, str] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def case_id_format(cls, value: str) -> str:
        if CASE_ID_RE.fullmatch(value) is None:
            raise ValueError("invalid case id")
        return value

    @field_validator("paper_sha256")
    @classmethod
    def paper_hash_format(cls, value: str) -> str:
        if SHA256_RE.fullmatch(value) is None:
            raise ValueError("paper_sha256 must be a SHA-256 digest")
        return value

    @model_validator(mode="after")
    def identity_matches(self) -> "CaseManifest":
        if self.case_id != make_case_id(self.first_author_surname, self.year, self.topic):
            raise ValueError("case manifest identity does not produce case_id")
        if self.paper_filename != f"{self.case_id}_paper.pdf":
            raise ValueError("paper filename must be <case_id>_paper.pdf")
        return self


def model_json_bytes(model: BaseModel) -> bytes:
    return canonical_json_bytes(model.model_dump(mode="json"))


def load_case_manifest(path: str | Path) -> CaseManifest:
    return CaseManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | Path) -> ProfileModel:
    return ProfileModel.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_ir(path: str | Path) -> IR:
    return IR.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_audit(path: str | Path) -> AuditRecord:
    return AuditRecord.model_validate_json(Path(path).read_text(encoding="utf-8"))


def append_event(record: AuditRecord, *, actor: str, action: str, stage: str, detail: Mapping[str, Any] | None = None) -> AuditRecord:
    previous = record.events[-1].event_hash if record.events else None
    event = AuditEvent(
        actor=actor,
        action=action,
        stage=stage,
        detail=dict(detail or {}),
        previous_event_hash=previous,
    ).with_hash()
    return record.model_copy(update={"events": record.events + (event,)})
