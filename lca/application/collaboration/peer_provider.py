"""PeerProfileResolver and PeerAssistantMaterializer (ADR-0250).

Bridges RoleCard definitions from roles/ into typed PeerProfile instances
and materializes persistent AssistantHome workspaces under ~/.lca/assistants/.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.agent.role_library import FileRoleLibrary
from lca.contracts.models.collaboration.peer import PeerProfile
from lca.contracts.protocols.collaboration.casting.casting import (
    RoleCard,
    RoleNotFoundError,
)
from lca.infrastructure.path.locator import get_lca_home

_ARCH_TRIAD_ROLES: tuple[str, ...] = (
    "architecture/guanlan",
    "architecture/hengyue",
    "architecture/jingchuan",
)

_DEFAULT_ROLE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "architecture/guanlan": ("contracts", "adr_guard", "domain_boundary"),
    "architecture/hengyue": ("state_machine", "invariants", "reducer_guard"),
    "architecture/jingchuan": ("antipattern_audit", "adversarial_review", "code_hygiene"),
}


class PeerProfileResolver:
    """Resolves RoleCard definitions into typed PeerProfile models."""

    def __init__(
        self,
        role_library: FileRoleLibrary | None = None,
        base_home: Path | None = None,
    ) -> None:
        self._library = role_library or FileRoleLibrary()
        self._base_home = base_home or get_lca_home()

    def resolve(self, role_id: str) -> PeerProfile:
        """Resolve a specific role_id into a PeerProfile."""
        try:
            card = self._library.get(role_id)
        except RoleNotFoundError as exc:
            raise KeyError(f"Role not found: {role_id}") from exc

        peer_name_slug = role_id.split("/")[-1]
        peer_id = (
            f"arch_{peer_name_slug}" if not peer_name_slug.startswith("arch_") else peer_name_slug
        )
        home_path = self._base_home / "assistants" / peer_id
        capabilities = _DEFAULT_ROLE_CAPABILITIES.get(role_id, ("general_architecture",))

        # 职责简述从 summary 或 backstory 第一句提炼
        role_desc = card.summary or f"{card.title} · 系统架构专家"

        return PeerProfile(
            peer_id=peer_id,
            name=card.title,
            role=role_desc,
            description=card.summary or card.title,
            home_namespace=str(home_path),
            capabilities=capabilities,
        )

    def resolve_triad(self) -> tuple[PeerProfile, ...]:
        """Resolve the Architecture Triad (Guanlan, Hengyue, Jingchuan)."""
        return tuple(self.resolve(r_id) for r_id in _ARCH_TRIAD_ROLES)


def materialize_peer_assistant(
    profile: PeerProfile,
    role_card: RoleCard | None = None,
    library: FileRoleLibrary | None = None,
) -> Path:
    """Materializes a persistent AssistantHome directory for the given PeerProfile.

    Idempotent: if the directory and files already exist, preserves user customizations.
    """
    home_dir = Path(profile.home_namespace)
    home_dir.mkdir(parents=True, exist_ok=True)

    # 1. SOUL.md: 固化角色人设与专业法则
    soul_file = home_dir / "SOUL.md"
    if not soul_file.exists():
        backstory = ""
        if role_card is not None:
            backstory = role_card.backstory
        else:
            lib = library or FileRoleLibrary()
            # 尝试通过 peer_id 逆向查找或默认
            slug = profile.peer_id.removeprefix("arch_")
            try:
                card = lib.get(f"architecture/{slug}")
                backstory = card.backstory
            except Exception:
                backstory = (
                    f"# {profile.name} · {profile.role}\n\n第一性原理驱动的高级系统架构专家。"
                )
        soul_file.write_text(f"# SOUL of {profile.name}\n\n{backstory}\n", encoding="utf-8")

    # 2. USER.md: 用户偏好（初始为空或占位）
    user_file = home_dir / "USER.md"
    if not user_file.exists():
        user_file.write_text(
            "# USER Profile & Guidelines\n\n- 严守架构纪律与第一性原理。\n", encoding="utf-8"
        )

    # 3. AGENTS.md: 认知契约常驻提示
    agents_file = home_dir / "AGENTS.md"
    if not agents_file.exists():
        agents_file.write_text(
            f"# {profile.name} Coding & Review Guardrails\n\n"
            "- 严禁越权修改非管辖领域代码 (AP-01)\n"
            "- 任何架构不变量必须具备确定性自动化测试 (AP-02)\n"
            "- 保持单写原则与纯净依赖分层 (C1~C14)\n",
            encoding="utf-8",
        )

    # 4. meta.json: 结构化元数据 (SSOT)
    meta_file = home_dir / "meta.json"
    meta_payload = {
        "peer_id": profile.peer_id,
        "name": profile.name,
        "role": profile.role,
        "description": profile.description,
        "home_namespace": profile.home_namespace,
        "capabilities": list(profile.capabilities),
    }
    meta_file.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return home_dir
