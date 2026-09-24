from __future__ import annotations

import pytest

from papersim.case_audit import SyntheticEvidenceVerifier, approve, audit_hash, audit_profile, ensure_approved
from papersim.case_contracts import AuditRecord, CheckStatus, IR, IterationState
from papersim.contracts import ContractError


def _audit(profile, paper_hash="a" * 64):
    return audit_profile(
        case_id=profile.case_id,
        iteration=1,
        paper_sha256=paper_hash,
        profile_sha256="b" * 64,
        profile=profile,
        verifier=SyntheticEvidenceVerifier(paper_hash),
    )


def test_profile_audit_is_deterministic_and_passes(kobayashi_profile):
    audit, evidence = _audit(kobayashi_profile)
    assert len(evidence) == len(kobayashi_profile.evidence)
    assert all(item.status == CheckStatus.PASS for item in audit.checks)
    assert audit_hash(audit) == audit_hash(audit)


def test_approval_binds_hashes_and_can_be_checked(kobayashi_profile):
    audit, evidence = _audit(kobayashi_profile)
    ir = IR(
        case_id=kobayashi_profile.case_id,
        iteration=1,
        paper_filename="kobayashi1993_dendrite_paper.pdf",
        paper_sha256="a" * 64,
        profile_sha256="b" * 64,
        scope=kobayashi_profile.scope,
        profile=kobayashi_profile,
        evidence=evidence,
    ).with_hash()
    audit = audit.model_copy(update={"ir_sha256": ir.ir_hash})
    approved = approve(audit, approved_by="test-only:reviewer", reason="synthetic fixture", test_only=True)
    ensure_approved(approved, ir)
    changed = ir.model_copy(update={"scope": "changed scope"}).with_hash()
    with pytest.raises(ContractError):
        ensure_approved(approved, changed)


def test_invalid_unit_blocks_audit(kobayashi_profile):
    payload = kobayashi_profile.model_dump(mode="json")
    payload["parameters"][0]["units"] = "not-a-unit"
    # The validator intentionally accepts strings, while the audit must reject
    # semantically invalid units.
    from papersim.case_contracts import ProfileModel

    profile = ProfileModel.model_validate(payload)
    audit, _ = _audit(profile)
    failed = [item.check_id for item in audit.checks if not item.passed]
    assert "units" in failed
