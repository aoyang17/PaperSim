"""JSON Schema export for every canonical PaperSim contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .case_contracts import (
    AuditRecord,
    CaseManifest,
    IR,
    ProfileModel,
)

SCHEMA_MODELS = {
    "case_manifest": CaseManifest,
    "profile": ProfileModel,
    "ir": IR,
    "audit": AuditRecord,
}


def export_schemas(directory: str | Path) -> dict[str, str]:
    target = Path(directory).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for name, model in SCHEMA_MODELS.items():
        schema: dict[str, Any] = model.model_json_schema()
        path = target / f"{name}.schema.json"
        import json

        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[name] = str(path)
    return written
