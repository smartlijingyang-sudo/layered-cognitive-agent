"""Unit tests for the default attachment provider + renderer (ADR-0121 PR-B).

Covers:
  * Resolver correctly maps attachment_id → FileRef (kind=user_upload).
  * resolve_for_plane swaps display_path → sandbox_init or inbox_staged.
  * Renderer identity/guest/inline blocks render the right LLM-facing shapes.
  * System role renderer fills *all* placeholders in one pass — this is the
    regression gate for the trace that lost <files_info> / <uploaded_files>.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.attachment.default_provider import (
    DefaultAttachmentPromptRenderer,
    DefaultAttachmentResolver,
    DefaultAttachmentStager,
)
from lca.infrastructure.attachment.run_file_store_scope import run_file_store_scope
from lca.infrastructure.attachment.run_machine_root_scope import run_machine_root_scope
from lca.infrastructure.attachment.settings import (
    reset_attachment_settings_for_tests,
)
from lca.infrastructure.attachment.system_role_renderer import render_system_role
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.tools.run_attachment_scope import run_attachment_scope


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_attachment_settings_for_tests()
    yield
    reset_attachment_settings_for_tests()


@pytest.fixture
def tmp_store(tmp_path: Path) -> LocalFileStore:
    store = LocalFileStore(root=tmp_path)
    store.put(
        data=b"hello world",
        name="Clash_1752915628.yaml",
        mime_type="text/plain",
    )
    return store


def _first_id(store: LocalFileStore) -> str:
    for k in store._root.iterdir():  # type: ignore[attr-defined]
        return k.name
    raise AssertionError("store empty")


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class TestDefaultResolver:
    def test_resolves_to_user_upload(self, tmp_store: LocalFileStore) -> None:
        aid = _first_id(tmp_store)
        resolver = DefaultAttachmentResolver(store=tmp_store)
        out = resolver.resolve([aid])
        assert len(out) == 1
        ref = out[0].ref
        assert ref.kind == "user_upload"
        assert ref.target_key == aid
        assert ref.display_path == "Clash_1752915628.yaml"
        assert ref.file_url.startswith("/files/")
        assert ref.attachment_id == aid

    def test_resolve_for_sandbox_sets_sandbox_path(self, tmp_store: LocalFileStore) -> None:
        aid = _first_id(tmp_store)
        ref = DefaultAttachmentResolver(store=tmp_store).resolve([aid])[0].ref
        sandbox = PlaneRef(
            id="sb",
            label="sb",
            kind=PlaneKind.SANDBOX,
            root="/mnt/data",
            outputs_dir="/mnt/data/outputs",
        )
        resolved = DefaultAttachmentResolver(store=tmp_store).resolve_for_plane(ref, sandbox)
        assert resolved.process_path == "/mnt/data/Clash_1752915628.yaml"
        assert resolved.kind == "sandbox_init"

    def test_resolve_for_machine_uses_inbox(self, tmp_store: LocalFileStore) -> None:
        aid = _first_id(tmp_store)
        ref = DefaultAttachmentResolver(store=tmp_store).resolve([aid])[0].ref
        machine = PlaneRef(
            id="m", label="m", kind=PlaneKind.MACHINE, root="/inbox", outputs_dir="/inbox/outputs"
        )
        resolved = DefaultAttachmentResolver(store=tmp_store).resolve_for_plane(ref, machine)
        assert resolved.kind == "inbox_staged"
        assert "/inbox/" in resolved.process_path
        assert resolved.process_path.endswith("Clash_1752915628.yaml")


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class TestDefaultRenderer:
    def test_identity_block_has_files_info_but_no_process_path(
        self, tmp_store: LocalFileStore
    ) -> None:
        aid = _first_id(tmp_store)
        resolver = DefaultAttachmentResolver(store=tmp_store)
        refs = [item.ref for item in resolver.resolve([aid])]
        renderer = DefaultAttachmentPromptRenderer(resolver=resolver)
        text = renderer.identity_block(refs)
        assert "<files_info>" in text
        assert 'url="/files/' in text
        # LLM-facing identity must NOT leak sandbox paths.
        assert "/mnt/data" not in text

    def test_guest_path_block_lists_process_path(self, tmp_store: LocalFileStore) -> None:
        aid = _first_id(tmp_store)
        resolver = DefaultAttachmentResolver(store=tmp_store)
        refs = [item.ref for item in resolver.resolve([aid])]
        renderer = DefaultAttachmentPromptRenderer(resolver=resolver)
        sandbox = PlaneRef(
            id="sb",
            label="sb",
            kind=PlaneKind.SANDBOX,
            root="/mnt/data",
            outputs_dir="/mnt/data/outputs",
        )
        text = renderer.guest_path_block(refs, sandbox)
        assert "<uploaded_files>" in text
        assert "/mnt/data/Clash_1752915628.yaml" in text

    def test_guest_path_block_is_empty_when_no_refs(self, tmp_store: LocalFileStore) -> None:
        renderer = DefaultAttachmentPromptRenderer(
            resolver=DefaultAttachmentResolver(store=tmp_store)
        )
        assert renderer.guest_path_block((), plane=None) == ""


# ---------------------------------------------------------------------------
# System-role renderer — the regression gate
# ---------------------------------------------------------------------------


class TestSystemRoleRendererRegression:
    """Lock down the trace-failure trace: ``run_75e88a76899b`` lost
    ``<files_info>`` and ``<uploaded_files>`` because
    ``build_cloud_sandbox_prompt`` gated on ``store is not None``.
    These tests assert that — given any ambient scope — both blocks appear.
    """

    def test_cloud_branch_emits_uploaded_files_block(
        self, tmp_store: LocalFileStore
    ) -> None:
        aid = _first_id(tmp_store)
        with run_file_store_scope(tmp_store), run_attachment_scope([aid]):
            result = render_system_role(
                plane=PlaneRef(
                    id="sb",
                    label="sb",
                    kind=PlaneKind.SANDBOX,
                    root="/mnt/data",
                    outputs_dir="/mnt/data/outputs",
                ),
                template_name="cloud_sandbox_system_role",
            )
        assert "<uploaded_files>" in result.text
        assert "/mnt/data/Clash_1752915628.yaml" in result.text

    def test_no_attachments_renders_empty_uploaded_block(self, tmp_store: LocalFileStore) -> None:
        with run_file_store_scope(tmp_store):
            result = render_system_role(
                plane=PlaneRef(
                    id="sb",
                    label="sb",
                    kind=PlaneKind.SANDBOX,
                    root="/mnt/data",
                    outputs_dir="/mnt/data/outputs",
                ),
                template_name="cloud_sandbox_system_role",
            )
        # Template keeps its <uploaded_files> tag, but the guest list is empty.
        assert "<uploaded_files>" in result.text
        assert "Clash_1752915628.yaml" not in result.text

    def test_all_placeholders_substituted_in_one_pass(self, tmp_store: LocalFileStore) -> None:
        aid = _first_id(tmp_store)
        with run_file_store_scope(tmp_store), run_attachment_scope([aid]):
            result = render_system_role(
                plane=PlaneRef(
                    id="sb",
                    label="sb",
                    kind=PlaneKind.SANDBOX,
                    root="/mnt/data",
                    outputs_dir="/mnt/data/outputs",
                ),
                template_name="cloud_sandbox_system_role",
            )
        # No leftover placeholders from the cloud sandbox template.
        for placeholder in (
            "{{attachment_policy}}",
            "{{uploaded_files}}",
            "{{sandbox_uploaded_files}}",
            "{{sandbox_environment_note}}",
            "{{sandbox_workspace_root}}",
            "{{sandbox_outputs_dir}}",
        ):
            assert placeholder not in result.text, f"unfilled {placeholder}"


# ---------------------------------------------------------------------------
# Stager
# ---------------------------------------------------------------------------


class TestDefaultStager:
    def test_stage_to_machine_writes_file(self, tmp_store: LocalFileStore, tmp_path: Path) -> None:
        aid = _first_id(tmp_store)
        resolver = DefaultAttachmentResolver(store=tmp_store)
        ref = resolver.resolve([aid])[0].ref
        stager = DefaultAttachmentStager(resolver=resolver)
        with run_machine_root_scope(str(tmp_path / "machine-root")):
            out = stager.stage_to_machine(run_id="r1", refs=[ref])
        assert aid in out
        assert Path(out[aid]).exists()
        assert Path(out[aid]).read_bytes() == b"hello world"
