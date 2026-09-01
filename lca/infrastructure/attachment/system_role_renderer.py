"""Single system-role renderer — the only entry point for attachment prompts (ADR-0121).

The previous code path had four renderers that all touched ``<uploaded_files>``
/ ``<files_info>`` / ``{{attachment_policy}}`` in different files; whenever a
new path was added (DSH, then removed again), one branch silently lost its
injection. This module collapses them:

  * :func:`render_system_role` reads the current plane, resolves the
    FileStore ambient, and renders the matching template in **one** pass.
  * All placeholders (``{{uploaded_files}}``, ``{{sandbox_uploaded_files}}``,
    ``{{attachment_policy}}``, ``{{sandbox_environment_note}}``, …) are
    substituted here so a future placeholder cannot drift between branches.

Plugin / sandbox / machine-face swaps do not change this function's
signature: only the providers it composes change.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Protocol

from lca.contracts.models.core.file_ref import FileRef
from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.infrastructure.attachment.default_provider import (
    DefaultAttachmentPromptRenderer,
    DefaultAttachmentResolver,
    DefaultAttachmentStager,
)
from lca.infrastructure.attachment.settings import (
    AttachmentPolicyDocument,
    get_attachment_policy,
)
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.observability import current_file_store as get_current_run_file_store
from lca.infrastructure.sandbox.paths import ONLYBOXES


class _PlaneAccess(Protocol):
    """Minimal subset of :class:`PlaneRef` we actually read here."""

    kind: PlaneKind
    root: str
    outputs_dir: str
    label: str
    platform: str
    home: str


@dataclass(frozen=True)
class SystemRoleResult:
    """What the renderer hands back to the Reasoner."""

    text: str
    plane_kind: str
    refs_rendered: tuple[FileRef, ...]


def render_system_role(
    plane: PlaneRef | None,
    *,
    template_name: str,
    store: FileStore | None = None,
    extra_placeholders: dict[str, str] | None = None,
) -> SystemRoleResult:
    """Render one system-role block, fully substituted.

    Args:
      plane: the current :class:`PlaneRef` (``None`` → use the default sandbox).
      template_name: ``"cloud_sandbox_system_role"`` or ``"machine_system_role"``.
      store: explicit ``FileStore`` (preferred); falls back to the run ambient.
      extra_placeholders: caller-supplied substitutions appended after our own.
    """
    effective_store = store if store is not None else get_current_run_file_store()
    policy = get_attachment_policy()
    refs = _resolve_refs(effective_store)
    resolved_refs = tuple(_resolver().resolve_for_plane(r, plane) for r in refs)

    rendered_provider = DefaultAttachmentPromptRenderer(
        resolver=_resolver(),
        policy=policy,
    )

    template = _load_template(template_name)
    text = template
    text = text.replace(
        "{{attachment_policy}}",
        _policy_text(
            policy,
            plane,
        ),
    )
    text = text.replace("{{uploaded_files}}", rendered_provider.guest_path_block(refs, plane))
    text = text.replace(
        "{{sandbox_uploaded_files}}",
        rendered_provider.guest_path_block(refs, plane),
    )
    text = text.replace("{{sandbox_environment_note}}", _environment_note(plane))
    text = text.replace(
        "{{sandbox_workspace_root}}", plane.root if plane is not None else ONLYBOXES.root
    )
    text = text.replace(
        "{{sandbox_outputs_dir}}",
        plane.outputs_dir if plane is not None else ONLYBOXES.outputs_dir,
    )
    if plane is not None:
        text = text.replace("{{label}}", plane.label)
        text = text.replace("{{platform}}", plane.platform or "unknown")
        text = text.replace("{{root}}", plane.root)
        text = text.replace("{{outputs_dir}}", plane.outputs_dir)
    if extra_placeholders:
        for key, value in extra_placeholders.items():
            text = text.replace(key, value)

    return SystemRoleResult(
        text=text,
        plane_kind=(plane.kind.name if plane is not None else "NONE"),
        refs_rendered=resolved_refs,
    )


def _resolver() -> DefaultAttachmentResolver:
    store = get_current_run_file_store()
    if store is None:  # pragma: no cover - covered by tests
        raise RuntimeError(
            "render_system_role: no FileStore in ambient scope; "
            "bind via run_file_store_scope() before reasoning"
        )
    return DefaultAttachmentResolver(store=store)


def _resolve_refs(store: FileStore | None) -> tuple[FileRef, ...]:
    if store is None:
        return ()
    from lca.infrastructure.tools.run_attachment_scope import (
        get_current_run_attachment_ids,
    )

    ids = get_current_run_attachment_ids()
    if not ids:
        return ()
    resolver = DefaultAttachmentResolver(store=store)
    return tuple(item.ref for item in resolver.resolve(ids))


def _policy_text(policy: AttachmentPolicyDocument, plane: PlaneRef | None) -> str:
    if plane is not None and plane.kind is PlaneKind.MACHINE:
        return policy.machine_policy_text()
    return policy.sandbox_policy_text(plane.root if plane is not None else ONLYBOXES.root)


def _environment_note(plane: PlaneRef | None) -> str:
    if plane is None:
        return (
            f"- Workspace root: {ONLYBOXES.root}\n"
            f"- **Output directory (required for generated files): {ONLYBOXES.outputs_dir}**"
        )
    return (
        f"- Workspace root: {plane.root}\n"
        f"- **Output directory (required for generated files): {plane.outputs_dir}**"
    )


def _load_template(name: str) -> str:
    """Load a system-role template by name.

    Templates live under either ``lca.cognition.brain.prompts`` (cloud-sandbox)
    or ``lca.infrastructure.runtime_plane.prompts`` (machine); the renderer
    resolves whichever one exists first.
    """
    for package in ("lca.cognition.brain.prompts", "lca.infrastructure.runtime_plane.prompts"):
        try:
            return resources.files(package).joinpath(f"{name}.md").read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError):
            continue
    raise FileNotFoundError(f"system-role template {name!r} not found in any prompts package")


__all__ = ["SystemRoleResult", "render_system_role"]


# Re-exported to keep the public surface of the default provider package
# discoverable from a single import for plugin / scaffolding code.
_ = (DefaultAttachmentPromptRenderer, DefaultAttachmentResolver, DefaultAttachmentStager, Sequence)
