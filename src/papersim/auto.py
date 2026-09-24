"""Deterministic, LLM-free template selection for automatic paper extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ContractError
from .documents import PdfDocument, normalize_text


@dataclass(frozen=True)
class AutoProfileSelection:
    profile_path: Path
    template_name: str
    score: float
    matched_keywords: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_path": str(self.profile_path),
            "template_name": self.template_name,
            "score": self.score,
            "matched_keywords": list(self.matched_keywords),
        }


TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "name": "chen2014_phase_field_elastoplastic",
        "profile": "profiles/chen2014_elastoplastic.json",
        "keywords": (
            "phase-field model coupled with large elasto-plastic deformation",
            "lithiated silicon electrodes",
            "crystalline silicon",
            "cahn-hilliard",
            "first piola-kirchhoff",
        ),
        "minimum_score": 0.6,
    },
    {
        "name": "huang2013_lithiation_stress",
        "profile": "profiles/huang2013_lithiation.json",
        "keywords": (
            "stress generation during lithiation",
            "high-capacity electrode particles",
            "spherical particle",
            "elastic-plastic",
            "j2-flow",
        ),
        "minimum_score": 0.6,
    },
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_auto_profile(pdf_path: str | Path) -> AutoProfileSelection:
    document = PdfDocument(pdf_path)
    try:
        preview = " ".join(normalize_text(document.page_text(page)).lower() for page in range(1, min(document.page_count, 3) + 1))
    finally:
        document.close()

    ranked: list[AutoProfileSelection] = []
    for template in TEMPLATES:
        keywords = tuple(str(item) for item in template["keywords"])
        matched = tuple(item for item in keywords if item.lower() in preview)
        score = len(matched) / max(len(keywords), 1)
        profile = _repository_root() / str(template["profile"])
        if not profile.is_file():
            raise ContractError(f"auto profile template is missing: {profile}")
        if score >= float(template["minimum_score"]):
            ranked.append(
                AutoProfileSelection(
                    profile_path=profile,
                    template_name=str(template["name"]),
                    score=score,
                    matched_keywords=matched,
                )
            )
    if not ranked:
        raise ContractError(
            "PaperSim auto mode is deterministic and requires a registered model template; "
            "no template matched this PDF. Add a profile template before generating Java."
        )
    return max(ranked, key=lambda item: item.score)
