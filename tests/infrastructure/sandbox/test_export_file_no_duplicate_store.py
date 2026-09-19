"""exportFile must not write a duplicate FileStore blob.

The export tool already stores the file and exposes ``state.files``. The
observation builder must reuse that record instead of persisting a second
copy through ``generated_files``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lca.contracts.models.core.execution.sandbox import SandboxFile
from lca.infrastructure.computer.op.result import ComputerOpResult
from lca.infrastructure.file.store import LocalFileStore, file_part_from_stored
from lca.infrastructure.tools.lca_computer.observations import build_computer_observation


def test_export_file_observation_reuses_stored_file_part() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalFileStore(root=Path(os.path.join(tmp, "files")))
        stored = store.put(data=b"# report", name="report.md", mime_type="text/markdown")

        result = ComputerOpResult(
            success=True,
            content=f"Exported {stored.name} ({stored.size_bytes} bytes)",
            state={
                "success": True,
                "path": "/mnt/data/outputs/report.md",
                "filename": stored.name,
                "download_url": stored.url,
                "mime_type": "text/markdown",
                "size": stored.size_bytes,
                "files": [file_part_from_stored(stored)],
            },
            generated_files=(
                SandboxFile(name=stored.name, mime_type="text/markdown", data=b"# report"),
            ),
        )

        obs = build_computer_observation(result, tool_name="exportFile", start=0.0, store=store)

        # The file part rides the observation for the ledger and tool wire.
        assert obs.extra["files"][0]["name"] == "report.md"
        assert obs.extra["files"][0]["url"] == stored.url
        # No second blob was persisted.
        assert len(list(store.root.iterdir())) == 1
