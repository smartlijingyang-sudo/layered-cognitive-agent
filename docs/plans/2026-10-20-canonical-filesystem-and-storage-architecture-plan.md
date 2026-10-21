# Canonical Filesystem & Storage Architecture Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Implement an enterprise-grade, persistent, write-in-place filesystem and storage system for `layered-cognitive-agent`, resolving the 9-run isolation mismatch and aligning with canonical Muse storage principles.

**Architecture:** Bind-mount the assistant's durable workspace `{assistant_home}/workspace/` directly to the sandbox guest `/mnt/data`, eliminating per-run session fragmentation. Ingest uploads directly to `workspace/user/`, enforce deliverables written in-place to `workspace/your_files/`, inject a dynamic `## Filesystem` prompt section, and gate delivery behind physical `stat` assertions.

**Tech Stack:** Python 3.12, Pydantic V2, SQLite (WAL mode), Linux `unshare` mount namespaces, Pytest.

---

### Task 1: Contracts Layer (`FileRecord` & Readability/Visibility Tiers)

**Files:**
- Create: `lca/contracts/models/core/workspace/file_record.py`
- Modify: `lca/contracts/models/core/workspace/__init__.py`
- Test: `tests/contracts/test_file_record_contract.py`
- Does NOT own: `lca/infrastructure/*`, `lca/cognition/*`, `lca/plugins/*`
- Invariants to test:
  1. `VisibilityTier` is deterministically derived from `path`: `your_files/*` and `goals/*/files/*` $\to$ `USER`; all others $\to$ `INTERNAL`.
  2. `readability_of(path, mime)` classifies extensions (`.txt`, `.py`, `.json` $\to$ `NATIVE`; `.pdf`, `.xlsx` $\to$ `CONVERTED`; `.png`, `.jpg` $\to$ `VISUAL`; `.bin` $\to$ `OPAQUE`).
  3. `sandbox://` URI generation format must strictly match `sandbox://workspace/<clean_relative_path>`.

**Step 1: Write the failing test**

```python
# tests/contracts/test_file_record_contract.py
import pytest
from datetime import datetime, timezone
from lca.contracts.models.core/workspace.file_record import (
    FileRecord,
    ReadabilityTier,
    VisibilityTier,
    derive_visibility,
    classify_readability,
    to_sandbox_uri,
)

def test_derive_visibility():
    assert derive_visibility("your_files/report.pdf") == VisibilityTier.USER
    assert derive_visibility("goals/growth/files/summary.md") == VisibilityTier.USER
    assert derive_visibility("goals/growth/hidden_files/seen.json") == VisibilityTier.INTERNAL
    assert derive_visibility("user/doc.xlsx") == VisibilityTier.INTERNAL
    assert derive_visibility(".trash/old.txt") == VisibilityTier.INTERNAL

def test_classify_readability():
    assert classify_readability("test.py", "text/x-python") == ReadabilityTier.NATIVE
    assert classify_readability("sheet.xlsx", "application/vnd.openxmlformats") == ReadabilityTier.CONVERTED
    assert classify_readability("chart.png", "image/png") == ReadabilityTier.VISUAL
    assert classify_readability("app.bin", "application/octet-stream") == ReadabilityTier.OPAQUE

def test_to_sandbox_uri():
    assert to_sandbox_uri("your_files/plan.pdf") == "sandbox://workspace/your_files/plan.pdf"
    assert to_sandbox_uri("/mnt/data/your_files/plan.pdf") == "sandbox://workspace/your_files/plan.pdf"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/contracts/test_file_record_contract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '...file_record'`

**Step 3: Write minimal implementation**

```python
# lca/contracts/models/core/workspace/file_record.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal
from pydantic import BaseModel, Field

class ReadabilityTier(str, Enum):
    NATIVE = "native"
    CONVERTED = "converted"
    VISUAL = "visual"
    OPAQUE = "opaque"

class VisibilityTier(str, Enum):
    USER = "user"
    INTERNAL = "internal"

_NATIVE_EXTENSIONS = {".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml", ".ts", ".js", ".html", ".sh"}
_CONVERTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".epub", ".rtf"}
_VISUAL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

def derive_visibility(path: str) -> VisibilityTier:
    clean = str(PurePosixPath(path.lstrip("/"))).replace("\\", "/")
    parts = clean.split("/")
    if parts and parts[0] == "your_files":
        return VisibilityTier.USER
    if len(parts) >= 3 and parts[0] == "goals" and parts[2] == "files":
        return VisibilityTier.USER
    return VisibilityTier.INTERNAL

def classify_readability(filename: str, mime: str = "") -> ReadabilityTier:
    ext = os.path.splitext(filename)[1].lower()
    if ext in _NATIVE_EXTENSIONS or mime.startswith("text/"):
        return ReadabilityTier.NATIVE
    if ext in _CONVERTED_EXTENSIONS or "officedocument" in mime or "pdf" in mime:
        return ReadabilityTier.CONVERTED
    if ext in _VISUAL_EXTENSIONS or mime.startswith("image/"):
        return ReadabilityTier.VISUAL
    return ReadabilityTier.OPAQUE

def to_sandbox_uri(rel_path: str) -> str:
    clean = rel_path.replace("/mnt/data/", "").lstrip("/")
    return f"sandbox://workspace/{clean}"

class FileRecord(BaseModel):
    file_id: str
    path: str
    origin: Literal["upload", "agent_created", "browser_download", "artifact_build"]
    visibility: VisibilityTier
    goal_id: str | None = None
    mime: str = "application/octet-stream"
    size_bytes: int = 0
    readability: ReadabilityTier = ReadabilityTier.OPAQUE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_chat_id: str | None = None
    trashed_at: datetime | None = None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/contracts/test_file_record_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/core/workspace/file_record.py tests/contracts/test_file_record_contract.py
git commit -m "feat(contracts): add FileRecord schema and visibility/readability helpers"
```

---

### Task 2: Sandbox Host Mount Consolidation (`LocalSandboxAdapter`)

**Files:**
- Modify: `lca/infrastructure/sandbox/local/adapter.py:131-135,316-324`
- Modify: `lca/infrastructure/sandbox/runtime/runtime.py:143-157`
- Test: `tests/infrastructure/sandbox/test_local_sandbox_workspace_mount.py`
- Does NOT own: `OnlyboxesSandboxAdapter`, `lca/plugins/prompts/*`
- Invariants to test:
  1. `_session_root` returns the persistent `{assistant_home}/workspace/` root.
  2. Files written to `/mnt/data/your_files/output.txt` by Run A are immediately available at the host `{assistant_home}/workspace/your_files/output.txt`.
  3. Run B using `listFiles('/mnt/data/your_files')` immediately finds `output.txt` without isolation loss.

**Step 1: Write the failing test**

```python
# tests/infrastructure/sandbox/test_local_sandbox_workspace_mount.py
import pytest
from pathlib import Path
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter

@pytest.mark.asyncio
async def test_sandbox_mounts_persistent_workspace_directly(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    adapter = LocalSandboxAdapter(host_root=str(workspace))

    # Session creation must now map directly to workspace, not create isolated .sessions subdirs
    session = await adapter.create_session()
    paths = adapter._paths_for(session.session_id)
    assert paths.host_root == workspace
    assert not (workspace / ".sessions").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/sandbox/test_local_sandbox_workspace_mount.py -v`
Expected: FAIL (currently creates `.sessions/lsess_xxx`)

**Step 3: Write minimal implementation**

In `lca/infrastructure/sandbox/local/adapter.py`:
- In `_session_root(self, session_id: str = "") -> Path`:
  When session belongs to an assistant workspace, return `Path(self._host_root)`.
- In `create_session`:
  Bind `session_id` to `Path(self._host_root)` rather than instantiating a new sub-folder under `.sessions/`.
- Ensure `outputs/`, `your_files/`, and `user/` directories exist on workspace initialization.

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/sandbox/test_local_sandbox_workspace_mount.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/sandbox/local/adapter.py tests/infrastructure/sandbox/test_local_sandbox_workspace_mount.py
git commit -m "fix(sandbox): unify local sandbox host root to persistent assistant workspace"
```

---

### Task 3: Upload Pipeline & FileStore Realignment (`workspace/user/`)

**Files:**
- Modify: `lca/infrastructure/file/store.py`
- Create: `lca/infrastructure/file/registry.py` (SQLite `workspace_files` index)
- Test: `tests/infrastructure/file/test_file_store_workspace_user.py`
- Does NOT own: Cognition reasoners, Web transport router
- Invariants to test:
  1. Uploaded files land in `{workspace}/user/<original_name>`.
  2. Name collisions append a monotonic timestamp suffix (`report_20261020_150950.xlsx`).
  3. `LocalFileStore.put` registers an entry in SQLite index `workspace_files`.
  4. Truncating the SQLite table and calling `rebuild_index_from_fs(workspace)` restores all records with identical metadata.

**Step 1: Write the failing test**

```python
# tests/infrastructure/file/test_file_store_workspace_user.py
import pytest
from pathlib import Path
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.file.registry import FileIndexRegistry

def test_upload_lands_in_user_directory_and_indexes(tmp_path: Path):
    workspace = tmp_path / "workspace"
    registry = FileIndexRegistry(db_path=tmp_path / "test_files.db")
    store = LocalFileStore(root=workspace, registry=registry)

    # Put file
    record = store.put(data=b"hello sql", name="uuids.sql", mime_type="application/sql", conversation_id="conv_123")
    expected_path = workspace / "user" / "uuids.sql"
    assert expected_path.exists()
    assert expected_path.read_bytes() == b"hello sql"
    assert record.path == "user/uuids.sql"

    # Collision test
    record2 = store.put(data=b"hello sql 2", name="uuids.sql", mime_type="application/sql")
    assert record2.path != "user/uuids.sql"
    assert record2.path.startswith("user/uuids_")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/file/test_file_store_workspace_user.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named '...registry'`

**Step 3: Write minimal implementation**

Implement `FileIndexRegistry` in `lca/infrastructure/file/registry.py` with SQLite table:
```sql
CREATE TABLE IF NOT EXISTS workspace_files (
    file_id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    origin TEXT NOT NULL,
    visibility TEXT NOT NULL,
    goal_id TEXT,
    mime TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    readability TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_chat_id TEXT,
    trashed_at TEXT
);
```
Update `LocalFileStore` in `lca/infrastructure/file/store.py` to write into `user/` subfolder and sync with `FileIndexRegistry`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/file/test_file_store_workspace_user.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/file/store.py lca/infrastructure/file/registry.py tests/infrastructure/file/test_file_store_workspace_user.py
git commit -m "feat(storage): relocate file store to workspace/user and add SQLite index registry"
```

---

### Task 4: Dedicated `## Filesystem` Prompt Section & Constitution Invariants

**Files:**
- Create: `lca/plugins/prompts/sections/filesystem.py`
- Modify: `lca/plugins/prompts/sections/__init__.py`
- Modify: `lca/plugins/assistant/templates/CONSTITUTION.md`
- Test: `tests/cognition/prompt/test_filesystem_section.py`
- Does NOT own: Execution runtime adapters, browser automation
- Invariants to test:
  1. Prompt contains explicit `## Filesystem` header and exact directory contracts (`your_files/`, `user/`, `/tmp`).
  2. Active turn uploads are enumerated under `Attachments available in ~/workspace/user/` with `/mnt/data/user/...` guest mapping.
  3. `CONSTITUTION.md` contains P0/P1/P2 persistence definitions.

**Step 1: Write the failing test**

```python
# tests/cognition/prompt/test_filesystem_section.py
import pytest
from lca.plugins.prompts.sections.filesystem import FilesystemPromptSection
from lca.contracts.models.core.workspace.file_record import FileRecord, ReadabilityTier, VisibilityTier

def test_filesystem_prompt_section_rendering():
    files = [
        FileRecord(
            file_id="f1",
            path="user/报价单.xlsx",
            origin="upload",
            visibility=VisibilityTier.INTERNAL,
            size_bytes=19000,
            readability=ReadabilityTier.CONVERTED,
        )
    ]
    section = FilesystemPromptSection(uploaded_files=files)
    rendered = section.render()

    assert "## Filesystem" in rendered
    assert "~/workspace/your_files/" in rendered
    assert "~/workspace/user/" in rendered
    assert "sandbox://workspace/path" in rendered
    assert "/mnt/data/user/报价单.xlsx" in rendered
    assert "converted" in rendered
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/cognition/prompt/test_filesystem_section.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Implement `FilesystemPromptSection` in `lca/plugins/prompts/sections/filesystem.py` as designed in §4.3.
Update `lca/plugins/assistant/templates/CONSTITUTION.md` to append the Storage & Workspace Invariant charter.

**Step 4: Run test to verify it passes**

Run: `pytest tests/cognition/prompt/test_filesystem_section.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/plugins/prompts/sections/filesystem.py lca/plugins/assistant/templates/CONSTITUTION.md tests/cognition/prompt/test_filesystem_section.py
git commit -m "feat(prompt): add FilesystemPromptSection and update CONSTITUTION.md invariants"
```

---

### Task 5: Delivery Gate & Physical Stat Verification

**Files:**
- Create: `lca/runtime/delivery/delivery_gate.py`
- Modify: `lca/runtime/pipeline/response_pipeline.py` (or post-process output filter)
- Test: `tests/agent/test_delivery_stat_gate.py`
- Does NOT own: Sandboxed bash process, code execution sandbox
- Invariants to test:
  1. Text with `![Report](sandbox://workspace/your_files/good.pdf)` passes if `workspace/your_files/good.pdf` exists.
  2. Text with `![Report](sandbox://workspace/your_files/missing.pdf)` raises `DeliveryVerificationError`.
  3. Text referencing `/tmp/...` as a download/attachment link raises `DeliverySecurityError`.

**Step 1: Write the failing test**

```python
# tests/agent/test_delivery_stat_gate.py
import pytest
from pathlib import Path
from lca.runtime.delivery.delivery_gate import verify_delivery_attachments, DeliveryVerificationError, DeliverySecurityError

def test_delivery_gate_blocks_missing_or_tmp_files(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "your_files").mkdir()
    (workspace / "your_files" / "real.pdf").write_bytes(b"content")

    # Valid delivery
    valid_text = "Here is your plan: ![Plan](sandbox://workspace/your_files/real.pdf)"
    assert verify_delivery_attachments(valid_text, workspace_root=workspace) is True

    # Missing file delivery
    fake_text = "Generated: ![Fake](sandbox://workspace/your_files/ghost.pdf)"
    with pytest.raises(DeliveryVerificationError):
        verify_delivery_attachments(fake_text, workspace_root=workspace)

    # Ephemeral /tmp leak
    tmp_leak_text = "Here: ![Temp](sandbox://workspace//tmp/scratch.pdf)"
    with pytest.raises(DeliverySecurityError):
        verify_delivery_attachments(tmp_leak_text, workspace_root=workspace)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_delivery_stat_gate.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Implement `verify_delivery_attachments` in `lca/runtime/delivery/delivery_gate.py` using regex `sandbox://workspace/([^\s\)]+)`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_delivery_stat_gate.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/runtime/delivery/delivery_gate.py tests/agent/test_delivery_stat_gate.py
git commit -m "feat(runtime): add delivery gate with physical stat and tmp path assertion"
```

---

### Task 6: Recoverable Trash Manager (`.trash/`)

**Files:**
- Create: `lca/infrastructure/file/trash.py`
- Test: `tests/infrastructure/file/test_trash_manager.py`
- Does NOT own: User auth, network sockets
- Invariants to test:
  1. `trash_file("your_files/old.pdf")` moves file to `.trash/<timestamp>_old.pdf`.
  2. Index marks `trashed_at` with timestamp; file disappears from active listings.
  3. `restore_file("your_files/old.pdf")` moves file back to exact original path and clears `trashed_at`.

**Step 1: Write the failing test**

```python
# tests/infrastructure/file/test_trash_manager.py
import pytest
from pathlib import Path
from lca.infrastructure.file.trash import TrashManager
from lca.infrastructure.file.registry import FileIndexRegistry

def test_trash_and_restore_cycle(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "your_files" / "report.pdf"
    target.parent.mkdir()
    target.write_bytes(b"report bytes")

    registry = FileIndexRegistry(db_path=tmp_path / "test.db")
    trash = TrashManager(workspace_root=workspace, registry=registry)

    # Delete
    trash.trash_file("your_files/report.pdf")
    assert not target.exists()
    assert len(list((workspace.parent / ".trash").iterdir())) == 1

    # Restore
    trash.restore_file("your_files/report.pdf")
    assert target.exists()
    assert target.read_bytes() == b"report bytes"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/infrastructure/file/test_trash_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Implement `TrashManager` in `lca/infrastructure/file/trash.py` with 30-day purge helper.

**Step 4: Run test to verify it passes**

Run: `pytest tests/infrastructure/file/test_trash_manager.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/file/trash.py tests/infrastructure/file/test_trash_manager.py
git commit -m "feat(storage): implement recoverable TrashManager and index sync"
```

---

### Task 7: End-to-End Regression Verification (INV-FS-01 ~ 10)

**Files:**
- Create: `tests/e2e/test_canonical_filesystem_invariants.py`
- Does NOT own: Production production servers
- Invariants to test:
  1. Full reproduction of the 9-run conversation: Run 1 uploads Excel $\to$ Run 2 executes code to read Excel $\to$ Run 3 writes PDF $\to$ Run 4 executes `listFiles` and immediately finds both the Excel in `user/` and PDF in `your_files/`.
  2. No hallucinatory apologies.

**Step 1: Write the end-to-end test**

```python
# tests/e2e/test_canonical_filesystem_invariants.py
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_cross_turn_workspace_continuity_e2e(tmp_path: Path):
    # Setup test workspace and simulator
    ...
```

**Step 2: Run test to verify it passes with the new unified architecture**

Run: `pytest tests/e2e/test_canonical_filesystem_invariants.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/e2e/test_canonical_filesystem_invariants.py
git commit -m "test(e2e): verify 10 canonical filesystem invariants and cross-turn continuity"
```

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-10-20-canonical-filesystem-and-storage-architecture-plan.md`.

Next step: run `.agent/workflows/execute-plan.md` to execute this plan task-by-task in single-flow mode.
