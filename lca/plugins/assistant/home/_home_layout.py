"""AssistantHome 目录布局 + manifest schema + digest 校验（ADR-0187 §3 D2）。
# ADR-0203 §3.3: sha256_digest() 是 file-bytes streaming hash;canonical_digest 不适用。

本模块负责磁盘 SSOT 形状：

- 目录骨架：``{assistants_root}/{assistant_id}/`` 含配置面文件 + 占位子目录
- manifest.json 形态：``schema_version`` / ``digests`` / ``revision_seq`` /
  ``template_id`` / ``manifest_digest`` / ``created_at``
- digest 校验：重算磁盘文件 digest,与 manifest 比对(I-A3 fail-closed)

**职责单一**:本模块只做 Home 磁盘布局与 manifest 字段;Catalog 的
``create / get / list`` 业务逻辑在 ``catalog.py``。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from lca.contracts.atoms.ids.ids import utc_now_iso
from lca.contracts.observability.canonical_digest import canonical_digest
from lca.infrastructure.assistant.io import read_json, sha256_digest
from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout

__all__ = [
    "CONFIG_FACE_FILES",
    "DEFAULT_TEMPLATE_DIR_NAME",
    "DEFAULT_TEMPLATE_ID",
    "SCHEMA_VERSION",
    "SOUL_CORE_SECTIONS",
    "SOUL_SAFETY_SECTIONS",
    "TEMPLATE_REGISTRY",
    "AssistantAlreadyExistsError",
    "AssistantCatalogError",
    "AssistantDigestMismatchError",
    "HomePaths",
    "SoulValidationError",
    "build_manifest",
    "compute_digests",
    "known_template_ids",
    "load_manifest",
    "render_default_template",
    "render_template",
    "scaffold_subdirs",
    "sha256_digest",
    "write_manifest",
    "write_revision_snapshot",
]


# ── 常量 ─────────────────────────────────────────────────────────────

DEFAULT_TEMPLATE_ID: str = "assistant.default"
DEFAULT_TEMPLATE_DIR_NAME: str = "assistant_default"
SCHEMA_VERSION: int = 1

# 配置面参与 manifest digest 的文件清单(MEMORY.md / memory/ 不在列:I-A13)
# plan.yaml 是 per-agent plan/prompt 覆盖(ADR-0242 D10),进 digest:
# 修改 plan.yaml ⇒ manifest_digest 变化 ⇒ (assistant_id, manifest_digest)
# 缓存键变化 ⇒ 下一 run 重新编译(I-B10)。
CONFIG_FACE_FILES: tuple[str, ...] = (
    "profile.json",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "goals.yaml",
    "grants.yaml",
    "tools.yaml",
    "plan.yaml",
)

# Home 占位子目录(空目录占位)
_HOME_SUBDIRS: tuple[str, ...] = (
    "skills",
    "tools",
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


class AssistantDigestMismatchError(AssistantCatalogError):
    """manifest 配置面 digest 与磁盘文件 digest 不一致(I-A3 fail-closed)。

    触发场景:resolve 时重算文件 digest,与 ``manifest.json.digests`` 比对
    不匹配;禁止「告警后放行」,必须抛本异常由调用方决定拒绝策略。
    """


class AssistantAlreadyExistsError(AssistantCatalogError):
    """``create`` 时 ``assistant_id`` 已存在。"""


# SOUL 完整度校验的四个核心语义段（ADR-0242 D1 / 附录 C）。
# 安全边界 / 记忆规则 / 错误处理 / 红线四段由模板预置，向导只确认，不强制手写。
SOUL_CORE_SECTIONS: tuple[str, ...] = (
    "## 🧠 身份",
    "## 🎭 性格",
    "## 🛠 能力",
    "## 🗣 语气",
)

# 四核心段的语义名（去 emoji 后的规范名）。校验时按语义匹配而非字节精确匹配：
# 接受 "## 身份"、"### 🧠身份"、"## 🛠️ 能力"（变体选择符）等写法。业界规范
# （OpenAI GPTs / Claude Projects 均为 freeform）：normalize 后验语义，不卡格式。
SOUL_CORE_SECTION_NAMES: tuple[str, ...] = ("身份", "性格", "能力", "语气")


def normalize_soul_section_header(line: str) -> str:
    """归一化 SOUL 语义段标题行，便于语义匹配。

    去掉：markdown 标题符号（#）、emoji（含变体选择符 U+FE0F、ZWJ U+200D、
    肤色修饰符）、首尾空白。返回纯语义文本，如 "## 🧠 身份" -> "身份"。
    """
    text = line.strip()
    # 去掉行首的 # 号（支持 ## / ### 等）
    text = text.lstrip("#").strip()
    # 去掉 emoji 及相关不可见修饰符
    kept: list[str] = []
    for ch in text:
        cp = ord(ch)
        if (
            0x1F000 <= cp <= 0x1FAFF  # emoji 主区
            or 0x2600 <= cp <= 0x27BF  # 杂项符号/装饰
            or cp in (0xFE0F, 0x200D)  # 变体选择符 / 零宽连接符
            or 0x1F3FB <= cp <= 0x1F3FF  # 肤色修饰符
        ):
            continue
        kept.append(ch)
    return "".join(kept).strip()


def find_missing_soul_sections(soul: str) -> tuple[str, ...]:
    """按语义名检查 SOUL 缺失的核心段，返回缺失的语义名。"""
    present: set[str] = set()
    for line in soul.splitlines():
        norm = normalize_soul_section_header(line)
        if norm in SOUL_CORE_SECTION_NAMES:
            present.add(norm)
    return tuple(n for n in SOUL_CORE_SECTION_NAMES if n not in present)


# 模板预置的四个平台保底安全段（ADR-0242 附录 C）。revise 提交缺失时由
# Catalog 从当前文件 / 模板合并补回；修改其内容是敏感操作，需用户确认。
# 唯一词表：catalog revise 合并与 self-manage 工具确认门都从这里 import。
SOUL_SAFETY_SECTIONS: tuple[str, ...] = (
    "## 🔒 安全边界",
    "## 💾 记忆规则",
    "## ⚠️ 错误处理",
    "## 🚫 红线",
)


class SoulValidationError(AssistantCatalogError):
    """``catalog.create`` 的 SOUL 完整度校验失败（fail-closed，ADR-0242 I-B2）。

    消息必须告诉调用方（LLM）具体缺哪一段 / 长度不足，便于继续对齐。
    """


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
    manifest_digest = canonical_digest(digests, length=64, prefix="sha256:")
    return {
        "schema_version": SCHEMA_VERSION,
        "assistant_id": assistant_id,
        "template_id": template_id,
        "revision_seq": revision_seq,
        "digests": digests,
        "manifest_digest": manifest_digest,
        "created_at": created_at or utc_now_iso(),
    }


def write_manifest(home: Path, manifest: dict[str, object]) -> None:
    """manifest 写盘:UTF-8 + 缩进 + sort_keys(可读 + 稳定)。"""
    (home / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_revision_snapshot(
    home: Path,
    revision_seq: int,
    manifest: Mapping[str, object],
) -> None:
    """把修订后的 manifest 快照写入 ``revisions/{revision_seq}.json``（ADR-0242 D6）。

    配置面每次变更（``revise_profile`` / ``reimport`` / skill 删除）都必须留下
    快照，供回滚与审计。manifest 中的 ``digests`` 是配置面文件摘要，快照按
    变更时刻的 manifest 原文保存；``files`` 键额外保存变更时刻配置面文件的
    全文（磁盘上存在的 ``CONFIG_FACE_FILES``），使回滚可以恢复内容而不仅是
    校验 digest。revision 0 是 create 写入的出生状态基线。
    """
    files: dict[str, str] = {}
    for name in CONFIG_FACE_FILES:
        path = home / name
        if path.is_file():
            files[name] = path.read_text(encoding="utf-8")
    snapshot: dict[str, object] = dict(manifest)
    snapshot["files"] = files
    revisions_dir = home / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    (revisions_dir / f"{revision_seq}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
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
        manifest = read_json(manifest_path)
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

# 模板注册表：template_id → templates/ 下的目录名（ADR-0187 §3 D11 +
# D12 对话创建的选项面）。新增角色模板 = 数据扩展；catalog.create 仅接受
# 本表内的 template_id（未知 ⇒ 4xx，防拼写错误静默落成 default）。
TEMPLATE_REGISTRY: dict[str, str] = {
    "assistant.default": "assistant_default",
    "assistant.research": "assistant_research",
    "assistant.writing": "assistant_writing",
    "assistant.coding": "assistant_coding",
    "assistant.translation": "assistant_translation",
    "assistant.daily": "assistant_daily",
}


def known_template_ids() -> tuple[str, ...]:
    """已登记 template_id 的稳定排序视图（选项菜单与错误信息用）。"""
    return tuple(sorted(TEMPLATE_REGISTRY))


def _templates_root() -> Path:
    """模板根目录（``lca/plugins/assistant/templates/``）：data 与插件 module 同级。"""
    return Path(__file__).resolve().parent.parent / "templates"


def _template_dir(template_id: str = DEFAULT_TEMPLATE_ID) -> Path:
    """解析 template_id 对应的模板目录路径。

    Failure：未登记的 template_id ⇒ ``AssistantCatalogError``（4xx 语义，
    由调用方决定状态码；不回落 default）。
    """
    dir_name = TEMPLATE_REGISTRY.get(template_id)
    if dir_name is None:
        raise AssistantCatalogError(
            f"未知 template_id={template_id!r};已登记: {', '.join(known_template_ids())}"
        )
    return _templates_root() / dir_name


@dataclass(frozen=True)
class TemplateRender:
    """模板字段替换结果。"""

    files: dict[str, str] = field(default_factory=dict)
    """{相对路径: 文本内容};相对根 = AssistantHome。"""


_TEMPLATE_PLACEHOLDER_DEFAULTS: dict[str, str] = {
    "{{ locale }}": "zh-CN",
    "{{ role }}": "",
    "{{ capabilities }}": "",
    "{{ boundaries }}": "",
    "{{ tone }}": "",
    "{{ emoji_style }}": "",
    "{{ tech_style }}": "",
}
"""SOUL 模板占位符默认值（ADR-0242 D9/PR-8）。

``locale`` 默认 zh-CN（模板 profile.json 同值）；其余占位符由创建向导经
``soul`` 覆盖填充，裸创建时替换为空串，避免字面 mustache 标签进入 SOUL。
"""


def _substitute_template_placeholders(text: str) -> str:
    """替换模板中已登记的额外占位符；未出现的占位符原样不动。"""
    for placeholder, value in _TEMPLATE_PLACEHOLDER_DEFAULTS.items():
        text = text.replace(placeholder, value)
    return text


def render_template(template_id: str, *, name: str, description: str) -> TemplateRender:
    """物化指定模板:替换 ``{{ name }}`` / ``{{ description }}`` 占位。

    同时替换 SOUL 模板的 ``{{ locale }}``（默认 ``zh-CN``）与
    ``{{ role }}`` / ``{{ capabilities }}`` / ``{{ boundaries }}`` /
    ``{{ tone }}`` / ``{{ emoji_style }}`` / ``{{ tech_style }}``
    （默认空串，避免字面 mustache 标签进入 BACKSTORY；ADR-0242 D9/PR-8）。

    不复制文件目录本身;只生成需要写入 Home 的 file payload 字典。
    模板目录由 :func:`_template_dir` 解析,**不**走 ``os.environ``。

    Failure：未登记 template_id / 模板目录缺失 ⇒ ``AssistantCatalogError``。
    """
    tpl_dir = _template_dir(template_id)
    if not tpl_dir.is_dir():
        raise AssistantCatalogError(f"template 目录不存在: {tpl_dir}")

    files: dict[str, str] = {}
    for entry in CONFIG_FACE_FILES:
        src = tpl_dir / entry
        text = src.read_text(encoding="utf-8")
        text = text.replace("{{ name }}", name).replace("{{ description }}", description)
        text = _substitute_template_placeholders(text)
        files[entry] = text

    # BOOTSTRAP.md 创建时存在;引导式创建（带 seed_user_md）完成流删除并发 EP。
    bootstrap_src = tpl_dir / _BOOTSTRAP_FILE
    if bootstrap_src.is_file():
        files[_BOOTSTRAP_FILE] = bootstrap_src.read_text(encoding="utf-8")

    # 其余常驻文件是活备忘，不进配置面摘要。投影文件等第一次写入再出现。
    files.update(_scaffold_standing_notes(name=name, description=description))

    return TemplateRender(files=files)


def _scaffold_standing_notes(*, name: str = "", description: str = "") -> dict[str, str]:
    """Load standing files that are neither config face nor the projection.

    A quirk edit must not change ``manifest_digest``. ``MEMORY.md`` stays out
    because the projection replaces that file, and an empty copy would look
    like a record store.
    """

    layout = packaged_layout()
    skip = set(CONFIG_FACE_FILES) | {layout.projection_file}
    notes: dict[str, str] = {}
    for entry in layout.standing_files:
        if entry in skip:
            continue
        src = _templates_root() / entry
        if not src.is_file():
            raise AssistantCatalogError(f"常驻文件模板缺失: {entry}")
        text = src.read_text(encoding="utf-8")
        if name:
            text = text.replace("{{ name }}", name)
        if description:
            text = text.replace("{{ description }}", description)
        notes[entry] = text
    return notes


def render_default_template(*, name: str, description: str) -> TemplateRender:
    """``assistant.default`` 模板的渲染入口（等价 ``render_template(DEFAULT_TEMPLATE_ID, ...)``）。"""
    return render_template(DEFAULT_TEMPLATE_ID, name=name, description=description)


def write_home_files(home: Path, files: Mapping[str, str]) -> None:
    """把 file payload 字典写到 Home(一次性);已存在抛 AssistantAlreadyExistsError。"""
    if home.exists():
        raise AssistantAlreadyExistsError(f"assistant home 已存在: {home}")
    home.mkdir(parents=True, exist_ok=False)
    for rel, content in files.items():
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    scaffold_subdirs(home)


def cleanup_home(home: Path) -> None:
    """best-effort 删除目录(create 失败时清理半成品)。"""
    if not home.exists():
        return
    import shutil

    shutil.rmtree(home, ignore_errors=True)


# ── helpers ──────────────────────────────────────────────────────────


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
