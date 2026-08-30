"""Map LCA machine plane → DeepSeek Harness SDK launch env (paths only, no prompts)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from lca.contracts.models.core.guest_layout import join_under
from lca.contracts.models.core.plane import PlaneRef
from lca.infrastructure.attachment import get_attachment_policy
from lca.infrastructure.attachment.layout import sanitize_run_segment
from lca.infrastructure.attachment.prompt import render_dsh_workspace_context
from lca.infrastructure.dsh.settings import DshSettings
from lca.infrastructure.file_store import FileStore, LocalFileStore


def build_harness_env(
    machine: PlaneRef,
    *,
    run_id: str,
    session_root: Path | str,
    settings: DshSettings | None = None,
    attachment_ids: Sequence[str] | None = None,
    store: FileStore | None = None,
) -> dict[str, str]:
    """Factual paths for DSH cordis (``DSH_CWD`` is set by the SDK from ``cwd``).

    ``LCA_*`` keys are optional hooks for custom cordis overlays. Bundled DSH
    defaults use ``DSH_CWD`` + agent ``workspaceContext``; skills stay on DSH
    ``tool-skill`` — not LCA ``activate_skill``.
    """
    cfg = settings if settings is not None else DshSettings()
    env: dict[str, str] = {}
    root = (machine.root or "").strip()
    outputs = (machine.outputs_dir or "").strip()
    if root:
        env["LCA_MACHINE_ROOT"] = root
    if outputs:
        env["LCA_OUTPUTS_DIR"] = outputs
    policy = get_attachment_policy()
    inbox_rel = join_under(policy.inbox_dir, sanitize_run_segment(run_id))
    if root:
        env["LCA_INBOX_DIR"] = join_under(root, inbox_rel)
    else:
        env["LCA_INBOX_DIR"] = inbox_rel
    env["LCA_RUN_ID"] = run_id.strip()
    env["DSH_SESSION_ROOT"] = str(session_root)
    prompt = cfg.system_prompt.strip()
    ids = tuple(str(i).strip() for i in (attachment_ids or ()) if str(i).strip())
    if ids and root:
        active_store = store if store is not None else LocalFileStore()
        workspace_ctx = render_dsh_workspace_context(root, run_id, ids, active_store)
        if workspace_ctx:
            prompt = f"{prompt}\n\n{workspace_ctx}".strip() if prompt else workspace_ctx
    if prompt:
        env["DSH_SYSTEM_PROMPT"] = prompt
    return env
