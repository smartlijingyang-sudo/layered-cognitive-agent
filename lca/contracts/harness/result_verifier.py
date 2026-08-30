"""Result verification contracts for autonomous task completion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from lca.contracts.harness.artifact_manifest import ArtifactManifest
from lca.contracts.models.core.lifecycle import TaskStatus


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    REJECTED = "rejected"


@dataclass(frozen=True)
class VerificationReport:
    status: VerificationStatus
    checks_passed: int
    checks_failed: int
    evidence_refs: tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        if self.checks_passed < 0 or self.checks_failed < 0:
            raise ValueError("verification check counts must be non-negative")
        if self.status is VerificationStatus.VERIFIED and self.checks_failed:
            raise ValueError("verified result cannot contain failed checks")
        if self.status is VerificationStatus.REJECTED and not self.checks_failed:
            raise ValueError("rejected result must contain failed checks")
        if self.status is VerificationStatus.VERIFIED and not self.evidence_refs:
            raise ValueError("verified result requires evidence")


def verify_artifact_manifest(task_id: str, manifest: ArtifactManifest) -> VerificationReport:
    """Verify that a produced manifest is non-empty and owned by the task."""
    if manifest.task_id != task_id:
        return VerificationReport(
            status=VerificationStatus.REJECTED,
            checks_passed=0,
            checks_failed=1,
            message="artifact manifest belongs to another task",
        )
    if not manifest.entries:
        return VerificationReport(
            status=VerificationStatus.REJECTED,
            checks_passed=0,
            checks_failed=1,
            message="artifact manifest is empty",
        )
    return VerificationReport(
        status=VerificationStatus.VERIFIED,
        checks_passed=len(manifest.entries),
        checks_failed=0,
        evidence_refs=tuple(entry.uri for entry in manifest.entries),
        message="artifact manifest verified",
    )


def task_status_from_verification(report: VerificationReport) -> TaskStatus:
    """Project verification into the existing task lifecycle vocabulary."""

    if report.status is VerificationStatus.VERIFIED:
        return TaskStatus.COMPLETED
    if report.status is VerificationStatus.PARTIAL:
        return TaskStatus.PARTIAL
    return TaskStatus.FAILED


@runtime_checkable
class TaskResultVerifier(Protocol):
    def verify(self, task_id: str, result: object) -> VerificationReport: ...


__all__ = [
    "TaskResultVerifier",
    "VerificationReport",
    "VerificationStatus",
    "task_status_from_verification",
    "verify_artifact_manifest",
]
