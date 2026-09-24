"""Deterministic IR audit and approval gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .case_contracts import (
    AuditRecord,
    CheckResult,
    CheckStatus,
    EquationClass,
    Evidence,
    EvidenceSpec,
    IR,
    IterationState,
    ProfileModel,
    SourceKind,
    append_event,
    canonical_hash,
    sha256_bytes,
)
from .contracts import ContractError, StoreError
from .documents import PdfDocument, normalize_text
from .units import UnitValidator


RULE_VERSION = "papersim.ir-rules.v1"
_KNOWN_SYMBOLS = {
    "x",
    "y",
    "t",
    "dt",
    "px",
    "py",
    "Tx",
    "Ty",
    "p",
    "T",
    "pi",
}


class EvidenceVerifier(Protocol):
    def resolve(self, spec: EvidenceSpec) -> Evidence:
        ...


@dataclass
class PdfEvidenceVerifier:
    document: PdfDocument

    def resolve(self, spec: EvidenceSpec) -> Evidence:
        self.document._check_page(spec.page)
        page = self.document._document[spec.page - 1]
        quote = normalize_text(spec.quote)
        page_text = normalize_text(page.get_text("text"))
        if not quote or quote not in page_text:
            raise ContractError(f"evidence {spec.id!r} quote was not found on page {spec.page}")
        bbox = spec.bbox
        if bbox is None:
            matching = []
            quote_tokens = [token for token in quote.split(" ") if token]
            for line in self.document.lines(spec.page):
                normalized = normalize_text(line.text)
                if normalized and (normalized in quote or quote in normalized):
                    matching.append(line)
            if not matching:
                # OCR text often splits equations across physical lines. Use
                # all lines containing at least half of the quote tokens.
                token_set = {token.lower() for token in quote_tokens}
                for line in self.document.lines(spec.page):
                    line_tokens = {token.lower() for token in normalize_text(line.text).split(" ")}
                    if token_set and len(token_set & line_tokens) / len(token_set) >= 0.5:
                        matching.append(line)
            if not matching:
                raise ContractError(f"could not derive a bbox for evidence {spec.id!r}")
            bbox = (
                min(item.bbox[0] for item in matching),
                min(item.bbox[1] for item in matching),
                max(item.bbox[2] for item in matching),
                max(item.bbox[3] for item in matching),
            )
        x0, y0, x1, y1 = bbox
        rect = page.rect
        if not (0 <= x0 < x1 <= rect.x1 + 1e-6 and 0 <= y0 < y1 <= rect.y1 + 1e-6):
            raise ContractError(f"evidence {spec.id!r} has an invalid bbox")
        return Evidence(
            id=spec.id,
            page=spec.page,
            bbox=tuple(float(value) for value in bbox),
            quote=spec.quote,
            quote_sha256=sha256_bytes(normalize_text(spec.quote).encode("utf-8")),
            source_sha256=self.document.sha256,
            label=spec.label,
        )


@dataclass
class SyntheticEvidenceVerifier:
    """Test-only verifier for profiles that do not exercise PDF extraction."""

    source_sha256: str

    def resolve(self, spec: EvidenceSpec) -> Evidence:
        bbox = spec.bbox or (0.0, 0.0, 1.0, 1.0)
        return Evidence(
            id=spec.id,
            page=spec.page,
            bbox=bbox,
            quote=spec.quote,
            quote_sha256=sha256_bytes(normalize_text(spec.quote).encode("utf-8")),
            source_sha256=spec.source_hash or self.source_sha256,
            label=spec.label,
        )


def _check(
    entity_id: str,
    check_id: str,
    validator: str,
    passed: bool,
    *,
    reason: str = "",
    evidence: tuple[str, ...] = (),
    unknown: bool = False,
) -> CheckResult:
    status = CheckStatus.PASS if passed else (CheckStatus.UNKNOWN if unknown else CheckStatus.FAIL)
    return CheckResult(
        entity_id=entity_id,
        check_id=check_id,
        validator=validator,
        status=status,
        reason="" if passed else reason,
        evidence=evidence,
        rule_version=RULE_VERSION,
    )


def _source_requires_evidence(source: SourceKind) -> bool:
    return source in {SourceKind.PAPER, SourceKind.EXTRACTED}


def _symbols(profile: ProfileModel) -> set[str]:
    return (
        {item.id for item in profile.parameters}
        | {item.comsol_name for item in profile.parameters}
        | {item.id for item in profile.variables}
        | {item.comsol_name for item in profile.variables}
        | _KNOWN_SYMBOLS
    )


def audit_profile(
    *,
    case_id: str,
    iteration: int,
    paper_sha256: str,
    profile_sha256: str,
    profile: ProfileModel,
    verifier: EvidenceVerifier,
) -> tuple[AuditRecord, tuple[Evidence, ...]]:
    """Run every deterministic IR check and return an immutable audit record."""

    if profile.case_id != case_id:
        raise ContractError("profile case_id does not match audit case_id")
    checks: list[CheckResult] = []
    evidence: tuple[Evidence, ...]
    try:
        evidence = tuple(verifier.resolve(item) for item in profile.evidence)
        checks.append(_check(case_id, "evidence_anchors", "pdf-evidence", True))
    except Exception as exc:
        evidence = ()
        checks.append(_check(case_id, "evidence_anchors", "pdf-evidence", False, reason=str(exc)))

    if evidence:
        checks.append(
            _check(
                case_id,
                "evidence_source_hash",
                "sha256",
                all(item.source_sha256 == paper_sha256 for item in evidence),
                reason="one or more evidence anchors reference a different paper",
                evidence=tuple(item.id for item in evidence),
            )
        )

    unit_validator = UnitValidator()
    unit_failures: list[str] = []
    for parameter in profile.parameters:
        result = unit_validator.validate_parameter(
            float(parameter.value) if parameter.value is not None else None,
            parameter.units,
            expression=parameter.expression,
        )
        if not result["passed"]:
            unit_failures.append(parameter.id)
    for variable in profile.variables:
        if not unit_validator.parse(variable.units).passed:
            unit_failures.append(variable.id)
    checks.append(
        _check(
            case_id,
            "units",
            "pint",
            not unit_failures,
            reason=f"invalid units or values: {sorted(unit_failures)}",
        )
    )

    classification_failures: list[str] = []
    for equation in profile.equations:
        if equation.classification == EquationClass.CONTROL and not equation.dependent_variables:
            classification_failures.append(equation.id)
        if equation.classification == EquationClass.CONTROL and not equation.comsol_features:
            classification_failures.append(equation.id)
        if equation.classification == EquationClass.CONSTITUTIVE and equation.comsol_features:
            classification_failures.append(equation.id)
    checks.append(
        _check(
            case_id,
            "equation_classification",
            "comsol-modeling-r1",
            not classification_failures,
            reason=f"classification/feature mismatch: {sorted(set(classification_failures))}",
        )
    )

    known_symbols = _symbols(profile)
    unknown_symbols: list[str] = []
    for equation in profile.equations:
        for symbol in equation.referenced_symbols:
            if symbol not in known_symbols:
                unknown_symbols.append(f"{equation.id}:{symbol}")
    checks.append(
        _check(
            case_id,
            "symbol_closure",
            "symbol-table",
            not unknown_symbols,
            reason=f"undefined symbols: {sorted(unknown_symbols)}",
        )
    )

    evidence_required: list[str] = []
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
        for item in getattr(profile, collection_name):
            source = getattr(item, "source", None)
            if source is not None and _source_requires_evidence(source) and not item.evidence_ids:
                evidence_required.append(f"{collection_name}:{item.id}")
    checks.append(
        _check(
            case_id,
            "evidence_coverage",
            "evidence-map",
            not evidence_required,
            reason=f"paper-derived entities lack evidence: {evidence_required}",
        )
    )

    parameter_symbols = {item.comsol_name for item in profile.parameters} | {item.symbol for item in profile.parameters}
    variable_symbols = {item.comsol_name for item in profile.variables} | {item.symbol for item in profile.variables}
    dependency_failures: list[str] = []
    for boundary in profile.boundary_conditions:
        if boundary.variable not in parameter_symbols | variable_symbols | set(profile.dependent_variables):
            dependency_failures.append(boundary.id)
    for initial in profile.initial_conditions:
        if initial.variable not in parameter_symbols | variable_symbols | set(profile.dependent_variables):
            dependency_failures.append(initial.id)
    checks.append(
        _check(
            case_id,
            "boundary_initial_references",
            "reference-closure",
            not dependency_failures,
            reason=f"unknown boundary/initial variables: {dependency_failures}",
        )
    )

    output_metrics = {item.id for item in profile.outputs}
    acceptance_metrics = {item.metric for item in profile.acceptance}
    unknown_metrics = sorted(acceptance_metrics - output_metrics)
    checks.append(
        _check(
            case_id,
            "acceptance_metrics",
            "acceptance-contract",
            bool(profile.acceptance) and not unknown_metrics,
            reason=f"acceptance references unknown output metrics: {unknown_metrics}",
        )
    )

    checks.append(
        _check(
            case_id,
            "open_gaps_blocking",
            "fail-closed",
            not profile.open_gaps,
            reason=f"open gaps must be resolved before modeling: {list(profile.open_gaps)}",
            unknown=True,
        )
    )

    audit = AuditRecord(
        case_id=case_id,
        iteration=iteration,
        state=IterationState.IR_AUDITED,
        paper_sha256=paper_sha256,
        profile_sha256=profile_sha256,
        checks=tuple(checks),
        approval=None,
    )
    audit = append_event(audit, actor="papersim", action="audit_ir", stage="ir", detail={"checks": len(checks)})
    return audit, evidence


def audit_hash(record: AuditRecord) -> str:
    payload = record.model_dump(mode="json", exclude={"approval", "state"})
    payload.pop("events", None)
    payload["checks"] = [
        item
        for item in payload.get("checks", [])
        if item.get("validator") not in {"comsol-readback", "numeric-audit"}
    ]
    payload["comsol_snapshot"] = {}
    payload["numerical_checks"] = []
    payload["comparison"] = {}
    payload["assessment"] = {}
    return canonical_hash(payload)


def approve(
    record: AuditRecord,
    *,
    approved_by: str,
    reason: str,
    test_only: bool = False,
) -> AuditRecord:
    if record.state != IterationState.IR_AUDITED:
        raise ContractError("only an audited IR can be approved")
    failing = [item.check_id for item in record.checks if not item.passed]
    if failing:
        raise ContractError(f"IR audit has blocking checks: {failing}")
    if test_only and not approved_by.startswith("test-only:"):
        raise ContractError("test-only approval identity must start with 'test-only:'")
    from .case_contracts import Approval

    approval = Approval(
        approved_by=approved_by,
        reason=reason,
        case_id=record.case_id,
        iteration=record.iteration,
        paper_sha256=record.paper_sha256,
        profile_sha256=record.profile_sha256,
        ir_sha256=record.ir_sha256,
        audit_sha256=audit_hash(record),
        rule_version=RULE_VERSION,
    )
    updated = record.model_copy(update={"approval": approval, "state": IterationState.APPROVED})
    return append_event(updated, actor=approved_by, action="approve_ir", stage="approval", detail={"test_only": test_only})


def build_ir(
    *,
    case_id: str,
    iteration: int,
    paper_filename: str,
    paper_sha256: str,
    profile_sha256: str,
    profile: ProfileModel,
    audit: AuditRecord,
    evidence: tuple[Evidence, ...],
) -> IR:
    failing = [item.check_id for item in audit.checks if not item.passed]
    if failing:
        raise ContractError(f"cannot build an approved IR while audit checks fail: {failing}")
    ir = IR(
        case_id=case_id,
        iteration=iteration,
        paper_filename=paper_filename,
        paper_sha256=paper_sha256,
        profile_sha256=profile_sha256,
        scope=profile.scope,
        profile=profile,
        evidence=evidence,
    ).with_hash()
    return ir


def audit_pdf_profile(
    *,
    case_id: str,
    iteration: int,
    paper_path: str | Path,
    paper_sha256: str,
    profile_sha256: str,
    profile: ProfileModel,
) -> tuple[AuditRecord, tuple[Evidence, ...], IR]:
    document = PdfDocument(paper_path)
    try:
        if document.sha256 != paper_sha256:
            raise StoreError("PDF hash changed before IR audit")
        audit, evidence = audit_profile(
            case_id=case_id,
            iteration=iteration,
            paper_sha256=paper_sha256,
            profile_sha256=profile_sha256,
            profile=profile,
            verifier=PdfEvidenceVerifier(document),
        )
    finally:
        document.close()
    ir = build_ir(
        case_id=case_id,
        iteration=iteration,
        paper_filename=Path(paper_path).name,
        paper_sha256=paper_sha256,
        profile_sha256=profile_sha256,
        profile=profile,
        audit=audit,
        evidence=evidence,
    )
    return audit, evidence, ir


def ensure_approved(record: AuditRecord, ir: IR) -> None:
    if record.state not in {
        IterationState.APPROVED,
        IterationState.JAVA_GENERATED,
        IterationState.BUILT,
        IterationState.IMPLEMENTATION_AUDITED,
        IterationState.SOLVED,
        IterationState.NUMERICAL_AUDITED,
        IterationState.COMPARED,
        IterationState.ASSESSED,
    }:
        raise ContractError("IR is not approved")
    if record.approval is None:
        raise ContractError("IR approval record is missing")
    if record.approval.ir_sha256 != ir.ir_hash:
        raise ContractError("IR changed after approval")
    if record.approval.profile_sha256 != ir.profile_sha256:
        raise ContractError("profile changed after approval")
    if record.approval.paper_sha256 != ir.paper_sha256:
        raise ContractError("paper changed after approval")
    if record.approval.audit_sha256 != audit_hash(record):
        raise ContractError("IR audit changed after approval")
