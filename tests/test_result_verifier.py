from __future__ import annotations

import pytest

from lca.contracts.harness.gate.result_verifier import VerificationReport, VerificationStatus


def test_verified_result_requires_evidence() -> None:
    report = VerificationReport(
        status=VerificationStatus.VERIFIED,
        checks_passed=3,
        checks_failed=0,
        evidence_refs=("journal:42",),
        message="CRM state read back successfully",
    )

    assert report.status is VerificationStatus.VERIFIED
    assert report.evidence_refs == ("journal:42",)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": VerificationStatus.VERIFIED, "checks_passed": 1, "checks_failed": 0},
        {
            "status": VerificationStatus.VERIFIED,
            "checks_passed": 1,
            "checks_failed": 1,
            "evidence_refs": ("e",),
        },
        {"status": VerificationStatus.REJECTED, "checks_passed": 1, "checks_failed": 0},
    ],
)
def test_verification_report_rejects_inconsistent_outcome(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        VerificationReport(**kwargs)


def test_verification_projects_to_existing_task_status() -> None:
    from lca.contracts.harness.gate.result_verifier import task_status_from_verification
    from lca.contracts.models.core.lifecycle import TaskStatus

    assert (
        task_status_from_verification(
            VerificationReport(
                status=VerificationStatus.VERIFIED,
                checks_passed=1,
                checks_failed=0,
                evidence_refs=("e",),
            )
        )
        is TaskStatus.COMPLETED
    )
    assert (
        task_status_from_verification(
            VerificationReport(
                status=VerificationStatus.PARTIAL,
                checks_passed=1,
                checks_failed=1,
            )
        )
        is TaskStatus.PARTIAL
    )


def test_artifact_manifest_verification_requires_task_ownership() -> None:
    from lca.contracts.harness.journal.artifact_manifest import (
        ArtifactEntry,
        ArtifactKind,
        ArtifactManifest,
    )
    from lca.contracts.harness.gate.result_verifier import verify_artifact_manifest

    entry = ArtifactEntry(
        "a1", "report.md", ArtifactKind.REPORT, "sha256:x", "text/markdown", "artifact://a1", 1
    )
    report = verify_artifact_manifest("task-1", ArtifactManifest("task-1", (entry,)))
    assert report.status is VerificationStatus.VERIFIED

    rejected = verify_artifact_manifest("task-2", ArtifactManifest("task-1", (entry,)))
    assert rejected.status is VerificationStatus.REJECTED
