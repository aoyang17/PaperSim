"""Independent deterministic review of extracted equations and parameters."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .contracts import ContractError
from .documents import PdfDocument
from .extraction import ExtractionBundle


@dataclass(frozen=True)
class ReviewFinding:
    severity: str
    area: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractionReview:
    decision: str
    findings: tuple[ReviewFinding, ...]
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "passed": self.passed,
            "findings": [item.as_dict() for item in self.findings],
        }


def review_extraction(bundle: ExtractionBundle) -> ExtractionReview:
    document = PdfDocument(bundle.source_path)
    findings: list[ReviewFinding] = []
    try:
        if document.sha256 != bundle.source_sha256:
            findings.append(ReviewFinding("fail", "source", "PDF hash differs from extraction source hash"))
        equation_evidence = [item for equation in bundle.equations for item in equation.evidence]
        parameter_evidence = [item for parameter in bundle.parameters for item in parameter.evidence]
        relation_evidence = [item for relation in bundle.relations for item in relation.evidence]
        evidence_result = document.validate_evidence([*equation_evidence, *parameter_evidence, *relation_evidence])
        for item in evidence_result["findings"]:
            if not item["passed"]:
                findings.append(
                    ReviewFinding(
                        "fail",
                        "evidence",
                        f"{item['label']} failed source validation: {item}",
                    )
                )

        if not bundle.equations:
            findings.append(ReviewFinding("fail", "equations", "no equations extracted"))
        for equation in bundle.equations:
            if not equation.latex.strip():
                findings.append(ReviewFinding("fail", "equations", f"Eq. ({equation.number}) has empty LaTeX"))
            if equation.classification not in {"control", "constitutive", "auxiliary", "boundary", "initial"}:
                findings.append(
                    ReviewFinding("fail", "equations", f"Eq. ({equation.number}) has invalid classification")
                )
            if equation.raw_text.strip() == "":
                findings.append(
                    ReviewFinding("fail", "equations", f"Eq. ({equation.number}) has no raw source region")
                )

        for parameter in bundle.parameters:
            if not parameter.unit_check.get("passed"):
                findings.append(
                    ReviewFinding("fail", "units", f"parameter {parameter.source_symbol} failed unit validation")
                )
            if parameter.value is None and not parameter.expression:
                findings.append(
                    ReviewFinding("fail", "parameters", f"parameter {parameter.source_symbol} has no value or expression")
                )

        for check_id, check in bundle.unit_equation_checks.items():
            if not check.get("passed"):
                findings.append(ReviewFinding("fail", "units", f"equation unit check failed: {check_id}"))

        known_symbols = {item.source_symbol for item in bundle.parameters}
        known_symbols.update(symbol for equation in bundle.equations for symbol in equation.referenced_symbols)
        for relation in bundle.relations:
            if not relation.relation.strip():
                findings.append(ReviewFinding("fail", "relations", f"relation {relation.id} has no expression"))
            missing = [item for item in relation.source_symbols if item not in known_symbols]
            if relation.target_symbol not in known_symbols:
                missing.append(relation.target_symbol)
            for symbol in missing:
                findings.append(
                    ReviewFinding("review", "relations", f"relation {relation.id} references unextracted symbol {symbol}")
                )

        java_model = bundle.java_model
        if not java_model:
            findings.append(ReviewFinding("fail", "java", "java_model specification is missing"))
        if "equations" in java_model and "variables" not in java_model:
            findings.append(ReviewFinding("fail", "r1", "java model must separate equations and constitutive variables"))
    finally:
        document.close()

    failures = [item for item in findings if item.severity == "fail"]
    return ExtractionReview(
        decision="accepted" if not failures else "rejected",
        findings=tuple(findings),
        passed=not failures,
    )
