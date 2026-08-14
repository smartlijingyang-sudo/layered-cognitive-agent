"""操作技能库契约 —— SkillPackageStore / SkillImporter（ADR-0048）。

Role 回答「谁来做」（身份 + 团队分工，组队时刻绑定）；
Operational Skill 回答「怎么做」（纯操作知识，与身份无关，执行中按需拉取）。

内容与机制分离：技能包来自网络 import 后的本地缓存（默认 ``~/.lca/skills``），
不进 ``lca`` 包。与 ``SkillRouter``（Prompt 模板路由，``cognition.py``）语义不同。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Guest mount prefix under SANDBOX_MOUNT_ROOT (_skills/<skill_id>/…).
SANDBOX_SKILL_MOUNT_PREFIX: str = "_skills"

# Import / IO caps (gateway-side enforcement).
SKILL_MAX_ZIP_BYTES: int = 20 * 1024 * 1024
SKILL_MAX_RESOURCE_BYTES: int = 5 * 1024 * 1024
SKILL_MAX_RESOURCES: int = 200
SKILL_MAX_CONTENT_CHARS: int = 512_000


class SkillNotFoundError(ValueError):
    """skill_id 不存在于已安装技能库。"""


class SkillImportError(ValueError):
    """技能包下载 / 解析 / 校验失败。"""


@dataclass(frozen=True)
class SkillIndexEntry:
    """精简索引 —— 供 search / activate 选择，不含全文。"""

    skill_id: str
    name: str
    summary: str
    source_url: str = ""
    version: str = ""


@dataclass(frozen=True)
class SkillPackage:
    """已安装技能包 —— 纯操作知识 + 可选资源索引，无人格字段。"""

    skill_id: str
    name: str
    summary: str
    content: str  # SKILL.md 正文（frontmatter 已剥离）
    resource_paths: tuple[str, ...]
    source_url: str
    content_hash: str
    version: str = ""


@dataclass(frozen=True)
class SkillSearchResult:
    """Market 或本地检索结果页。"""

    items: tuple[SkillIndexEntry, ...]
    total: int
    page: int
    page_size: int


class SkillPackageStore(Protocol):
    """已安装技能库：list / get / 读资源 / 取挂载字节。"""

    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        """本地已安装技能索引（skill_id 升序）。"""
        ...

    def get(self, skill_id: str) -> SkillPackage:
        """按 skill_id 取完整包；未知 id 抛 SkillNotFoundError。"""
        ...

    def read_resource(self, skill_id: str, rel_path: str) -> str:
        """读取包内文本资源；路径必须在 resource_paths 白名单内。"""
        ...

    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        """返回 skill 全部资源相对路径 → bytes，供沙箱挂载。"""
        ...


class SkillImporter(Protocol):
    """从 Market / URL / GitHub 拉取技能包并 materialize 到 SkillPackageStore。"""

    async def search_market(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> SkillSearchResult:
        """检索 marketplace；无 token 时可降级为仅搜本地已安装。"""
        ...

    async def import_from_market(self, identifier: str) -> SkillPackage:
        """从 LobeHub Market 下载 ZIP 并安装。"""
        ...

    async def import_from_url(self, url: str, *, kind: str = "auto") -> SkillPackage:
        """从 URL 导入：lobehub skill 链接 / GitHub / ZIP / 裸 SKILL.md。"""
        ...
