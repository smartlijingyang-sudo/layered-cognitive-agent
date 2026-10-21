# Canonical Filesystem & Storage Architecture Design (Layered Cognitive Agent)

> **Document ID**: `LCA-DESIGN-2026-10-20-FS-STORAGE`
> **Target System**: `/home/lichao/layered-cognitive-agent` (252 & Production LCA Nodes)
> **Author**: Antigravity Pair Programming & System Architecture
> **Date**: 2026-10-20
> **Status**: APPROVED (Ready for Implementation Planning)
> **Autopilot Blast Radius**: `DRAFT` (Core runtime & sandbox mount refactor; gated by automated verification suites)

---

## 0. Executive Summary & Problem Diagnosis

### 0.1 The Incident: 9 Consecutive Runs RCA
On 2026-10-20 (15:08 ~ 15:28), assistant `asst_98281d294a4e` engaged in a 9-turn session (`tpc_P7ZxHkwqjZak.jsonl`) involving file uploads (`uuids.sql`, `快乐通宝-法大大公有云电子签报价单0622.xlsx`) and generated deliverables (`法大大电子签报价分析报告.pdf`, `北京出差计划_20261021.pdf`).

**The Failure Mode**:
When the user asked *"Are my uploaded file and your generated file saved in your workspace?"* (Run 5) and *"Why didn't you save to workspace?"* (Run 7), the agent ran `listFiles('/mnt/data')`, saw an empty directory, and hallucinated that:
1. Uploaded files are purely ephemeral and disappeared.
2. The generated PDF was exported without keeping a copy in workspace.
3. The agent offered an apologetic, factually false commitment promising to "save a copy to workspace next time".

**Root Cause**:
- **Isolation Mismatch (Session Per Run vs Session Per Assistant)**: The `LocalSandboxAdapter` generated a brand new isolated directory `.sessions/lsess_<random>/` for every single run.
- **Physical Disconnect**: Files were indeed persisted on host disk under `.sessions/lsess_xxx`, but each new run mounted a new empty `.sessions/lsess_yyy` as `/mnt/data`.
- **Cognitive Blindspot**: The agent had no visibility into previous run sessions, believing `/mnt/data` was empty.

---

## 1. Architectural Scope & Mandatory Boundaries (AP-01 & AP-05)

### 1.1 Boundaries
- **Owns (In-Scope)**:
  - **`contracts`**: Definition of `FileRecord`, `ReadabilityTier`, `VisibilityTier`, and `sandbox://` URI specification.
  - **`infrastructure`**:
    - Refactor `LocalSandboxAdapter` to bind-mount `{assistant_home}/workspace/` directly to `/mnt/data`, deprecating per-run session fragmentation.
    - Migrate `FileStore` root from `traces/files/` directly to `{assistant_home}/workspace/user/`.
    - Implement SQLite file index registry (`workspace_files.db` or metadata table) with full fs-scan recovery capability.
    - Implement `.trash/` recoverable retention engine (30-day soft delete).
  - **`cognition`**:
    - Implement dedicated `FilesystemPromptSection` (`## Filesystem`) in `lca/plugins/prompts/sections/filesystem.py`.
    - Document fundamental storage invariances in `CONSTITUTION.md`.
  - **`runtime`**:
    - Upload ingestion pipeline with format/size gating and silent transcoding.
    - Delivery gate with physical `stat` validation before permitting `sandbox://` links.
    - Zero-copy Library and System Files projection service.
  - **`agent`**: Standardize core tools (`read_file`, `write_file`, `edit_file`, `trash_file`, `list_files`).
- **Does NOT own (Strictly Out-of-Scope / Forbidden to Mutate)**:
  - Do NOT modify the guest contract root `/mnt/data` (required by Onlyboxes remote images).
  - Do NOT alter core conversation and state schemas in `agent-state.db`.
  - Do NOT modify semantic memory vector retrieval engines (`memory_search`).

---

## 2. Five Inviolable First Principles

1. **State is External, Model is Stateless**: The LLM remembers nothing across runs. Memory compaction compresses dialogue history, but the filesystem **never participates in compaction**.
2. **SSOT Workspace**: `{assistant_home}/workspace/` is the single source of truth for all durable artifacts.
3. **Write-in-Place (创建即归位)**: Deliverables are created directly at their destination (`your_files/` or `goals/<slug>/files/`). Temporary drafting then copying is strictly banned (eliminating duplicate drift and broken links).
4. **Physical Visibility Isolation**: User deliverables and internal bookkeeping are partitioned by **filesystem paths**, never by prompt-level self-discipline.
5. **Soft Guidance + Hard Guarantees**: Prompts guide the agent; runtime mounts and tool gates enforce physical existence and boundaries.

---

## 3. Directory Layout & Persistence Hierarchy

```text
{assistant_home}/                          # e.g., ~/.lca/assistants/<asst_id>/
├── workspace/                             # The SSOT Workspace (Mapped as /mnt/data in Sandbox)
│   ├── your_files/                        # [User Visible] Unassigned deliverables (PDFs, reports, charts)
│   ├── goals/<goal-slug>/
│   │   ├── GOAL.md                        # Goal execution notes
│   │   ├── files/                         # [User Visible] Goal-specific deliverables
│   │   └── hidden_files/                  # [Agent Only] Bookkeeping (watermarks, seen lists, logs)
│   ├── user/                              # [Agent/User] User uploads landing zone
│   │   └── media_library/                 # User-uploaded images/videos
│   ├── custom-skills/                     # Installed custom skills
│   └── custom-connectors/                 # Local connectors
├── memory/                                # Memory tree (MEMORY.md, people/, groups/)
├── docs/                                  # Read-only product documentation
└── .trash/                                # 30-day recoverable trash repository
```

### Persistence Tiers
| Tier | Scope | Target Path | Lifecycle & Guarantees |
|---|---|---|---|
| **P0 Persistent** | Across reboots, machines & chats | `{assistant_home}/workspace/` | Bound to persistent volume. Survives container restarts. |
| **P1 Task-level** | Duration of active task | `workspace/.worktree/` or sandbox scratch | Cleaned after task completion. |
| **P2 Ephemeral** | Transient dump | `/tmp` | Volatile scratch space. Strictly forbidden to hand `/tmp` paths to users. |

---

## 4. Layered System Architecture & Data Flow

### 4.1 Layer 1: Contracts (`lca/contracts/`)
```python
class ReadabilityTier(str, Enum):
    NATIVE = "native"        # Text, Markdown, Python, JSON, CSV
    CONVERTED = "converted"  # PDF, Word, Excel, PPT (parsed to Markdown text)
    VISUAL = "visual"        # PNG, JPEG, WEBP (injected into multimodal context)
    OPAQUE = "opaque"        # Binaries, archives (metadata registered only)

class VisibilityTier(str, Enum):
    USER = "user"            # Derived if path is under your_files/ or goals/*/files/
    INTERNAL = "internal"    # Derived for all other paths

class FileRecord(BaseModel):
    file_id: str             # UUID
    path: str                # Relative to workspace root, unique key
    origin: Literal["upload", "agent_created", "browser_download", "artifact_build"]
    visibility: VisibilityTier
    goal_id: str | None = None
    mime: str
    size_bytes: int
    readability: ReadabilityTier
    created_at: datetime
    updated_at: datetime
    source_chat_id: str | None = None
    trashed_at: datetime | None = None
```

### 4.2 Layer 2: Infrastructure (`lca/infrastructure/`)
1. **`LocalSandboxAdapter` Mount Unification**:
   - Instead of per-run `.sessions/lsess_*`, the adapter mounts `{assistant_home}/workspace/` directly:
     ```bash
     unshare -Urm bash -c 'mount --make-rprivate /; mkdir -p /mnt/data; mount --bind {assistant_home}/workspace /mnt/data; cd /mnt/data && <cmd>'
     ```
   - In virtual path mode (fallback), `/mnt/data` resolves directly to `{assistant_home}/workspace/`.
2. **`LocalFileStore` Redirection**:
   - File uploads land in `{assistant_home}/workspace/user/`.
   - File collisions resolve via timestamp affix (`<name>_YYYYMMDD_HHMMSS.<ext>`).
   - Metadata is recorded in SQLite file index.
3. **`TrashManager` (`.trash/`)**:
   - Soft deletion moves file to `.trash/<timestamp>_<filename>` with reverse mapping preserved.
   - Deletion sets `trashed_at`. Restoration moves file back and clears `trashed_at`.

### 4.3 Layer 3: Cognition & Prompt Assembly (`lca/cognition/` & `lca/plugins/prompts/`)
1. **`FilesystemPromptSection` (`## Filesystem`)**:
   Implemented in `lca/plugins/prompts/sections/filesystem.py`. Dynamically injected into prompt:
   ```text
   ## Filesystem
   Your home directory is `~` and your workspace is `~/workspace` (mapped inside your execution sandbox as `/mnt/data`). File tools resolve relative paths from `~`.

   Persistence: `~` survives restarts and machine replacements. Keep durable files, scripts and tools under `~/workspace/`. Anything under `/tmp` is strictly ephemeral.

   Directory contract:
   - `~/workspace/your_files/`: ONLY files meant for the user. A deliverable is written here (or into its goal's files/ dir) on the way in, never built elsewhere and copied or moved afterwards.
   - `~/workspace/goals/<goal-slug>/files/`: user-facing documents for that goal. Internal bookkeeping (run logs, watermarks, seen lists, snapshots) goes to `~/workspace/goals/<goal-slug>/hidden_files/`, never files/.
   - `~/workspace/user/`: files the user handed you. Uploads land here; they do not automatically appear in the user's Library.
   - `/tmp`: ephemeral scratch only (page scrapes, dumps, screenshots). Never hand the user a /tmp path.

   Delivery: attach a file by putting `![alt](sandbox://workspace/path)` on its own line. Verify the file exists before attaching it. Never mention a file by bare path alone.
   ```
2. **Dynamic Ingestion Injection**:
   If user uploads files in the current turn, inject a dedicated sub-block:
   ```text
   Attachments available in ~/workspace/user/:
   - `user/报价单.xlsx` (Readability: converted, Size: 19KB) -> accessible at `/mnt/data/user/报价单.xlsx`
   ```

### 4.4 Layer 4: Runtime Orchestration (`lca/runtime/`)
1. **Upload Pipeline**:
   Validate file size (non-image $\le 25\text{MB}$, video $\le 100\text{MB}$) $\to$ Transcode HEIC/AVIF to JPEG $\to$ Save to `workspace/user/` $\to$ Record in SQLite $\to$ Inject prompt section.
2. **Delivery & Physical Stat Gate**:
   Intercept any outgoing assistant response matching `sandbox://workspace/<path>`.
   Run physical `os.path.exists()` check. If missing, fail-fast with error: *Deliverable file does not exist on disk*.
3. **Library Dynamic Projection**:
   Queries `FileRecord` where `visibility == 'user'` and `trashed_at IS NULL`. Zero physical duplicate copies.

### 4.5 Layer 5: Agent Tools (`lca/agent/`)
- `readFile(path)`: Dispatches according to `ReadabilityTier`.
- `writeFile(path, content)`: Replaces/appends content directly into destination.
- `editFile(path, search, replace)`: Precise in-place modification.
- `trashFile(path)`: Moves target to `.trash/`.
- `listFiles(directoryPath)`: Scans filesystem within `~`.

---

## 5. Verification & Invariants Matrix (AP-02)

The implementation must pass the following 10 automated test suites before merging:

1. **INV-FS-01 (Upload Survival)**: Upload a file $\to$ restart agent runtime process $\to$ file persists in `workspace/user/`, index records intact, agent reads file content.
2. **INV-FS-02 (Compaction Immunity)**: Trigger context memory compaction $\to$ verify byte-for-byte SHA256 checksum of generated files in `workspace/` remains identical.
3. **INV-FS-03 (Write-in-Place)**: Instruct agent to generate a goal deliverable $\to$ verify file exists in `workspace/goals/<slug>/files/` and NO orphan copy exists in `/tmp` or `outputs/`.
4. **INV-FS-04 (Visibility Isolation)**: Inspect Library projection $\to$ files in `hidden_files/` and `user/` are NOT returned; files in `your_files/` and `goals/*/files/` ARE returned.
5. **INV-FS-05 (Physical Stat Delivery Gate)**: Agent outputs `![alt](sandbox://workspace/non_existent.pdf)` $\to$ Delivery gate intercepts and throws error, blocking false delivery claims.
6. **INV-FS-06 (Ephemeral Scratch Discipline)**: Write files to `/tmp` $\to$ restart $\to$ verify no P0 document maintains references to `/tmp`.
7. **INV-FS-07 (Soft Delete & Recovery)**: Delete deliverable $\to$ disappears from Library, appears in `.trash/` $\to$ invoke restore $\to$ file returns to exact original path with identical content.
8. **INV-FS-08 (30-Day Trash Expiration)**: Expire TTL on trash item $\to$ background cron physically unlinks expired blobs.
9. **INV-FS-09 (Index Reconstruction from Disk)**: Truncate SQLite `workspace_files` table $\to$ run `rebuild_index()` $\to$ all `FileRecord` entries reconstructed matching disk reality.
10. **INV-FS-10 (Cross-Turn Workspace Continuity)**: Run A generates PDF $\to$ Run B executes `listFiles('/mnt/data/your_files')` $\to$ Run B immediately sees and inspects the PDF without hallucinatory apologies.

---

## 6. Implementation Phasing Strategy

- **Phase 1: Contracts & Sandbox Mount Consolidation**:
  Implement `FileRecord`, refactor `LocalSandboxAdapter` to bind-mount `{assistant_home}/workspace/` to `/mnt/data`.
- **Phase 2: FileStore & Upload Pipeline Redirection**:
  Migrate storage from `traces/files/` to `workspace/user/`, integrate SQLite index.
- **Phase 3: Prompt Section & Delivery Gate**:
  Implement `FilesystemPromptSection`, update `CONSTITUTION.md`, implement `sandbox://` physical `stat` interceptor.
- **Phase 4: Trash System & Verification**:
  Implement `.trash/` recovery and execute the 10-point automated invariant test suite.
