"""AssistantHome 目录布局 + manifest schema + digest 校验（ADR-0187 §3 D2）。

本模块负责磁盘 SSOT 形状：

- 目录骨架：``{assistants_root}/{assistant_id}/`` 含配置面文件 + 占位子目录
- manifest.json 形态：``schema_version`` / ``digests`` / ``revision_seq`` /
  ``template_id`` / ``manifest_digest`` / ``created_at``
- digest 校验：重算磁盘文件 digest,与 manifest 比对(I-A3 fail-closed)

**职责单一**:本模块只做 Home 磁盘布局与 manifest 字段;Catalog 的
``create / get / list`` 业务逻辑在 ``catalog.py``。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "CONFIG_FACE_FILES",
    "DEFAULT_TEMPLATE_DIR_NAME",
    "DEFAULT_TEMPLATE_ID",
    "SCHEMA_VERSION",
    "AssistantAlreadyExists",
    "AssistantCatalogError",
    "AssistantDigestMismatch",
    "HomePaths",
    "build_manifest",
    "compute_digests",
    "load_manifest",
    "render_default_template",
    "scaffold_subdirs",
    "sha256_digest",
    "write_manifest",
]


# ── 常量 ─────────────────────────────────────────────────────────────

DEFAULT_TEMPLATE_ID: str = "assistant.default"
DEFAULT_TEMPLATE_DIR_NAME: str = "assistant_default"
SCHEMA_VERSION: int = 1

# 配置面参与 manifest digest 的文件清单(MEMORY.md / memory/ 不在列:I-A13)
CONFIG_FACE_FILES: tuple[str, ...] = (
    "profile.json",
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "AGENTS.md",
    "goals.yaml",
    "grants.yaml",
    "tools.yaml",
)

# Home 占位子目录(空目录占位)
_HOME_SUBDIRS: tuple[str, ...] = (
    "skills",
    "workspace",
    "memory",
    "routines",
    "revisions",
)

# 创建时存在;PR-7 完成流删除并发 EP
_BOOTSTRAP_FILE = "BOOTSTRAP.md"


# ── 异常 ──────────────────────────────────────────────────────────────


class AssistantCatalogError(RuntimeError):
    """Catalog 错误基类(4xx 语义;不静默回落)。"""


class AssistantDigestMismatch(AssistantCatalogError):  # noqa: N818
    """manifest 配置面 digest 与磁盘文件 digest 不一致(I-A3 fail-closed)。

    触发场景:resolve 时重算文件 digest,与 ``manifest.json.digests`` 比对
    不匹配;禁止「告警后放行」,必须抛本异常由调用方决定拒绝策略。
    """


class AssistantAlreadyExists(AssistantCatalogError):  # noqa: N818
    """``create`` 时 ``assistant_id`` 已存在。"""


# ── Home 路径集合 ────────────────────────────────────────────────────


@dataclass(frozen=True)
class HomePaths:
    """AssistantHome 的路径集合。"""

    root: Path
    """``{assistants_root}/{assistant_id}/``。"""

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def memory_md(self) -> Path:
        return self.root / "MEMORY.md"

    @property
    def bootstrap_md(self) -> Path:
        return self.root / _BOOTSTRAP_FILE


# ── digest 与 manifest ───────────────────────────────────────────────


def sha256_digest(path: Path) -> str:
    """计算文件的 ``sha256:<hex>`` 内容 digest。"""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def compute_digests(home: Path) -> dict[str, str]:
    """重算配置面文件 digest;文件缺失返回空字典(让校验步骤自然 fail)。"""
    digests: dict[str, str] = {}
    for name in CONFIG_FACE_FILES:
        path = home / name
        if path.is_file():
            digests[name] = sha256_digest(path)
    return digests


def build_manifest(
    *,
    assistant_id: str,
    template_id: str,
    revision_seq: int,
    home: Path,
    created_at: str | None = None,
    extra_digests: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """构造 manifest dict;manifest_digest 是 ``digests`` 序列化后的 sha256。

    ``extra_digests`` 合并进配置面 ``digests``(同名键以配置面重算值优先),
    供 skills 索引等非 ``CONFIG_FACE_FILES`` 的配置面条目进入
    manifest_digest 覆盖(digest SSOT 单点,ADR-0187 §3 D2)。
    """
    digests = dict(extra_digests or {})
    digests.update(compute_digests(home))
    canonical = json.dumps(digests, sort_keys=True).encode()
    manifest_digest = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    return {
        "schema_version": SCHEMA_VERSION,
        "assistant_id": assistant_id,
        "template_id": template_id,
        "revision_seq": revision_seq,
        "digests": digests,
        "manifest_digest": manifest_digest,
        "created_at": created_at or _utc_now_iso(),
    }


def write_manifest(home: Path, manifest: dict[str, object]) -> None:
    """manifest 写盘:UTF-8 + 缩进 + sort_keys(可读 + 稳定)。"""
    (home / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_manifest(home: Path, assistant_id: str) -> dict[str, object]:
    """读 manifest.json;字段校验失败抛 AssistantCatalogError。"""
    manifest_path = home / "manifest.json"
    if not home.is_dir():
        raise AssistantCatalogError(f"assistant home 不存在: {home}")
    if not manifest_path.is_file():
        raise AssistantCatalogError(f"assistant home 缺 manifest.json: {home}")
    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError) as exc:
        raise AssistantCatalogError(f"manifest.json 不可读: {home} ({exc})") from exc
    declared_id = manifest.get("assistant_id")
    if declared_id != assistant_id:
        raise AssistantCatalogError(
            f"manifest.assistant_id={declared_id!r} 与路径 id={assistant_id!r} 不匹配"
        )
    digests = manifest.get("digests")
    if not isinstance(digests, dict):
        raise AssistantCatalogError(f"manifest.digests 缺失或非 dict: {home}")
    return manifest


def diff_digests(declared: dict[str, str], actual: dict[str, str]) -> list[str]:
    """返回 declared digests 中与 actual 不一致的文件名列表(已排序)。"""
    return sorted(name for name in declared if name in actual and declared[name] != actual[name])


# ── 目录骨架 ────────────────────────────────────────────────────────


def scaffold_subdirs(home: Path) -> None:
    """创建 skills / workspace / memory / routines / revisions 占位空目录。"""
    for sub in _HOME_SUBDIRS:
        (home / sub).mkdir(parents=True, exist_ok=True)


# ── 模板渲染 ─────────────────────────────────────────────────────────


def _template_dir() -> Path:
    """返回默认模板目录(``assistant_default/``)的文件系统路径。

    模板是 data:与插件 module 同目录 ``templates/`` 子树,不打包成 module。
    """
    return Path(__file__).resolve().parent / "templates" / DEFAULT_TEMPLATE_DIR_NAME


@dataclass(frozen=True)
class TemplateRender:
    """模板字段替换结果。"""

    files: dict[str, str] = field(default_factory=dict)
    """{相对路径: 文本内容};相对根 = AssistantHome。"""


def render_default_template(*, name: str, description: str) -> TemplateRender:
    """物化模板:替换 ``{{ name }}`` / ``{{ description }}`` 占位。

    不复制文件目录本身;只生成需要写入 Home 的 file payload 字典。
    模板目录由 :func:`_template_dir` 解析,**不**走 ``os.environ``。
    """
    tpl_dir = _template_dir()
    if not tpl_dir.is_dir():
        raise AssistantCatalogError(f"default template 目录不存在: {tpl_dir}")

    files: dict[str, str] = {}
    for entry in CONFIG_FACE_FILES:
        src = tpl_dir / entry
        text = src.read_text(encoding="utf-8")
        text = text.replace("{{ name }}", name).replace("{{ description }}", description)
        files[entry] = text

    # BOOTSTRAP.md 在 PR-3 创建时存在;PR-7 完成流删除并发 EP。
    bootstrap_src = tpl_dir / _BOOTSTRAP_FILE
    if bootstrap_src.is_file():
        files[_BOOTSTRAP_FILE] = bootstrap_src.read_text(encoding="utf-8")

    return TemplateRender(files=files)


def write_home_files(home: Path, files: Mapping[str, str]) -> None:
    """把 file payload 字典写到 Home(一次性);已存在抛 AssistantAlreadyExists。"""
    if home.exists():
        raise AssistantAlreadyExists(f"assistant home 已存在: {home}")
    home.mkdir(parents=True, exist_ok=False)
    for rel, content in files.items():
        (home / rel).write_text(content, encoding="utf-8")
    scaffold_subdirs(home)


def cleanup_home(home: Path) -> None:
    """best-effort 删除目录(create 失败时清理半成品)。"""
    if not home.exists():
        return
    import shutil

    shutil.rmtree(home, ignore_errors=True)


# ── helpers ──────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, object]:
    """读取 JSON 文件;非 dict 抛 ValueError。"""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是 JSON object")
    return data


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def count_yaml_in(directory: Path) -> int:
    """统计目录下 YAML 文件数量(不含子目录);目录不存在返回 0。"""
    if not directory.is_dir():
        return 0
    return sum(
        1
        for child in directory.iterdir()
        if child.is_file() and child.suffix.lower() in {".yaml", ".yml"}
    )


def list_children_dirs(root: Path) -> Iterable[Path]:
    """按名字排序迭代 root 的直接子目录;root 不存在返回空迭代。"""
    if not root.is_dir():
        return ()
    return sorted(child for child in root.iterdir() if child.is_dir())
