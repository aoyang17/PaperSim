"""Dimensional validation and unit conversion for extracted quantities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .contracts import ContractError


def _ureg():
    try:
        import pint
    except ImportError as exc:
        raise ContractError("unit validation requires the optional 'extraction' dependencies") from exc
    return pint.UnitRegistry()


@dataclass(frozen=True)
class UnitCheck:
    input_unit: str
    canonical_unit: str
    dimensionalities: str
    factor: float
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_unit": self.input_unit,
            "canonical_unit": self.canonical_unit,
            "dimensionalities": self.dimensionalities,
            "factor": self.factor,
            "passed": self.passed,
        }


class UnitValidator:
    def __init__(self) -> None:
        self.ureg = _ureg()

    def parse(self, unit: str) -> UnitCheck:
        if unit is None or not str(unit).strip():
            return UnitCheck(str(unit or ""), "", "", 0.0, False)
        try:
            quantity = 1.0 * self.ureg.parse_units(str(unit))
        except Exception:
            return UnitCheck(str(unit), "", "", 0.0, False)
        return UnitCheck(
            input_unit=str(unit),
            canonical_unit=f"{quantity.units:~}",
            dimensionalities=str(quantity.dimensionality),
            factor=float(quantity.to_base_units().magnitude),
            passed=True,
        )

    def compatible(self, left: str, right: str) -> bool:
        left_value = self.parse(left)
        right_value = self.parse(right)
        if not left_value.passed or not right_value.passed:
            return False
        try:
            lq = 1.0 * self.ureg.parse_units(left)
            rq = 1.0 * self.ureg.parse_units(right)
            lq.to(rq.units)
            return True
        except Exception:
            return False

    def convert(self, value: float, source: str, target: str) -> float:
        try:
            quantity = float(value) * self.ureg.parse_units(source)
            converted = quantity.to(self.ureg.parse_units(target))
        except Exception as exc:
            raise ContractError(f"cannot convert {value} from {source!r} to {target!r}: {exc}") from exc
        return float(converted.magnitude)

    def validate_parameter(self, value: float | None, units: str, *, expression: str | None = None) -> dict[str, Any]:
        parsed = self.parse(units)
        finite = True
        if value is not None:
            finite = math.isfinite(float(value))
        passed = parsed.passed and finite
        if expression is not None and not expression.strip():
            passed = False
        return {
            "passed": passed,
            "value": value,
            "expression": expression,
            "unit_check": parsed.as_dict(),
            "reason": "" if passed else "invalid or missing unit/value",
        }

    def validate_equation(self, terms: list[str], expected_units: str) -> dict[str, Any]:
        expected = self.parse(expected_units)
        checks = [self.parse(term) for term in terms]
        compatible = [
            self.compatible(term, expected_units) for term in terms
        ] if expected.passed else [False for _ in terms]
        passed = expected.passed and bool(terms) and all(compatible)
        return {
            "passed": passed,
            "expected": expected.as_dict(),
            "terms": [item.as_dict() for item in checks],
            "term_compatibility": compatible,
            "reason": "" if passed else "equation terms are not dimensionally compatible",
        }
