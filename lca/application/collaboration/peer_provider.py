"""PeerProfileResolver and PeerAssistantMaterializer (ADR-0250).

Bridges RoleCard definitions from roles/ into typed PeerProfile instances
and materializes persistent AssistantHome workspaces under ~/.lca/assistants/.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from lca.agent.role_library import FileRoleLibrary
from lca.contracts.models.collaboration.peer import PeerProfile
from lca.contracts.protocols.collaboration.casting.casting import (
    RoleCard,
    RoleNotFoundError,
)
from lca.infrastructure.path.locator import get_lca_home

_logger = logging.getLogger(__name__)

_DEFAULT_ARCHITECTURE_TRIAD = (
    "architecture/guanlan",
    "architecture/hengyue",
    "architecture/jingchuan",
)


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

        # 保持 architecture 命名空间与 arch_ 规范兼容，其他部门使用标准命名
        if card.department == "architecture":
            peer_name_slug = role_id.split("/")[-1]
            peer_id = (
                f"arch_{peer_name_slug}"
                if not peer_name_slug.startswith("arch_")
                else peer_name_slug
            )
        else:
            peer_id = role_id.replace("/", "_")

        home_path = self._base_home / "assistants" / peer_id
        capabilities = self._resolve_capabilities(card)

        # 职责简述从 summary 或 backstory 第一句提炼
        role_desc = card.summary or f"{card.title} · {card.department.title()}专家"

        return PeerProfile(
            peer_id=peer_id,
            name=card.title,
            role=role_desc,
            description=card.summary or card.title,
            home_namespace=str(home_path),
            capabilities=capabilities,
        )

    def resolve_team(self, role_ids: Sequence[str]) -> tuple[PeerProfile, ...]:
        """Resolve a team of roles by their role_ids."""
        return tuple(self.resolve(r_id) for r_id in role_ids)

    def resolve_triad(self) -> tuple[PeerProfile, ...]:
        """Resolve the Architecture Triad (backward compatible helper)."""
        return self.resolve_team(_DEFAULT_ARCHITECTURE_TRIAD)

    def _resolve_capabilities(self, card: RoleCard) -> tuple[str, ...]:
        # 从角色卡部门与概要自适应提取能力
        caps: list[str] = []
        if card.department:
            caps.append(f"{card.department}_domain")
        if "契约" in card.summary or "边界" in card.summary:
            caps.extend(["contracts", "adr_guard", "domain_boundary"])
        elif "状态机" in card.summary or "不变量" in card.summary:
            caps.extend(["state_machine", "invariants", "reducer_guard"])
        elif "审计" in card.summary or "反模式" in card.summary:
            caps.extend(["antipattern_audit", "adversarial_review", "code_hygiene"])
        else:
            caps.append("general_analysis")
        return tuple(dict.fromkeys(caps))


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
            found_card = None
            candidate_keys = [
                profile.peer_id,
                profile.peer_id.replace("_", "/"),
            ]
            if profile.peer_id.startswith("arch_"):
                candidate_keys.append(f"architecture/{profile.peer_id.removeprefix('arch_')}")
            for cand in candidate_keys:
                try:
                    found_card = lib.get(cand)
                    break
                except Exception as exc:
                    _logger.debug("Candidate key %s not found in library: %s", cand, exc)
                    continue

            if found_card is not None:
                backstory = found_card.backstory
            else:
                backstory = (
                    f"# {profile.name} · {profile.role}\n\n第一性原理驱动的高级领域专家。"
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
