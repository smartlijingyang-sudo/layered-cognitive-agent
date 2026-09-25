"""Patch: lca_presets — replace marketplace onboarding templates with LCA presets.

ADR-0252 D7：``AgentPickerStep`` 数据源换成 LCA ``/v1/onboarding/presets``
（角色卡 + 技能目录）。保留 ``fetchOnboardingAgentTemplates`` 的
``AgentTemplateFetcher`` 签名（SWR hook 不变），新增
``fetchOnboardingSkillCapabilities`` 供技能勾选步骤使用。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_NEW_SOURCE = """import {
  type AgentTemplate,
  type AgentTemplateFetcher,
  normalizeAgentTemplate,
  type RawAgentTemplate,
} from '@lobechat/builtin-tool-web-onboarding/agentMarketplace';

// LCA presets (ADR-0252 D7): role-card departments -> MarketplaceCategory slugs.
const DEPARTMENT_CATEGORY_MAP: Record<string, string> = {
  academic: 'learning-research',
  architecture: 'engineering',
  design: 'design-creative',
  engineering: 'engineering',
  finance: 'finance-legal',
  'game-development': 'creator-economy',
  gis: 'engineering',
  hr: 'people-hr',
  legal: 'finance-legal',
  marketing: 'marketing',
  'paid-media': 'marketing',
  product: 'product-management',
  'project-management': 'product-management',
  sales: 'sales-customer',
  security: 'engineering',
  'spatial-computing': 'engineering',
  specialized: 'operations',
  'supply-chain': 'operations',
  support: 'sales-customer',
  testing: 'engineering',
};
const DEFAULT_CATEGORY = 'product-management';

export interface LcaOnboardingPresets {
  roles: Array<{
    id: string;
    title: string;
    description: string;
    avatar?: string;
    category: string;
  }>;
  skills: Array<{ id: string; name: string; description: string }>;
}

const fetchLcaOnboardingPresets = async (): Promise<LcaOnboardingPresets> => {
  const response = await fetch('/lca-api/v1/onboarding/presets');
  if (!response.ok) throw new Error(`onboarding presets failed: ${response.status}`);
  return response.json();
};

export const fetchOnboardingSkillCapabilities = async (): Promise<
  LcaOnboardingPresets['skills']
> => {
  const presets = await fetchLcaOnboardingPresets();
  return presets.skills ?? [];
};

export const fetchOnboardingAgentTemplates: AgentTemplateFetcher = async () => {
  const presets = await fetchLcaOnboardingPresets();
  const templates: AgentTemplate[] = [];
  for (const role of presets.roles ?? []) {
    const category = DEPARTMENT_CATEGORY_MAP[role.category] || DEFAULT_CATEGORY;
    const normalized = normalizeAgentTemplate(
      {
        identifier: role.id,
        name: role.title,
        description: role.description,
        avatar: role.avatar,
      } as RawAgentTemplate,
      category,
    );
    if (normalized) templates.push(normalized);
  }
  return templates;
};
"""

meta = PatchMeta(
    name="lca_presets",
    description="Replace onboarding agent templates with LCA role-card presets",
    files=("src/services/agentMarketplace.ts",),
    risk="medium",
    category="onboarding",
    depends_on=(),
    why="ADR-0252 D7: AgentPickerStep reads LCA presets instead of the upstream marketplace",
    technical_detail=(
        "Full-file rewrite. Keeps fetchOnboardingAgentTemplates as "
        "AgentTemplateFetcher so useOnboardingAgentTemplates SWR stays intact; "
        "adds fetchOnboardingSkillCapabilities for the skill checkbox step."
    ),
    verify_file="src/services/agentMarketplace.ts",
    verify_marker="LCA presets",
)


def apply(ctx: PatchContext) -> bool:
    rel = "src/services/agentMarketplace.ts"
    if ctx.has_marker(rel, "LCA presets"):
        return False
    ctx.write(rel, _NEW_SOURCE)
    return True