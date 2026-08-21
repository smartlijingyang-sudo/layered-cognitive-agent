"""Patch: LobeHub model picker only exposes solo / team / auto / creator."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_HOOK = "src/hooks/useEnabledChatModels.ts"
_SELECTION = "src/features/ChatInput/hooks/useAgentModelSelection.ts"
_MODEL = "src/features/ChatInput/ActionBar/Model/index.tsx"
_LABEL = "src/features/ChatInput/ActionBar/ModelLabel/index.tsx"
_MARKER = "LCA: picker only solo/team/auto/creator"

meta = PatchMeta(
    name="lca_model_catalog",
    description="Chat model picker shows only solo / team / auto / creator",
    files=(_HOOK, _SELECTION, _MODEL, _LABEL),
    risk="medium",
    category="provider",
    depends_on=(),
    why="Users must pick an LCA mode, not a vendor model; vendor ids leak into /webapi/chat",
    technical_detail=(
        "useEnabledChatModels returns a fixed LCA catalog (solo/team/auto/creator). "
        "useAgentModelSelection remaps any non-LCA stored model to solo."
    ),
    verify_file=_HOOK,
    verify_marker=_MARKER,
)

_HOOK_TS = """import { type EnabledProviderWithModels } from '@/types/aiProvider';

/* LCA: picker only solo/team/auto/creator */

export const LCA_CHAT_PROVIDER = 'openai';

export const LCA_CHAT_MODELS = ['solo', 'team', 'auto', 'cordis-creator'] as const;

export type LcaChatModel = (typeof LCA_CHAT_MODELS)[number];

const LCA_CATALOG: EnabledProviderWithModels[] = [
  {
    children: [
      {
        abilities: { functionCall: true, vision: true },
        contextWindowTokens: 1_000_000,
        description: 'Single assistant. No team casting.',
        displayName: 'Solo',
        id: 'solo',
      },
      {
        abilities: { functionCall: true, vision: true },
        contextWindowTokens: 1_000_000,
        description: 'Auto-cast a team for the task.',
        displayName: 'Team',
        id: 'team',
      },
      {
        abilities: { functionCall: true, vision: true },
        contextWindowTokens: 1_000_000,
        description: 'Same as Team. Kept as an explicit entry.',
        displayName: 'Auto',
        id: 'auto',
      },
      {
        abilities: { functionCall: true, vision: true },
        contextWindowTokens: 1_000_000,
        description: 'Creator §13.3 — agent self-authors plugins and persists them.',
        displayName: 'Creator',
        id: 'cordis-creator',
      },
    ],
    id: LCA_CHAT_PROVIDER,
    name: 'LCA',
    source: 'custom',
  },
];

export function resolveLcaChatModel(model: string | undefined): LcaChatModel {
  return (LCA_CHAT_MODELS as readonly string[]).includes(model ?? '')
    ? (model as LcaChatModel)
    : 'solo';
}

export const useEnabledChatModels = (): EnabledProviderWithModels[] => LCA_CATALOG;
"""

_SELECTION_NEEDLE = """  return {
    canDisplayModel,
    canSelectModel,
    isPreferenceLoading,
    model: effectiveModel.model,
    provider: effectiveModel.provider ?? sharedProvider,
"""

_SELECTION_REPLACEMENT = """  /* LCA: picker only solo/team/auto/creator */
  const lcaModel: LcaChatModel =
    (LCA_CHAT_MODELS as readonly string[]).includes(effectiveModel.model)
      ? (effectiveModel.model as LcaChatModel)
      : 'solo';

  return {
    canDisplayModel,
    canSelectModel,
    isPreferenceLoading,
    model: lcaModel,
    provider: 'openai',
"""


def apply(ctx: PatchContext) -> bool:
    changed = ctx.write_if_changed(_HOOK, _HOOK_TS)
    text = ctx.read(_SELECTION)
    if _MARKER not in text:
        if "from '@/hooks/useEnabledChatModels'" not in text:
            import_anchor = "import { usePermission } from '@/hooks/usePermission';\n"
            if import_anchor not in text:
                raise SystemExit("[lca_model_catalog] selection hook import anchor not found")
            text = text.replace(
                import_anchor,
                import_anchor
                + "import { LCA_CHAT_MODELS, type LcaChatModel } from "
                + "'@/hooks/useEnabledChatModels';\n",
                1,
            )
        if _SELECTION_NEEDLE not in text:
            raise SystemExit("[lca_model_catalog] selection hook anchor not found")
        text = text.replace(_SELECTION_NEEDLE, _SELECTION_REPLACEMENT, 1)
        ctx.write(_SELECTION, text)
        changed = True
    for rel in (_MODEL, _LABEL):
        body = ctx.read(rel)
        original = body
        if "resolveLcaChatModel" not in body:
            import_anchor = (
                "import { useAgentModelSelection } from '../../hooks/useAgentModelSelection';\n"
            )
            if import_anchor not in body:
                raise SystemExit(f"[lca_model_catalog] import anchor missing in {rel}")
            body = body.replace(
                import_anchor,
                import_anchor
                + "import { resolveLcaChatModel } from '@/hooks/useEnabledChatModels';\n",
                1,
            )
            old = (
                "  const model = topicModel?.model ?? agentModel;\n"
                "  const provider = topicModel?.model ? topicModel.provider : agentProvider;\n"
            )
            if old not in body:
                raise SystemExit(f"[lca_model_catalog] model/provider anchor missing in {rel}")
            body = body.replace(
                old,
                "  const model = resolveLcaChatModel(topicModel?.model ?? agentModel);\n"
                "  const provider = 'openai';\n",
                1,
            )
        unused = "    model: agentModel,\n    provider: agentProvider,\n"
        if unused in body:
            body = body.replace(unused, "    model: agentModel,\n", 1)
        if body != original:
            ctx.write(rel, body)
            changed = True
    return changed
