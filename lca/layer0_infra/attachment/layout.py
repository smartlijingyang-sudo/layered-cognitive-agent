"""Run-scoped inbox paths. Machine home is never the attachment root."""

from __future__ import annotations

from lca.contracts.models.core.guest_layout import join_under
from lca.layer0_infra.attachment.settings import AttachmentPolicyDocument, get_attachment_policy


def sanitize_attachment_name(name: str) -> str:
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [part for part in cleaned.split("/") if part and part not in {".", ".."}]
    return parts[-1] if parts else "file"


def sanitize_run_segment(run_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in run_id.strip())
    return cleaned or "unbound"


class AttachmentLayout:
    """Derive inbox paths from the policy document."""

    def __init__(self, policy: AttachmentPolicyDocument | None = None) -> None:
        self._policy = policy if policy is not None else get_attachment_policy()

    @property
    def policy(self) -> AttachmentPolicyDocument:
        return self._policy

    def relative_file(self, run_id: str, name: str) -> str:
        return join_under(
            self._policy.inbox_dir,
            sanitize_run_segment(run_id),
            sanitize_attachment_name(name),
        )

    def absolute_file(self, root: str, run_id: str, name: str) -> str:
        return join_under(root, self.relative_file(run_id, name))
