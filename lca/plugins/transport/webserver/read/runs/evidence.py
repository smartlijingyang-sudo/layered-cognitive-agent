"""Read-side evidence, failure diagnostics, and user-facing error formatting.

Consolidates:
- Evidence lookups and verification through the Journal truth source
- Failure projection and exception record loading from run traces
- Sanitization and formatting of internal failures into user-facing errors
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.observability.evidence.evidence import (
    Classification,
    EvidenceRef,
    EvidenceStore,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    record_normalize,
)
from lca.infrastructure.observability.spine.sinks.naming import (
    exceptions_filename_for_run,
    spine_filename_for_run,
)

# --- Error Presentation & Sanitization ---

_SANITIZE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"DataInspectionFailed|content.?filter|inappropriate.?content|content.?safety",
            re.IGNORECASE,
        ),
        "模型输出触发了内容安全策略，请调整输入后重试",
    ),
    (
        re.compile(r"<\d{3}>|APIError|APIConnectionError|APITimeoutError|InternalError"),
        "模型服务暂时不可用，请稍后重试",
    ),
    (
        re.compile(r"timeout|connection|network", re.IGNORECASE),
        "网络连接异常，请检查网络后重试",
    ),
)

_INTERNAL_EXCEPTION_PREFIX = re.compile(r"^_*[A-Z][A-Za-z0-9._]*Error:\s*")


def sanitize_error(error: str) -> str:
    """Map known provider failures to safe, actionable messages."""
    if not error:
        return error
    for pattern, replacement in _SANITIZE_RULES:
        if pattern.search(error):
            return replacement
    return error


def format_user_error(error: str, *, run_id: str, trace_id: str) -> str:
    """Return the user-facing failure text."""
    del run_id, trace_id
    return _strip_internal_exception_prefix(sanitize_error(error))


def _strip_internal_exception_prefix(error: str) -> str:
    """Remove one leading Python exception type from an error message."""
    return _INTERNAL_EXCEPTION_PREFIX.sub("", error or "", count=1)


# --- Failure Projection ---

_DEFAULT_TRACES_ROOT = Path("traces") / "runs"


def _run_dir(run_id: str, *, traces_root: Path = _DEFAULT_TRACES_ROOT) -> Path:
    return traces_root / run_id


def load_exception_records(
    run_id: str,
    *,
    traces_root: Path = _DEFAULT_TRACES_ROOT,
) -> list[dict[str, Any]]:
    """Load ``exception.caught`` payloads from ``*.exceptions.jsonl`` or spine fallback."""
    run_path = _run_dir(run_id, traces_root=traces_root)
    exceptions_path = run_path / exceptions_filename_for_run(run_id)
    records: list[dict[str, Any]] = []
    if exceptions_path.is_file():
        for line in exceptions_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else row
            if isinstance(payload, dict):
                records.append(payload)
        return records

    spine_path = run_path / spine_filename_for_run(run_id)
    if not spine_path.is_file():
        return []
    for line in spine_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("execution_point") != "exception.caught":
            continue
        payload = row.get("payload")
        if isinstance(payload, dict):
            records.append(payload)
    return records


def failure_summary_for_run(
    run_id: str,
    *,
    user_error: str = "",
    traces_root: Path = _DEFAULT_TRACES_ROOT,
) -> dict[str, Any]:
    """Operator-facing failure DTO: sanitized user message + exception index."""
    records = load_exception_records(run_id, traces_root=traces_root)
    latest = records[-1] if records else {}
    return {
        "run_id": run_id,
        "user_message": user_error,
        "exception_class": latest.get("exception_class") or latest.get("exc_type") or "",
        "exception_message": latest.get("exception_message") or latest.get("message") or "",
        "err_kind": latest.get("err_kind") or "",
        "boundary": latest.get("boundary") or "",
        "exception_count": len(records),
        "has_traceback": bool(latest.get("traceback_text")),
    }


# --- Evidence Resolution ---


class RunEvidenceQueryError(ValueError):
    """Base error for a lookup that cannot yield a JSON evidence payload."""


class InvalidEvidenceDigestError(RunEvidenceQueryError):
    """The caller supplied a digest outside the accepted SHA-256 vocabulary."""


class RunEvidenceNotFoundError(RunEvidenceQueryError):
    """The requested run or digest has no durable evidence reference."""


class EvidencePayloadDecodeError(RunEvidenceQueryError):
    """A verified evidence payload is not valid UTF-8 JSON."""

    def __init__(self, byte_length: int) -> None:
        super().__init__("evidence payload is not JSON-decodable")
        self.byte_length = byte_length


@dataclass(frozen=True, slots=True)
class RunEvidence:
    """A verified JSON payload and the durable reference that authorized it."""

    run_id: str
    requested_ref: str
    reference: EvidenceRef
    byte_length: int
    data: object


class RunEvidenceReader:
    """Resolve a run-scoped evidence digest through the Journal truth source."""

    def __init__(self, evidence_store: EvidenceStore) -> None:
        self._evidence_store = evidence_store

    def read_json(
        self,
        *,
        run_id: str,
        requested_ref: str,
        journal_path: Path | None,
        requester: str,
        audience: Classification = Classification.INTERNAL,
    ) -> RunEvidence:
        """Read one Journal-authorized evidence payload and decode its JSON."""
        digest = normalize_evidence_digest(requested_ref)
        reference = self._find_reference(journal_path, digest)
        payload = self._evidence_store.get(reference, requester=requester, audience=audience)
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidencePayloadDecodeError(len(payload)) from exc
        return RunEvidence(
            run_id=run_id,
            requested_ref=requested_ref,
            reference=reference,
            byte_length=len(payload),
            data=data,
        )

    @staticmethod
    def _find_reference(journal_path: Path | None, digest: str) -> EvidenceRef:
        if journal_path is None or not journal_path.is_file():
            raise RunEvidenceNotFoundError("run journal was not found")
        for record in load_journal_records(journal_path, strict=False):
            normalized = record_normalize(record)
            if normalized.get("schema") != "lca.journal/2":
                continue
            data = normalized.get("data", {})
            ref_raw = data.get("arguments_ref") or data.get("output_ref") or data.get("state_ref")
            if not isinstance(ref_raw, dict):
                continue
            try:
                reference = EvidenceRef.from_dict(ref_raw)
            except (ValueError, TypeError, KeyError):
                continue
            if reference.digest.lower() == digest:
                return reference
        raise RunEvidenceNotFoundError("evidence reference was not found in the run journal")


def normalize_evidence_digest(requested_ref: str) -> str:
    """Accept a SHA-256 digest with or without its explicit algorithm prefix."""
    raw = requested_ref.strip()
    digest = raw[len("sha256:") :] if raw.startswith("sha256:") else raw
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
        raise InvalidEvidenceDigestError("evidence reference must be a SHA-256 digest")
    return digest.lower()


__all__ = [
    "EvidencePayloadDecodeError",
    "InvalidEvidenceDigestError",
    "RunEvidence",
    "RunEvidenceNotFoundError",
    "RunEvidenceQueryError",
    "RunEvidenceReader",
    "failure_summary_for_run",
    "format_user_error",
    "load_exception_records",
    "normalize_evidence_digest",
    "sanitize_error",
]
