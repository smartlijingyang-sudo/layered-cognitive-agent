from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.contracts.observability.evidence import (
    Classification,
    EvidenceIntegrityError,
    EvidenceRef,
)
from lca.plugins.transport.webserver.handlers.runs.observability.evidence import (
    EvidencePayloadDecodeError,
    InvalidEvidenceDigestError,
    RunEvidenceNotFoundError,
    RunEvidenceReader,
    normalize_evidence_digest,
)


class _EvidenceStore:
    def __init__(self, payload: bytes | Exception) -> None:
        self._payload = payload
        self.requests: list[tuple[EvidenceRef, str, Classification]] = []

    def get(
        self,
        ref: EvidenceRef,
        *,
        requester: str,
        audience: Classification,
    ) -> bytes:
        self.requests.append((ref, requester, audience))
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _reference() -> EvidenceRef:
    return EvidenceRef(
        digest="a" * 64,
        media_type="application/json",
        byte_length=16,
        locator="evidence/test.json",
    )


def _write_journal(path: Path, reference: EvidenceRef) -> None:
    record = {
        "schema": "lca.journal/2",
        "data": {"state_ref": reference.to_dict()},
    }
    path.write_text(f"not-json\n{json.dumps(record)}\n", encoding="utf-8")


def test_reader_uses_journal_authorized_reference_and_governed_store(tmp_path: Path) -> None:
    reference = _reference()
    journal = tmp_path / "run.jsonl"
    _write_journal(journal, reference)
    store = _EvidenceStore(b'{"answer":"verified"}')

    evidence = RunEvidenceReader(store).read_json(
        run_id="run-1",
        requested_ref=f"sha256:{reference.digest}",
        journal_path=journal,
        requester="gateway:run-1",
    )

    assert evidence.run_id == "run-1"
    assert evidence.reference == reference
    assert evidence.byte_length == len(b'{"answer":"verified"}')
    assert evidence.data == {"answer": "verified"}
    assert store.requests == [(reference, "gateway:run-1", Classification.INTERNAL)]


@pytest.mark.parametrize(
    "requested_ref",
    ["", "sha256:not-a-digest", "g" * 64, "a" * 63],
)
def test_normalize_digest_rejects_non_sha256_values(requested_ref: str) -> None:
    with pytest.raises(InvalidEvidenceDigestError):
        normalize_evidence_digest(requested_ref)


def test_reader_rejects_missing_journal_without_querying_store(tmp_path: Path) -> None:
    store = _EvidenceStore(b"{}")

    with pytest.raises(RunEvidenceNotFoundError, match="run journal"):
        RunEvidenceReader(store).read_json(
            run_id="run-missing",
            requested_ref="a" * 64,
            journal_path=tmp_path / "missing.jsonl",
            requester="gateway:run-missing",
        )

    assert store.requests == []


def test_reader_rejects_digest_not_authorized_by_the_run_journal(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    _write_journal(journal, _reference())
    store = _EvidenceStore(b"{}")

    with pytest.raises(RunEvidenceNotFoundError, match="reference"):
        RunEvidenceReader(store).read_json(
            run_id="run-1",
            requested_ref="b" * 64,
            journal_path=journal,
            requester="gateway:run-1",
        )

    assert store.requests == []


def test_reader_preserves_integrity_failures_from_the_governed_store(tmp_path: Path) -> None:
    reference = _reference()
    journal = tmp_path / "run.jsonl"
    _write_journal(journal, reference)
    store = _EvidenceStore(EvidenceIntegrityError("digest mismatch"))

    with pytest.raises(EvidenceIntegrityError, match="digest mismatch"):
        RunEvidenceReader(store).read_json(
            run_id="run-1",
            requested_ref=reference.digest,
            journal_path=journal,
            requester="gateway:run-1",
        )


def test_reader_rejects_verified_payload_that_is_not_json(tmp_path: Path) -> None:
    reference = _reference()
    journal = tmp_path / "run.jsonl"
    _write_journal(journal, reference)

    with pytest.raises(EvidencePayloadDecodeError, match="JSON-decodable"):
        RunEvidenceReader(_EvidenceStore(b"not json")).read_json(
            run_id="run-1",
            requested_ref=reference.digest,
            journal_path=journal,
            requester="gateway:run-1",
        )
