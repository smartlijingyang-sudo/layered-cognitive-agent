"""create_assistant_skill 工具：支持 source_url 网络源安装（ADR-0247 流程测试补强）。

模型经该工具把外部 skill 安装到本助理 Home 的 skills/ 目录，安装路径经
``assistant.skill_overlay`` 的 0048 拉取 + 0067 三闸校验（verified 后才落盘）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.infrastructure.tools.assistant.create_skill_tool import AssistantCreateSkillTool


class _FakeOverlay:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, str]] = []

    async def install(
        self,
        assistant_id: str,
        source: object,
        *,
        actor: str = "system",
    ) -> SimpleNamespace:
        self.calls.append((assistant_id, source, actor))
        return SimpleNamespace(
            skill_id="product-manager-toolkit",
            install_path=f"/home/{assistant_id}/skills/product-manager-toolkit",
        )


@pytest.mark.asyncio
async def test_install_from_source_url() -> None:
    overlay = _FakeOverlay()
    tool = AssistantCreateSkillTool(overlay=overlay, assistant_id="asst_1")  # type: ignore[arg-type]

    obs = await tool.execute({"source_url": "https://example.com/skills/product-manager.zip"})

    assert obs.success is True
    assert obs.payload["skill_id"] == "product-manager-toolkit"
    assert len(overlay.calls) == 1
    assistant_id, source, actor = overlay.calls[0]
    assert assistant_id == "asst_1"
    assert getattr(source, "url", "") == "https://example.com/skills/product-manager.zip"
    assert actor == "agent"


@pytest.mark.asyncio
async def test_source_url_mutually_exclusive_with_skill_md() -> None:
    overlay = _FakeOverlay()
    tool = AssistantCreateSkillTool(overlay=overlay, assistant_id="asst_1")  # type: ignore[arg-type]

    obs = await tool.execute({"source_url": "https://example.com/s.zip", "skill_md": "# x"})

    assert obs.success is False
    assert overlay.calls == []


@pytest.mark.asyncio
async def test_requires_one_source() -> None:
    overlay = _FakeOverlay()
    tool = AssistantCreateSkillTool(overlay=overlay, assistant_id="asst_1")  # type: ignore[arg-type]

    obs = await tool.execute({})
    assert obs.success is False
    assert "至少提供一个" in (obs.error or "")


@pytest.mark.asyncio
async def test_install_from_skill_md_still_works() -> None:
    overlay = _FakeOverlay()
    tool = AssistantCreateSkillTool(overlay=overlay, assistant_id="asst_1")  # type: ignore[arg-type]

    obs = await tool.execute({"skill_md": "---\nname: my-skill\n---\n# My Skill\n"})

    assert obs.success is True
    assert len(overlay.calls) == 1
    _, source, _actor = overlay.calls[0]
    assert getattr(source, "local_path", "") != ""
