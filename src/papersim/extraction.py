"""Paper equation/parameter extraction with source-addressable evidence."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .contracts import ContractError
from .documents import EvidenceRef, EquationRegion, PdfDocument, normalize_text
from .units import UnitValidator


CLASSIFICATIONS = {"control", "constitutive", "auxiliary", "boundary", "initial"}


@dataclass(frozen=True)
class EquationRecord:
    id: str
    number: int
    latex: str
    raw_text: str
    classification: str
    dependent_variables: tuple[str, ...]
    referenced_symbols: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    confidence: str = "high"

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = [item.as_dict() for item in self.evidence]
        return value


@dataclass(frozen=True)
class ParameterRecord:
    source_symbol: str
    comsol_name: str
    value: float | int | None
    expression: str | None
    units: str
    meaning: str
    status: str
    evidence: tuple[EvidenceRef, ...]
    unit_check: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = [item.as_dict() for item in self.evidence]
        value["unit_check"] = dict(self.unit_check)
        return value


@dataclass(frozen=True)
class RelationRecord:
    id: str
    source_symbols: tuple[str, ...]
    target_symbol: str
    relation: str
    relation_type: str
    evidence: tuple[EvidenceRef, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = [item.as_dict() for item in self.evidence]
        return value


@dataclass(frozen=True)
class ExtractionBundle:
    schema_version: str
    source_path: str
    source_sha256: str
    equations: tuple[EquationRecord, ...]
    parameters: tuple[ParameterRecord, ...]
    relations: tuple[RelationRecord, ...]
    java_model: Mapping[str, Any]
    unit_equation_checks: Mapping[str, Any]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "equations": [item.as_dict() for item in self.equations],
            "parameters": [item.as_dict() for item in self.parameters],
            "relations": [item.as_dict() for item in self.relations],
            "java_model": dict(self.java_model),
            "unit_equation_checks": dict(self.unit_equation_checks),
            "warnings": list(self.warnings),
        }


def load_extraction_profile(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ContractError(f"extraction profile does not exist: {source}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid extraction profile: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("extraction profile must be a JSON object")
    return value


def _region_for_number(regions: list[EquationRegion], page: int | None, number: int) -> EquationRegion:
    candidates = [item for item in regions if item.number == number and (page is None or item.page == page)]
    if not candidates:
        raise ContractError(f"equation ({number}) was not detected in the PDF")
    return max(candidates, key=lambda item: len(item.raw_text))


def _line_bbox(document: PdfDocument, page: int, quote: str) -> tuple[float, float, float, float]:
    normalized_quote = normalize_text(quote)
    lines = document.lines(page)
    for item in lines:
        normalized_line = normalize_text(item.text)
        if normalized_quote in normalized_line or normalized_line in normalized_quote:
            return item.bbox
    raise ContractError(f"source quote was not found on page {page}: {quote!r}")


def _evidence(
    document: PdfDocument,
    *,
    label: str,
    page: int,
    bbox: tuple[float, float, float, float],
    quote: str,
) -> EvidenceRef:
    return EvidenceRef(label, document.sha256, page, bbox, quote)


def _extract_equation_records(
    document: PdfDocument,
    profile: Mapping[str, Any],
    detected: list[EquationRegion],
) -> tuple[EquationRecord, ...]:
    records: list[EquationRecord] = []
    for item in profile.get("equations", []):
        if not isinstance(item, Mapping):
            raise ContractError("profile equations must be objects")
        number = int(item["number"])
        region = _region_for_number(detected, item.get("page"), number)
        classification = str(item.get("classification") or "")
        if classification not in CLASSIFICATIONS:
            raise ContractError(f"equation ({number}) has invalid classification: {classification!r}")
        latex = str(item.get("latex") or "").strip()
        if not latex:
            raise ContractError(f"equation ({number}) is missing normalized LaTeX")
        evidence = _evidence(
            document,
            label=f"eq:{number}",
            page=region.page,
            bbox=region.bbox,
            quote=region.raw_text,
        )
        records.append(
            EquationRecord(
                id=str(item.get("id") or f"eq-{number}"),
                number=number,
                latex=latex,
                raw_text=region.raw_text,
                classification=classification,
                dependent_variables=tuple(str(value) for value in item.get("dependent_variables", [])),
                referenced_symbols=tuple(str(value) for value in item.get("referenced_symbols", [])),
                evidence=(evidence,),
                confidence=str(item.get("confidence") or "high"),
            )
        )
    return tuple(records)


def _extract_parameter_records(
    document: PdfDocument,
    profile: Mapping[str, Any],
    validator: UnitValidator,
) -> tuple[ParameterRecord, ...]:
    records: list[ParameterRecord] = []
    for item in profile.get("parameters", []):
        if not isinstance(item, Mapping):
            raise ContractError("profile parameters must be objects")
        page = int(item["page"])
        quote = str(item.get("quote") or "")
        bbox = _line_bbox(document, page, quote)
        value = item.get("value")
        expression = item.get("expression")
        units = str(item.get("units") or "")
        unit_check = validator.validate_parameter(
            float(value) if value is not None else None,
            units,
            expression=str(expression) if expression is not None else None,
        )
        if not unit_check["passed"]:
            raise ContractError(
                f"parameter {item.get('source_symbol')} has invalid unit/value: {unit_check['reason']}"
            )
        records.append(
            ParameterRecord(
                source_symbol=str(item["source_symbol"]),
                comsol_name=str(item["comsol_name"]),
                value=value,
                expression=str(expression) if expression is not None else None,
                units=units,
                meaning=str(item["meaning"]),
                status=str(item.get("status") or "reported"),
                evidence=(_evidence(document, label=f"param:{item['comsol_name']}", page=page, bbox=bbox, quote=quote),),
                unit_check=unit_check,
            )
        )
    return tuple(records)


def _extract_relation_records(
    document: PdfDocument,
    profile: Mapping[str, Any],
) -> tuple[RelationRecord, ...]:
    records: list[RelationRecord] = []
    for item in profile.get("relations", []):
        if not isinstance(item, Mapping):
            raise ContractError("profile relations must be objects")
        page = int(item["page"])
        quote = str(item.get("quote") or "")
        bbox = _line_bbox(document, page, quote)
        records.append(
            RelationRecord(
                id=str(item["id"]),
                source_symbols=tuple(str(value) for value in item.get("source_symbols", [])),
                target_symbol=str(item["target_symbol"]),
                relation=str(item["relation"]),
                relation_type=str(item["relation_type"]),
                evidence=(_evidence(document, label=f"relation:{item['id']}", page=page, bbox=bbox, quote=quote),),
            )
        )
    return tuple(records)


def _scan_numeric_assignments(document: PdfDocument) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<symbol>[A-Za-z][A-Za-z0-9_]{0,12})\s*=\s*(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    )
    for page in range(1, document.page_count + 1):
        for match in pattern.finditer(normalize_text(document.page_text(page))):
            candidates.append(
                {
                    "symbol": match.group("symbol"),
                    "value": float(match.group("value")),
                    "page": page,
                    "quote": match.group(0),
                    "status": "candidate_requires_review",
                }
            )
    return candidates


def extract_paper(
    pdf_path: str | Path,
    profile_path: str | Path,
    *,
    extraction_dir: str | Path | None = None,
) -> ExtractionBundle:
    profile = load_extraction_profile(profile_path)
    document = PdfDocument(pdf_path)
    try:
        detected = document.render_equation_regions(
            Path(extraction_dir) / "formula_regions" if extraction_dir else Path(pdf_path).expanduser().resolve().parent / "formula_regions"
        ) if extraction_dir else document.equation_regions()
        equations = _extract_equation_records(document, profile, detected)
        parameters = _extract_parameter_records(document, profile, UnitValidator())
        relations = _extract_relation_records(document, profile)
        unit_checks = {
            item["id"]: UnitValidator().validate_equation(
                [str(value) for value in item.get("term_units", [])],
                str(item["expected_units"]),
            )
            for item in profile.get("unit_equations", [])
            if isinstance(item, Mapping)
        }
        warnings: list[str] = []
        if len(equations) != len(detected):
            warnings.append(f"normalized {len(equations)} equations for {len(detected)} detected numbered regions")
        candidates = _scan_numeric_assignments(document)
        warnings.append(f"{len(candidates)} automatic numeric assignment candidates require review")
        return ExtractionBundle(
            schema_version="papersim.extraction.v1",
            source_path=str(document.path),
            source_sha256=document.sha256,
            equations=equations,
            parameters=parameters,
            relations=relations,
            java_model=dict(profile.get("java_model") or {}),
            unit_equation_checks=unit_checks,
            warnings=tuple(warnings),
        )
    finally:
        document.close()


def write_extraction_bundle(bundle: ExtractionBundle, path: str | Path) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
