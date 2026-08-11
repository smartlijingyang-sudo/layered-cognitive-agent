"""Sandbox execution contracts (ADR-0044).

Provider-neutral result shapes for code sandboxes. No I/O — pure data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Default wall-clock budget for a single sandbox invocation (seconds).
DEFAULT_SANDBOX_TIMEOUT_S: int = 60

# Soft cap for stdout/stderr previews embedded in Observation.payload / ToolInvoked.
SANDBOX_PREVIEW_CHAR_LIMIT: int = 8000

# Guest path where tool-supplied attachment bytes are mounted (all backends).
SANDBOX_MOUNT_ROOT: str = "/mnt/data"

# Relative to SANDBOX_MOUNT_ROOT: guest dir whose files are collected as downloadable products.
# Full path: /mnt/data/outputs — files written elsewhere are not harvested (ADR-0046).
SANDBOX_OUTPUT_SUBDIR: str = "outputs"

# Caps for harvested generated_files (over-limit files skipped with diagnostics; run still succeeds).
SANDBOX_MAX_GENERATED_FILES: int = 20
SANDBOX_MAX_GENERATED_FILE_BYTES: int = 20 * 1024 * 1024

# Production Onlyboxes pythonExec image baseline (deploy/onlyboxes/requirements-python.txt).
# Ops contract for tool descriptions / prompts — not enforced by Sandbox Protocol.
SANDBOX_PREINSTALLED_PYTHON_PACKAGES: tuple[str, ...] = (
    # data science / ML
    "pandas",
    "numpy",
    "scipy",
    "scikit-learn",
    # visualization
    "matplotlib",
    "seaborn",
    "plotly",
    # image / media
    "pillow",
    "opencv-python-headless",
    # spreadsheet / document I/O
    "openpyxl",
    "xlsxwriter",
    "xlrd",
    "python-docx",
    "reportlab",
    "fpdf2",
    "pypdf",
    "olefile",
    "markitdown",
    # data processing / config
    "pyyaml",
    "toml",
    "python-dotenv",
    "tabulate",
    # network
    "requests",
    "aiofiles",
    "anyio",
    # web / server
    "fastapi",
    "uvicorn",
    "pydantic",
    # testing
    "pytest",
)


@dataclass(frozen=True)
class SandboxFile:
    """One file produced (or mounted) by a sandbox run — bytes + display metadata."""

    name: str
    mime_type: str
    data: bytes


class SandboxErrorKind(str, Enum):
    """Structured failure classification for sandbox observations (ADR-0050)."""

    NONE = "none"
    MOUNT = "mount"
    USER_CODE = "user_code"
    TIMEOUT = "timeout"
    INFRA = "infra"


@dataclass(frozen=True)
class MountEntry:
    """One attachment staged under ``SANDBOX_MOUNT_ROOT``."""

    path: str
    name: str
    size_bytes: int
    attachment_id: str


@dataclass(frozen=True)
class MountManifest:
    """Run-level mount contract — expected guest paths after ``ensure_ready``."""

    entries: tuple[MountEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SandboxResult:
    """Terminal outcome of ``Sandbox.run`` (after streaming deltas have been emitted)."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    success: bool = True
    generated_files: tuple[SandboxFile, ...] = field(default_factory=tuple)
    error: str = ""


@dataclass(frozen=True)
class SandboxExecResult:
    """Structured sandbox outcome for agent tools (extends terminal ``SandboxResult``)."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    success: bool = True
    generated_files: tuple[SandboxFile, ...] = field(default_factory=tuple)
    error: str = ""
    error_kind: SandboxErrorKind = SandboxErrorKind.NONE
    error_summary: str = ""
    suggested_fix: str = ""
    mount_manifest: MountManifest = field(default_factory=MountManifest)
    environment_ready: bool = False
    partial: bool = False
    failed_at_line: int | None = None
    inspect_profile: dict[str, Any] | None = None


@dataclass(frozen=True)
class SessionConfig:
    """创建沙箱会话的配置。

    会话是有状态的执行环境——容器跨调用存活，变量/安装包/文件系统均保持。
    生命周期应绑定 agent run：run 结束即销毁。
    """

    timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S
    files: dict[str, bytes] = field(default_factory=dict)
    python_version: str = "3.11"


@dataclass(frozen=True)
class SessionInfo:
    """已创建的沙箱会话元信息。"""

    session_id: str
    container_id: str = ""
    status: str = "active"
