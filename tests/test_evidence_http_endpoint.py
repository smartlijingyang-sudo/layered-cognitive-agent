"""Evidence HTTP endpoint tests —— ADR-0065 §四 L5 / PR-10。

drives the production ``gateway.app.create_app()`` and exercises
``GET /runs/{run_id}/evidence/{ref}`` end-to-end via Starlette's
``TestClient`` (real HTTP request path).

Verifies:
- happy path: ``state_ref`` → evidence bytes round-trip to original dict
- 200 + correct JSON body shape ``{run_id, ref, byte_length, data}``
- 404 when ``bound_observability`` not bound (no evidence seam)
- 404 when ``ref`` doesn't exist
- 400 on invalid ref format
- 500 on integrity violation (forced via tampered store)
- 403 on audience rejection (forced via policy override)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from starlette.testclient import TestClient

from lca.contracts.observability.evidence import (
    Classification,
    EvidenceIntegrityError,
    EvidenceRef,
    EvidenceStore,
    RetentionClass,
)
from lca.infrastructure.observability import (
    BoundObservability,
    bind_backends,
    run_scope,
)
from lca.infrastructure.observability.evidence.policy import (
    DefaultEvidencePolicy,
)
from lca.infrastructure.observability.evidence.store import (
    FilesystemEvidenceStore,
)
from lca.infrastructure.observability.journal.jsonl_projector import (
    JsonlJournalProjector,
)
from lca.infrastructure.observability.journal_backend import MemoryJournal
from lca.infrastructure.observability.policy import AttributePolicy


# A minimal evidence store wrapper that lets tests inject specific failure modes.
class _ScriptableEvidenceStore(EvidenceStore):
    """delegate-to-fs store with hooks for failure injection in tests."""

    def __init__(self, fs: FilesystemEvidenceStore) -> None:
        self._fs = fs
        self.raise_missing: bool = False
        self.raise_audience: bool = False
        self.raise_integrity: bool = False

    def prepare(
        self,
        payload,
        *,
        classification,
        retention,
        media_type="application/octet-stream",
        prepared_by="",
    ):
        return self._fs.prepare(
            payload,
            classification=classification,
            retention=retention,
            media_type=media_type,
            prepared_by=prepared_by,
        )

    def get(self, ref, *, requester, audience):
        if self.raise_missing:
            raise KeyError(f"ref not found: {ref.digest[:16]}")
        if self.raise_audience:
            raise PermissionError(f"audience {audience} rejected for {ref.digest[:16]}")
        if self.raise_integrity:
            raise EvidenceIntegrityError(f"sha256 mismatch for {ref.digest[:16]}")
        return self._fs.get(ref, requester=requester, audience=audience)

    def contains(self, ref):
        return self._fs.contains(ref)

    def sweep_orphan(self, ledger_index):
        return self._fs.sweep_orphan(ledger_index)


def _make_app_with_bound(
    bound: BoundObservability | None,
    jsonl_path: Path | None = None,
):
    """Build a minimal Starlette app with /runs/{id}/evidence/{ref} registered.

    Avoids the full gateway boot path (which depends on dsh runtime + plugins
    that aren't in test scope); the route handler reads ``app.state.bound_observability``
    so we only need to wire that one piece of state.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    from gateway.runs.query_endpoints import get_run_evidence

    application = Starlette(
        routes=[
            Route(
                "/runs/{run_id}/evidence/{ref:path}",
                get_run_evidence,
                methods=["GET"],
            ),
        ]
    )
    application.state.bound_observability = bound

    class _StubRunPort:
        def journal_path(self, _run_id: str) -> Path | None:
            return jsonl_path

    application.state.run_port = _StubRunPort()
    return application


def _drive_run_with_evidence(jsonl_path: Path, ev_root: Path) -> tuple[str, dict, dict]:
    """drive a ToolStarted through public record() path; capture state_ref."""

    policy = DefaultEvidencePolicy(inline_threshold_bytes=64)
    store = FilesystemEvidenceStore(ev_root)
    journal = MemoryJournal(policy=AttributePolicy()).with_projection(
        JsonlJournalProjector(jsonl_path)
    )
    bound = BoundObservability(
        evidence_store=store,
        evidence_policy=policy,
        journal=journal,
    )

    from lca.contracts.models.observability.journal import (
        RunScope,
        ToolStarted,
    )
    from lca.layer1_cognitive.body.tool_journal_emit import (
        emit_tool_started,
    )

    class _MockTool:
        name = "execute_code"

    big = {"code": "x" * 200, "language": "python", "description": "big state"}
    scope = RunScope(trace_id="t", run_id="run_e2e", agent_role="researcher")
    with bind_backends(bound), run_scope(scope):
        # ADR-0101 PR-2:emit_tool_started takes args (dict), returns arguments_ref
        ref = emit_tool_started(
            _MockTool(),
            big,
            invocation_id="inv1",
            evidence_store=store,
            evidence_policy=policy,
        )

    # Find the ToolStarted and capture its arguments_ref
    from lca.infrastructure.observability.journal.journal_io import read_journal

    events = read_journal(jsonl_path)
    ts = next(e for e in events if isinstance(e.event, ToolStarted))
    assert ref is not None
    assert ts.event.arguments_ref is not None
    return (
        "run_e2e",
        big,
        {
            "digest": ts.event.arguments_ref.digest,
            "ref": ts.event.arguments_ref,
        },
    )


def test_evidence_endpoint_happy_path() -> None:
    """200 + correct JSON body shape; round-trip equals original plugin_state."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, original, ref_info = _drive_run_with_evidence(jsonl, ev)
        app = _make_app_with_bound(
            BoundObservability(
                evidence_store=FilesystemEvidenceStore(ev),
                evidence_policy=DefaultEvidencePolicy(),
            ),
            jsonl_path=jsonl,
        )
        client = TestClient(app)
        r = client.get(f"/runs/{run_id}/evidence/{ref_info['digest']}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["run_id"] == run_id
        assert body["ref"] == ref_info["digest"]
        assert body["byte_length"] > 0
        assert body["data"] == original


def test_evidence_endpoint_accepts_sha256_prefix() -> None:
    """ref may be passed with ``sha256:`` prefix (canonical EvidenceRef format)."""
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, original, ref_info = _drive_run_with_evidence(jsonl, ev)
        app = _make_app_with_bound(
            BoundObservability(
                evidence_store=FilesystemEvidenceStore(ev),
                evidence_policy=DefaultEvidencePolicy(),
            ),
            jsonl_path=jsonl,
        )
        client = TestClient(app)
        r = client.get(f"/runs/{run_id}/evidence/sha256:{ref_info['digest']}")
        assert r.status_code == 200
        assert r.json()["data"] == original


def test_evidence_endpoint_missing_store_404() -> None:
    """no bound_observability on app.state → 404."""
    from starlette.applications import Starlette
    from starlette.routing import Route

    from gateway.runs.query_endpoints import get_run_evidence

    app = Starlette(
        routes=[
            Route("/runs/{run_id}/evidence/{ref:path}", get_run_evidence, methods=["GET"]),
        ]
    )
    app.state.bound_observability = None
    client = TestClient(app)
    r = client.get("/runs/abc/evidence/abc")
    assert r.status_code == 404
    assert r.json()["error"] == "evidence store not configured"


def _write_envelope_with_state_ref(jsonl_path: Path, *, digest: str, byte_length: int) -> None:
    """write a minimal v2 envelope line containing a ToolStarted with state_ref.

    Used by negative tests that need the journal lookup to succeed so the
    handler reaches the store layer.
    """

    sr = EvidenceRef(
        algorithm="sha256",
        digest=digest,
        media_type="application/json",
        byte_length=byte_length,
        classification=Classification.INTERNAL,
        retention=RetentionClass.RUN_DEFAULT,
        locator="",
    ).to_dict()
    line = {
        "schema": "lca.journal/2",
        "event_id": f"evt_{digest[:24]}",
        "run_id": "abc",
        "run_seq": 1,
        "occurred_at": 1.0,
        "committed_at": 1.0,
        "scope": {
            "trace_id": "t",
            "run_id": "abc",
            "parent_run_id": None,
            "parent_trace_id": None,
            "delegation_id": None,
            "agent_role": "researcher",
            "step": 0,
        },
        "causation": {"parent_event_id": "", "links": []},
        "descriptor": {"type": "ToolStarted", "version": 1, "payload_schema_version": 1},
        "data": {"tool_name": "t", "invocation_id": "i", "state_ref": sr},
        "evidence": [],
    }
    jsonl_path.write_text(json.dumps(line) + "\n", encoding="utf-8")


def test_evidence_endpoint_invalid_ref_400() -> None:
    """ref not sha256 hex (32 chars) → 400."""
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "ev"
        app = _make_app_with_bound(
            BoundObservability(
                evidence_store=FilesystemEvidenceStore(ev),
                evidence_policy=DefaultEvidencePolicy(),
            )
        )
        client = TestClient(app)
        r = client.get("/runs/abc/evidence/garbage_not_hex_!!")
        assert r.status_code == 400
        assert "invalid ref format" in r.json()["error"]


def test_evidence_endpoint_ref_not_found_500() -> None:
    """well-formed but missing-on-disk digest → 500 (L5 integrity failure).

    ADR-0065 §四: missing evidence is a structural integrity failure, not a
    404. The reference in the journal promises a content-addressed payload
    that's not there; returning 500 keeps the failure surface consistent
    with sha256 mismatch and lets the dashboard / alert route the failure
    to the right handler.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "ev"
        jsonl = Path(tmp) / "j.jsonl"
        fake = "0" * 64
        _write_envelope_with_state_ref(jsonl, digest=fake, byte_length=100)
        app = _make_app_with_bound(
            BoundObservability(
                evidence_store=FilesystemEvidenceStore(ev),
                evidence_policy=DefaultEvidencePolicy(),
            ),
            jsonl_path=jsonl,
        )
        client = TestClient(app)
        r = client.get(f"/runs/abc/evidence/{fake}")
        assert r.status_code == 500
        assert "integrity" in r.json()["error"] or "missing" in r.json()["error"]


def test_evidence_endpoint_integrity_violation_500() -> None:
    """forced integrity failure → 500 (L5: 完整性破坏不允许静默)."""
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "ev"
        jsonl = Path(tmp) / "j.jsonl"
        store = _ScriptableEvidenceStore(FilesystemEvidenceStore(ev))
        store.raise_integrity = True
        digest = "a" * 64
        # Need a state_ref in the envelope with the same digest; the
        # store will raise integrity error before reading the file.
        from lca.contracts.observability.evidence import Classification, EvidenceRef, RetentionClass

        sr = EvidenceRef(
            algorithm="sha256",
            digest=digest,
            media_type="application/json",
            byte_length=100,
            classification=Classification.INTERNAL,
            retention=RetentionClass.RUN_DEFAULT,
            locator="",
        ).to_dict()
        line = {
            "schema": "lca.journal/2",
            "event_id": f"evt_{digest[:24]}",
            "run_id": "abc",
            "run_seq": 1,
            "occurred_at": 1.0,
            "committed_at": 1.0,
            "scope": {
                "trace_id": "t",
                "run_id": "abc",
                "parent_run_id": None,
                "parent_trace_id": None,
                "delegation_id": None,
                "agent_role": "researcher",
                "step": 0,
            },
            "causation": {"parent_event_id": "", "links": []},
            "descriptor": {"type": "ToolStarted", "version": 1, "payload_schema_version": 1},
            "data": {"tool_name": "t", "invocation_id": "i", "state_ref": sr},
            "evidence": [],
        }
        jsonl.write_text(json.dumps(line) + "\n", encoding="utf-8")
        app = _make_app_with_bound(
            BoundObservability(evidence_store=store, evidence_policy=DefaultEvidencePolicy()),
            jsonl_path=jsonl,
        )
        client = TestClient(app)
        r = client.get(f"/runs/abc/evidence/{digest}")
        assert r.status_code == 500
        assert "integrity" in r.json()["error"]


def test_evidence_endpoint_audience_rejection_403() -> None:
    """forced audience rejection → 403 (L8: 策略先于持久化与外送)."""
    with tempfile.TemporaryDirectory() as tmp:
        ev = Path(tmp) / "ev"
        jsonl = Path(tmp) / "j.jsonl"
        store = _ScriptableEvidenceStore(FilesystemEvidenceStore(ev))
        store.raise_audience = True
        digest = "a" * 64
        from lca.contracts.observability.evidence import Classification, EvidenceRef, RetentionClass

        sr = EvidenceRef(
            algorithm="sha256",
            digest=digest,
            media_type="application/json",
            byte_length=100,
            classification=Classification.INTERNAL,
            retention=RetentionClass.RUN_DEFAULT,
            locator="",
        ).to_dict()
        line = {
            "schema": "lca.journal/2",
            "event_id": f"evt_{digest[:24]}",
            "run_id": "abc",
            "run_seq": 1,
            "occurred_at": 1.0,
            "committed_at": 1.0,
            "scope": {
                "trace_id": "t",
                "run_id": "abc",
                "parent_run_id": None,
                "parent_trace_id": None,
                "delegation_id": None,
                "agent_role": "researcher",
                "step": 0,
            },
            "causation": {"parent_event_id": "", "links": []},
            "descriptor": {"type": "ToolStarted", "version": 1, "payload_schema_version": 1},
            "data": {"tool_name": "t", "invocation_id": "i", "state_ref": sr},
            "evidence": [],
        }
        jsonl.write_text(json.dumps(line) + "\n", encoding="utf-8")
        app = _make_app_with_bound(
            BoundObservability(evidence_store=store, evidence_policy=DefaultEvidencePolicy()),
            jsonl_path=jsonl,
        )
        client = TestClient(app)
        r = client.get(f"/runs/abc/evidence/{digest}")
        assert r.status_code == 403
        assert "audience" in r.json()["error"]


def test_evidence_endpoint_resolves_full_ref_from_journal() -> None:
    """the journal's state_ref is the source of truth for byte_length /
    classification; the URL parameter is just a digest hint. The endpoint
    reads the full EvidenceRef from the run's journal.jsonl and uses
    that for store.get(); a missing-file then surfaces as 500 integrity
    failure, not 200, even when the journal knows the ref.
    """
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "j.jsonl"
        ev = Path(tmp) / "ev"
        run_id, _original, ref_info = _drive_run_with_evidence(jsonl, ev)

        # Build an app bound to a *different* (empty) evidence store; the
        # endpoint finds the ref in the journal but the store on a
        # different root reports integrity failure.
        other_ev = Path(tmp) / "ev_other"
        app = _make_app_with_bound(
            BoundObservability(
                evidence_store=FilesystemEvidenceStore(other_ev),
                evidence_policy=DefaultEvidencePolicy(),
            ),
            jsonl_path=jsonl,
        )
        client = TestClient(app)
        r = client.get(f"/runs/{run_id}/evidence/{ref_info['digest']}")
        assert r.status_code == 500
