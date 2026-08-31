"""Contract tests for ADR-0121 attachment / FileRef seams.

Each test names one *contract* (not implementation); the asserts call only on
the public Protocol surface so the same suite keeps working when default
providers move.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.models.core.file_ref import (
    FileRef,
    FileRefKind,
    FileRefSource,
)
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.core.sandbox import MountEntry, MountManifest
from lca.contracts.protocols.runtime.attachment import (
    AttachmentPromptRenderer,
    AttachmentResolver,
    AttachmentStager,
    ResolvedAttachment,
)
from lca.contracts.protocols.runtime.attachment_errors import (
    AmbiguousFileRefError,
    AttachmentErrorCode,
    UnresolvedFileRefError,
)
from lca.contracts.protocols.runtime.sandbox_backend import SandboxBackend


def _plane(kind: PlaneKind, root: str) -> PlaneRef:
    return PlaneRef(
        id=f"{kind.name}-x",
        label=kind.name,
        kind=kind,
        root=root,
        outputs_dir=f"{root}/outputs",
    )


def _ref(*, target_key: str = "k", process_path: str = "/p/x") -> FileRef:
    """Build a minimal FileRef for contract tests."""
    return FileRef(
        kind="user_upload",
        target_key=target_key,
        display_path=process_path,
        process_path=process_path,
        file_url=f"file://{process_path}",
        mime_type="text/plain",
        size_bytes=12,
        source="lobehub_upload",
    )


@dataclass
class _FakeResolver:
    label: str = "fake-resolver"

    def resolve(self, attachment_ids: Sequence[str]) -> tuple[ResolvedAttachment, ...]:
        return tuple(
            ResolvedAttachment(ref=_ref(target_key=str(aid), process_path=f"/p/{aid}"))
            for aid in attachment_ids
        )

    def resolve_for_plane(self, ref: FileRef, plane: PlaneRef | None) -> FileRef:
        if plane is None:
            return ref
        prefix = "/mnt/data" if plane.kind is PlaneKind.SANDBOX else "/inbox"
        return FileRef(
            kind=ref.kind,
            target_key=ref.target_key,
            display_path=ref.display_path,
            process_path=f"{prefix}/{ref.display_path.lstrip('/')}",
            file_url=ref.file_url,
            mime_type=ref.mime_type,
            size_bytes=ref.size_bytes,
            source=ref.source,
            attachment_id=ref.attachment_id,
        )


@dataclass
class _FakeStager:
    label: str = "fake-stager"

    def stage_to_machine(
        self,
        *,
        run_id: str,
        refs: Sequence[FileRef],
    ) -> dict[str, str]:
        return {ref.target_key: f"/inbox/{run_id}/{ref.target_key}" for ref in refs}

    def stage_to_sandbox(
        self,
        *,
        sandbox_id: str,
        refs: Sequence[FileRef],
    ) -> tuple[MountEntry, ...]:
        return tuple(
            MountEntry(
                path=f"/mnt/data/{ref.target_key}",
                name=ref.target_key,
                size_bytes=ref.size_bytes,
                attachment_id=ref.attachment_id or "",
            )
            for ref in refs
        )


@dataclass
class _FakeRenderer:
    label: str = "fake-renderer"

    def identity_block(self, refs: Sequence[FileRef]) -> str:
        ids = ",".join(r.target_key for r in refs)
        return f"<files_info count={len(refs)} ids={ids}/>"

    def guest_path_block(self, refs: Sequence[FileRef], plane: PlaneRef | None) -> str:
        paths = ",".join(r.process_path for r in refs)
        return f"<uploaded_files plane={plane.kind.name if plane else 'NONE'} paths={paths}/>"

    def inline_content_block(self, refs: Sequence[FileRef]) -> str:
        return "".join(f"<file id={r.target_key}/>" for r in refs)


@dataclass
class _FakeBackend:
    label: str = "fake-backend"

    def mount_root(self) -> str:
        return "/mnt/data"

    def ensure_mounts(self, manifest: MountManifest, *, timeout_s: int) -> MountManifest:
        return manifest

    def translate_ref(self, ref: FileRef) -> FileRef:
        return ref

    def read_bytes(self, process_path: str) -> bytes | None:
        return b""

    def list_files(self, directory: str) -> Sequence[str]:
        return ()


class TestFileRefContract:
    def test_kind_is_closed(self) -> None:
        # FileRefKind / FileRefSource are Literal aliases — extras are type errors.
        from typing import get_args

        assert set(get_args(FileRefKind)) == {
            "user_upload",
            "sandbox_init",
            "inbox_staged",
            "generated",
            "workspace",
            "external_url",
        }
        assert set(get_args(FileRefSource)) == {
            "lobehub_upload",
            "sandbox_bootstrap",
            "machine_stage",
            "tool_export",
            "inline_text",
        }

    def test_ref_is_frozen_and_complete(self) -> None:
        ref = _ref()
        assert ref.is_resolved() is True
        # Frozen dataclass: assignment raises.
        raised = False
        try:
            ref.target_key = "x"  # type: ignore[misc]
        except Exception:
            raised = True
        assert raised


class TestAttachmentResolverContract:
    def test_resolver_satisfies_protocol(self) -> None:
        assert isinstance(_FakeResolver(), AttachmentResolver)

    def test_resolve_returns_one_per_id_in_order(self) -> None:
        out = _FakeResolver().resolve(["a", "b", "c"])
        assert [r.ref.target_key for r in out] == ["a", "b", "c"]
        assert all(r.inline_content is None for r in out)

    def test_resolve_for_plane_recomputes_process_path(self) -> None:
        ref = _ref(process_path="a/foo.yaml")
        machine = _plane(PlaneKind.MACHINE, "/inbox")
        sandbox = _plane(PlaneKind.SANDBOX, "/mnt/data")
        assert _FakeResolver().resolve_for_plane(ref, machine).process_path == "/inbox/a/foo.yaml"
        assert (
            _FakeResolver().resolve_for_plane(ref, sandbox).process_path == "/mnt/data/a/foo.yaml"
        )
        assert _FakeResolver().resolve_for_plane(ref, None) is ref


class TestAttachmentStagerContract:
    def test_stager_satisfies_protocol(self) -> None:
        assert isinstance(_FakeStager(), AttachmentStager)

    def test_stage_to_machine_keys_by_target_key(self) -> None:
        s = _FakeStager().stage_to_machine(
            run_id="r1", refs=[_ref(target_key="k1"), _ref(target_key="k2")]
        )
        assert s == {"k1": "/inbox/r1/k1", "k2": "/inbox/r1/k2"}

    def test_stage_to_sandbox_emits_mount_entries(self) -> None:
        ref = _ref(target_key="k1")
        ref = FileRef(
            kind=ref.kind,
            target_key=ref.target_key,
            display_path=ref.display_path,
            process_path=ref.process_path,
            file_url=ref.file_url,
            mime_type=ref.mime_type,
            size_bytes=ref.size_bytes,
            source=ref.source,
            attachment_id="aid-1",
        )
        entries = _FakeStager().stage_to_sandbox(sandbox_id="sb", refs=[ref])
        assert entries[0].path == "/mnt/data/k1"
        assert entries[0].attachment_id == "aid-1"


class TestAttachmentPromptRendererContract:
    def test_renderer_satisfies_protocol(self) -> None:
        assert isinstance(_FakeRenderer(), AttachmentPromptRenderer)

    def test_blocks_are_independent(self) -> None:
        r = _FakeRenderer()
        refs = [_ref(target_key="k1")]
        # identity block must NOT contain process_path; LLM uses url only.
        ident = r.identity_block(refs)
        assert "process_path" not in ident
        assert "<files_info" in ident
        # guest path block must NOT contain inline content; just paths.
        guest = r.guest_path_block(refs, _plane(PlaneKind.SANDBOX, "/mnt/data"))
        assert "<uploaded_files" in guest
        assert "/p/x" in guest


class TestSandboxBackendContract:
    def test_backend_satisfies_protocol(self) -> None:
        assert isinstance(_FakeBackend(), SandboxBackend)

    def test_backend_label_is_stable(self) -> None:
        # Plugins depend on `label` for journal attribution; reserve a string.
        assert isinstance(_FakeBackend().label, str)


class TestAttachmentErrorVocabulary:
    def test_codes_are_closed(self) -> None:
        # The enum is the SSOT; adding a code requires ADR.
        known = {c.value for c in AttachmentErrorCode}
        assert "attachment.unresolved_ref" in known
        assert "attachment.ambiguous_ref" in known
        assert "attachment.sandbox_backend_unavailable" in known

    def test_unresolved_carries_raw(self) -> None:
        err = UnresolvedFileRefError("/files/missing")
        assert err.code is AttachmentErrorCode.UNRESOLVED_REF
        assert err.context["raw"] == "/files/missing"

    def test_ambiguous_carries_matches(self) -> None:
        err = AmbiguousFileRefError("x", ("a", "b"))
        assert err.code is AttachmentErrorCode.AMBIGUOUS_REF
        assert err.context["matches"] == ("a", "b")
