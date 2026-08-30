"""Read a JSON evidence payload referenced by one durable run journal.

The HTTP carrier supplies only a run identifier, an already-selected journal path,
and a response mapping.  This module owns the durable lookup: normalize a
content digest, rebuild the typed ``EvidenceRef`` recorded in the Journal, then
ask the governed evidence store to re-check authorization and integrity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lca.contracts.observability.evidence import (
    Classification,
    EvidenceRef,
    EvidenceStore,
)
from lca.infrastructure.observability.journal.engine.journal_io import (
    load_journal_records,
    record_normalize,
)


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
    """Resolve a run-scoped evidence digest through the Journal truth source.

    The reader deliberately receives an already-selected journal path.  Run
    ownership remains with the selected run adapter, while this module keeps the
    evidence lookup rules, Journal scan, and governed store access local.
    """

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
            # ADR-0101 PR-2:tool 事件带 arguments_ref / output_ref;
            # state_ref 字段已废弃但保留兼容读。
            data = normalized.get("data", {})
            ref_raw = (
                data.get("arguments_ref") or data.get("output_ref") or data.get("state_ref")
            )
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
    "normalize_evidence_digest",
]
