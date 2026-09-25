"""Patch: skill_picker_test — update AgentPickerStep tests for LCA onboarding.

ADR-0252 D7：``AgentPickerStep`` 现在调 ``installOnboardingAgent`` 并加载技能
目录。同步测试 mock 与断言（``fetchOnboardingSkillCapabilities`` 返回空技能，
``installOnboardingAgent`` 取代 ``installMarketplaceAgents``）。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="skill_picker_test",
    description="Update AgentPickerStep unit tests for LCA onboarding flow",
    files=("src/routes/onboarding/features/AgentPickerStep/index.test.tsx",),
    risk="low",
    category="onboarding",
    depends_on=("skill_picker",),
    why="Keep AgentPickerStep tests green after switching to installOnboardingAgent",
    technical_detail=(
        "Mock fetchOnboardingSkillCapabilities to return [] and "
        "installOnboardingAgent in place of installMarketplaceAgents."
    ),
    verify_file="src/routes/onboarding/features/AgentPickerStep/index.test.tsx",
    verify_marker="LCA skill_picker_test",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/routes/onboarding/features/AgentPickerStep/index.test.tsx"
    if ctx.has_marker(rel, "LCA skill_picker_test"):
        return False

    text = ctx.read(rel)

    # 0) Marker comment for idempotency.
    anchor_top = """import {
  type AgentTemplate,
  MarketplaceCategory,
} from '@lobechat/builtin-tool-web-onboarding/agentMarketplace';"""
    repl_top = """// LCA skill_picker_test (ADR-0252 D7): AgentPickerStep uses installOnboardingAgent.
import {
  type AgentTemplate,
  MarketplaceCategory,
} from '@lobechat/builtin-tool-web-onboarding/agentMarketplace';"""
    if anchor_top not in text:
        raise AssertionError("skill_picker_test: top import anchor not found")
    text = text.replace(anchor_top, repl_top, 1)

    # 1) Mocked service function.
    anchor_fn = """const installMarketplaceAgents = vi.fn().mockResolvedValue({
  installedAgentIds: [],
  skippedAgentIds: [],
  summaries: [],
});"""
    repl_fn = """const installOnboardingAgent = vi.fn().mockResolvedValue({
  assistantId: 'asst_1',
});"""
    if anchor_fn not in text:
        raise AssertionError("skill_picker_test: service mock fn anchor not found")
    text = text.replace(anchor_fn, repl_fn, 1)

    # 2) agentMarketplace mock gains the skill fetcher.
    anchor_am = """vi.mock('@/services/agentMarketplace', () => ({
  fetchOnboardingAgentTemplates: vi.fn(),
}));"""
    repl_am = """vi.mock('@/services/agentMarketplace', () => ({
  fetchOnboardingAgentTemplates: vi.fn(),
  fetchOnboardingSkillCapabilities: vi.fn().mockResolvedValue([]),
}));"""
    if anchor_am not in text:
        raise AssertionError("skill_picker_test: agentMarketplace mock anchor not found")
    text = text.replace(anchor_am, repl_am, 1)

    # 3) Service module mock.
    anchor_sm = """vi.mock('@/services/installMarketplaceAgents', () => ({
  installMarketplaceAgents: (...args: unknown[]) => installMarketplaceAgents(...args),
}));"""
    repl_sm = """vi.mock('@/services/installOnboardingAgent', () => ({
  installOnboardingAgent: (...args: unknown[]) => installOnboardingAgent(...args),
}));"""
    if anchor_sm not in text:
        raise AssertionError("skill_picker_test: service module mock anchor not found")
    text = text.replace(anchor_sm, repl_sm, 1)

    # 4) beforeEach clear.
    anchor_clear = """  installMarketplaceAgents.mockClear();"""
    repl_clear = """  installOnboardingAgent.mockClear();"""
    if anchor_clear not in text:
        raise AssertionError("skill_picker_test: mockClear anchor not found")
    text = text.replace(anchor_clear, repl_clear, 1)

    # 5) Continue assertion.
    anchor_continue = """    expect(installMarketplaceAgents).toHaveBeenCalledWith(['t1']);"""
    repl_continue = """    expect(installOnboardingAgent).toHaveBeenCalledWith(
      expect.objectContaining({
        fromRole: 't1',
        name: 'Code Reviewer',
        initialSkills: [],
        clientId: expect.any(String),
      }),
    );"""
    if anchor_continue not in text:
        raise AssertionError("skill_picker_test: continue assertion anchor not found")
    text = text.replace(anchor_continue, repl_continue, 1)

    # 6) Skip assertion.
    anchor_skip = """    expect(installMarketplaceAgents).not.toHaveBeenCalled();"""
    repl_skip = """    expect(installOnboardingAgent).not.toHaveBeenCalled();"""
    if anchor_skip not in text:
        raise AssertionError("skill_picker_test: skip assertion anchor not found")
    text = text.replace(anchor_skip, repl_skip, 1)

    ctx.write(rel, text)
    return True