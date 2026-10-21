"""FilesystemPromptSection — Canonical filesystem & storage contract injection.

ADR-0244 / Canonical Muse Filesystem SSOT alignment.
Injects durable workspace topology, delivery contracts, and dynamic attachment listings.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.execution.sandbox import SANDBOX_MOUNT_ROOT
from lca.contracts.models.core.workspace.file_record import FileRecord

_FILESYSTEM_CORE_TEMPLATE = """## Filesystem

Your home directory is `~` and your workspace is `~/workspace` (mapped inside your execution sandbox as `{mount}`). File tools resolve relative paths from `~`.

Persistence: `~` survives restarts and machine replacements. Treat anything outside it (including /usr/local/bin, /etc, /root, /var) as ephemeral: it can disappear at any time. Keep durable files, scripts and tools under `~/workspace/` and reference them by explicit path in scheduled jobs.

Directory contract:
- `~/workspace/your_files/`: ONLY files meant for the user. A deliverable is written here (or into its goal's files/ dir) on the way in, never built elsewhere and copied or moved afterwards. A copy leaves two documents that drift; a move breaks links the user already has.
- `~/workspace/goals/<goal-slug>/files/`: user-facing documents for that goal. Internal bookkeeping (run logs, watermarks, seen lists, snapshots) goes to `~/workspace/goals/<goal-slug>/hidden_files/`, never files/.
- `~/workspace/user/`: files the user handed you. Uploads land here; they do not automatically appear in the user's Library.
- `/tmp`: ephemeral scratch only (page scrapes, dumps, screenshots). Never hand the user a /tmp path; move final outputs to their real location.

Delivery: attach a file by putting `![alt](sandbox://workspace/path)` on its own line. Verify the file exists before attaching it. Never mention a file by bare path alone.""".replace(
    "{mount}", SANDBOX_MOUNT_ROOT
)


@dataclass
class FilesystemPromptSection:
    """Prompt section delivering canonical filesystem rules and dynamic turn attachments."""

    name: ClassVar[str] = "filesystem"
    uploaded_files: Sequence[FileRecord] = field(default_factory=tuple)

    def render(self, *args, **kwargs) -> SectionOutput:
        body = _FILESYSTEM_CORE_TEMPLATE
        if self.uploaded_files:
            lines = ["\n\nAttachments available in ~/workspace/user/:"]
            for f in self.uploaded_files:
                guest_path = f"{SANDBOX_MOUNT_ROOT}/{f.path}"
                size_kb = max(1, f.size_bytes // 1024)
                lines.append(
                    f"- `{f.path}` (Readability: {f.readability.value}, Size: {size_kb}KB) -> accessible at `{guest_path}`"
                )
            body += "\n".join(lines)
        return SectionOutput(text=body)


__all__ = ["FilesystemPromptSection"]
