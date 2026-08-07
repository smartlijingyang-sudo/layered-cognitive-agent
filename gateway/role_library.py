"""角色库文件实现 —— 扫描 AGENCY_ROLES_DIR 下的 Markdown 角色卡（ADR-0042）。

内容与机制分离：角色卡是纯数据内容包（默认随仓库 ``roles/`` 分发，可经
``AGENCY_ROLES_DIR`` 整体替换），本网关模块只负责解析，不进入 ``lca`` 包。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from lca.contracts.protocols.casting import (
    CastingError,
    RoleCard,
    RoleIndexEntry,
    RoleLibrary,
    RoleNotFoundError,
)

AGENCY_ROLES_DIR_ENV = "AGENCY_ROLES_DIR"
"""角色库目录环境变量；未设置时使用仓库内置 roles/。"""

_DEFAULT_ROLES_DIR = Path(__file__).resolve().parent.parent / "roles"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def resolve_roles_dir() -> Path:
    """角色库目录：AGENCY_ROLES_DIR 优先，缺省用仓库内置 roles/。"""
    configured = os.getenv(AGENCY_ROLES_DIR_ENV)
    return Path(configured).expanduser() if configured else _DEFAULT_ROLES_DIR


class FileRoleLibrary(RoleLibrary):
    """扫描目录中「带 name frontmatter 的 .md」为角色卡。

    role_id = 相对路径去扩展名（如 ``product/product-manager``），顶层目录
    名即 department。无 frontmatter 或缺 name 的 .md（如 README）跳过。
    """

    def __init__(self, root: Path | None = None) -> None:
        resolved = root if root is not None else resolve_roles_dir()
        if not resolved.is_dir():
            raise CastingError(f"角色库目录不存在：{resolved}（可用 {AGENCY_ROLES_DIR_ENV} 指定）")
        self._cards = self._scan(resolved)
        if not self._cards:
            raise CastingError(f"角色库为空：{resolved} 中没有可用的角色卡")

    def index(self) -> tuple[RoleIndexEntry, ...]:
        return tuple(
            RoleIndexEntry(
                role_id=card.role_id,
                title=card.title,
                department=card.department,
                summary=card.summary,
            )
            for card in sorted(self._cards.values(), key=lambda c: c.role_id)
        )

    def get(self, role_id: str) -> RoleCard:
        card = self._cards.get(role_id)
        if card is None:
            raise RoleNotFoundError(f"角色库中不存在 role_id：{role_id}")
        return card

    def _scan(self, root: Path) -> dict[str, RoleCard]:
        cards: dict[str, RoleCard] = {}
        for path in sorted(root.rglob("*.md")):
            card = self._parse_card(root, path)
            if card is not None:
                cards[card.role_id] = card
        return cards

    def _parse_card(self, root: Path, path: Path) -> RoleCard | None:
        text = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(text)
        if match is None:
            return None
        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
        if not isinstance(meta, dict) or not meta.get("name"):
            return None
        role_id = path.relative_to(root).with_suffix("").as_posix()
        department = role_id.split("/", 1)[0] if "/" in role_id else ""
        return RoleCard(
            role_id=role_id,
            title=str(meta["name"]).strip(),
            department=department,
            summary=str(meta.get("description", "")).strip(),
            backstory=match.group(2).strip(),
        )
