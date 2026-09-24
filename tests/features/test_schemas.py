from __future__ import annotations

from papersim.schemas import export_schemas


def test_schema_export(tmp_path):
    written = export_schemas(tmp_path / "schemas")
    assert set(written) == {"case_manifest", "profile", "ir", "audit"}
    for path in written.values():
        assert path.endswith(".schema.json")
        assert "properties" in open(path, encoding="utf-8").read()
