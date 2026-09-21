"""Patch: LobeHub model picker only exposes solo / team / auto."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_HOOK = "src/hooks/useEnabledChatModels.ts"
_SELECTION = "src/features/ChatInput/hooks/useAgentModelSelection.ts"
_MODEL = "src/features/ChatInput/ActionBar/Model/index.tsx"
_LABEL = "src/features/ChatInput/ActionBar/ModelLabel/index.tsx"
_TOOL_USE = "src/hooks/useModelSupportToolUse.ts"
_EFFECTIVE_MODE = "src/features/ChatInput/hooks/useEffectiveAgentMode.ts"
_MARKER = "LCA: picker only solo/team/auto"

meta = PatchMeta(
    name="lca_model_catalog",
    description="Chat model picker shows only solo / team / auto",
    files=(_HOOK, _SELECTION, _MODEL, _LABEL, _TOOL_USE, _EFFECTIVE_MODE),
    risk="medium",
    category="provider",
    depends_on=(),
    why="Users must pick an LCA mode, not a vendor model; vendor ids leak into /webapi/chat",
    technical_detail=(
        "useEnabledChatModels returns a fixed LCA catalog. "
        "useAgentModelSelection remaps any other stored model to solo. "
        "useModelSupportToolUse returns true for LCA catalog models because the "
        "gateway run carrier always provides tools, even when the aiInfra "
        "enabled-model list (server runtime state) has no solo/team/auto row. "
        "useEffectiveAgentMode remaps the stored model before the capability "
        "check so Agent mode (and the device selector) is available."
    ),
    verify_file=_HOOK,
    verify_marker=_MARKER,
)

_HOOK_TS = """import { type EnabledProviderWithModels } from '@/types/aiProvider';

/* LCA: picker only solo/team/auto */

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
        description: 'Cordis creator: plugin authoring + preset reuse.',
        displayName: 'Cordis Creator',
        id: 'cordis-creator',
      },
    ],
    id: LCA_CHAT_PROVIDER,
    name: 'LCA',
    source: 'custom',
  },
];

export function resolveLcaChatModel(model: string | undefined): LcaChatModel {
  return model === 'team' || model === 'auto' ? model : 'solo';
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

_SELECTION_REPLACEMENT = """  /* LCA: picker only solo/team/auto */
  const lcaModel =
    effectiveModel.model === 'team' || effectiveModel.model === 'auto'
      ? effectiveModel.model
      : 'solo';

  return {
    canDisplayModel,
    canSelectModel,
    isPreferenceLoading,
    model: lcaModel,
    provider: 'openai',
"""


_TOOL_USE_TS = """import { aiModelSelectors, useAiInfraStore } from '@/store/aiInfra';

/* LCA: catalog models always support tool calling (gateway run carrier). */
import { LCA_CHAT_MODELS } from '@/hooks/useEnabledChatModels';

export const useModelSupportToolUse = (model: string, provider: string) => {
  if ((LCA_CHAT_MODELS as readonly string[]).includes(model)) return true;
  return useAiInfraStore(aiModelSelectors.isModelSupportToolUse(model, provider));
};
"""

_EFFECTIVE_MODE_IMPORT = (
    "import { useModelSupportToolUse } from '@/hooks/useModelSupportToolUse';\n"
)
_EFFECTIVE_MODE_NEEDLE = "const supportToolUse = useModelSupportToolUse(model, provider);"
_EFFECTIVE_MODE_REPLACEMENT = (
    "/* LCA: remap stored vendor model to the LCA catalog before the tool-use "
    "check so Agent mode / device selector is available. */\n"
    "  const supportToolUse = useModelSupportToolUse(resolveLcaChatModel(model), 'openai');"
)


def _patch_effective_mode(ctx: PatchContext) -> bool:
    rel = _EFFECTIVE_MODE
    body = ctx.read(rel)
    original = body
    if "resolveLcaChatModel" not in body:
        if _EFFECTIVE_MODE_IMPORT not in body:
            raise SystemExit("[lca_model_catalog] effective-mode import anchor missing")
        body = body.replace(
            _EFFECTIVE_MODE_IMPORT,
            _EFFECTIVE_MODE_IMPORT + "import { resolveLcaChatModel } from '@/hooks/useEnabledChatModels';\n",
            1,
        )
    if _EFFECTIVE_MODE_NEEDLE in body:
        body = body.replace(_EFFECTIVE_MODE_NEEDLE, _EFFECTIVE_MODE_REPLACEMENT, 1)
    elif _EFFECTIVE_MODE_REPLACEMENT not in body:
        raise SystemExit("[lca_model_catalog] effective-mode supportToolUse anchor missing")
    if body != original:
        ctx.write(rel, body)
        return True
    return False


def apply(ctx: PatchContext) -> bool:
    changed = ctx.write_if_changed(_HOOK, _HOOK_TS)
    changed = ctx.write_if_changed(_TOOL_USE, _TOOL_USE_TS) or changed
    changed = _patch_effective_mode(ctx) or changed
    text = ctx.read(_SELECTION)
    if not ("provider: 'openai'" in text and "lcaModel" in text):
        if _SELECTION_NEEDLE not in text:
            raise SystemExit("[lca_model_catalog] selection hook anchor not found")
        ctx.write(_SELECTION, text.replace(_SELECTION_NEEDLE, _SELECTION_REPLACEMENT, 1))
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
