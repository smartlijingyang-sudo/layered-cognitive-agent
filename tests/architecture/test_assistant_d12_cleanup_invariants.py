"""ADR-0242 D12 清理验收的架构回归测试（PR-0 防复发）。

PR-0 承诺的架构测试（``find lca -name "_home_layout.py"`` 只剩一份、
assistant 域无 IDENTITY 残留、空壳包删除、evolve 复用 overlay 回执）
此前没有落地；本文件把 D12 的验收标准变成 CI 门禁。
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LCA = REPO / "lca"

# 允许的说明性注释（IDENTITY.md 已删除，身份由 profile.json SSOT 拥有）。
_ALLOWED_IDENTITY_RESIDUE = (
    "IDENTITY.md 已删除",
    "IDENTITY 已删除",
)


class TestHomeLayoutSingleCopy:
    def test_only_one_home_layout_module(self) -> None:
        """D12:``_home_layout.py`` 必须只剩 ``lca/plugins/assistant/home/`` 一份。"""
        copies = sorted(LCA.rglob("_home_layout.py"))
        assert copies == [LCA / "plugins" / "assistant" / "home" / "_home_layout.py"], (
            f"期望唯一 _home_layout.py，实际 {copies}"
        )


class TestNoEmptyShellPackages:
    def test_assistant_catalog_and_tools_shells_removed(self) -> None:
        """D12:``lca/plugins/assistant/catalog/`` 与 ``tools/`` 空壳包必须不存在。"""
        for shell in ("catalog", "tools"):
            assert not (LCA / "plugins" / "assistant" / shell).exists(), (
                f"空壳包 lca/plugins/assistant/{shell}/ 应已删除"
            )


class TestNoIdentityResidue:
    def test_no_identity_md_reference_in_assistant_domain(self) -> None:
        """D12:assistant 域代码无 IDENTITY.md 残留（允许说明性注释）。

        扫描范围与 ADR-0242 D12 验收命令一致。
        """
        roots = (
            LCA / "plugins" / "assistant",
            LCA / "contracts" / "models" / "assistant",
            LCA / "contracts" / "protocols" / "assistant",
        )
        offenders: list[tuple[Path, str]] = []
        for root in roots:
            for path in root.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if "IDENTITY" not in line:
                        continue
                    if any(allowed in line for allowed in _ALLOWED_IDENTITY_RESIDUE):
                        continue
                    # FunctionalGroup.G1_IDENTITY 是枚举名，不是文件引用。
                    if "G1_IDENTITY" in line:
                        continue
                    offenders.append((path, f"{line_no}:{line.strip()}"))
        assert offenders == [], f"assistant 域存在 IDENTITY 残留：{offenders}"


class TestEvolveReusesOverlayReceipt:
    def test_evolve_does_not_define_skill_install_receipt(self) -> None:
        """D12:``evolve.py`` 不定义 ``SkillInstallReceipt``，必须复用 skill_overlay。"""
        from lca.contracts.protocols.assistant import evolve, skill_overlay

        assert hasattr(skill_overlay, "SkillInstallReceipt")
        # evolve 不自行定义同名类：要么 re-export，要么只引用不定义。
        assert not hasattr(evolve, "SkillInstallReceipt") or (
            evolve.SkillInstallReceipt is skill_overlay.SkillInstallReceipt
        )
