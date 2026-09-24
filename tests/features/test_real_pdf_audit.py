from __future__ import annotations

import os
from pathlib import Path

import pytest

from papersim.case_audit import PdfEvidenceVerifier, audit_profile
from papersim.case_contracts import ProfileModel
from papersim.documents import PdfDocument


@pytest.mark.pdf
def test_real_kobayashi_pdf_evidence_audit(repo_root: Path):
    configured = os.environ.get("PAPERSIM_KOBAYASHI_PDF")
    if not configured:
        pytest.skip("set PAPERSIM_KOBAYASHI_PDF to run the real PDF audit")
    pdf = Path(configured)
    if not pdf.is_file():
        pytest.skip(f"Kobayashi PDF fixture is unavailable: {pdf}")
    profile = ProfileModel.model_validate_json((repo_root / "profiles" / "kobayashi1993_dendrite.json").read_text())
    document = PdfDocument(pdf)
    try:
        audit, evidence = audit_profile(
            case_id=profile.case_id,
            iteration=1,
            paper_sha256=document.sha256,
            profile_sha256="a" * 64,
            profile=profile,
            verifier=PdfEvidenceVerifier(document),
        )
    finally:
        document.close()
    assert len(evidence) == len(profile.evidence)
    assert all(item.passed for item in audit.checks), [item.model_dump() for item in audit.checks if not item.passed]
