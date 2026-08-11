#!/usr/bin/env bash
# LCA 集成：主聊天 + 系统 mini agent 均走 LCA gateway（solo / openai）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MARKER="${ROOT}/lobehub-ui/.lca-qwen-defaults-patched"

LCA_DEFAULT_MODEL="${LCA_DEFAULT_MODEL:-solo}"
LCA_DEFAULT_PROVIDER="${LCA_DEFAULT_PROVIDER:-openai}"
LCA_DEFAULT_MINI_MODEL="${LCA_DEFAULT_MINI_MODEL:-solo}"
LCA_DEFAULT_MINI_PROVIDER="${LCA_DEFAULT_MINI_PROVIDER:-openai}"

log() { printf '[patch-qwen] %s\n' "$*"; }

patch_business_const() {
  local llm_ts="${ROOT}/lobehub-ui/packages/business/const/src/llm.ts"
  local desktop_stub="${ROOT}/lobehub-ui/apps/desktop/stubs/business-const/src/index.ts"

  for f in "${llm_ts}" "${desktop_stub}"; do
    [[ -f "${f}" ]] || continue
    python3 - "${f}" \
      "${LCA_DEFAULT_MODEL}" "${LCA_DEFAULT_PROVIDER}" \
      "${LCA_DEFAULT_MINI_MODEL}" "${LCA_DEFAULT_MINI_PROVIDER}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
model, provider, mini_model, mini_provider = sys.argv[2:6]
text = path.read_text()

replacements = [
    (r"export const DEFAULT_MODEL = '[^']*';", f"export const DEFAULT_MODEL = '{model}';"),
    (r"export const DEFAULT_PROVIDER = '[^']*';", f"export const DEFAULT_PROVIDER = '{provider}';"),
    (r"export const DEFAULT_MINI_MODEL = '[^']*';", f"export const DEFAULT_MINI_MODEL = '{mini_model}';"),
    (
        r"export const DEFAULT_MINI_PROVIDER = '[^']*';",
        f"export const DEFAULT_MINI_PROVIDER = '{mini_provider}';",
    ),
]
for pattern, repl in replacements:
    text, count = re.subn(pattern, repl, text, count=1)
    if count != 1:
        raise SystemExit(f"patch failed for {pattern} in {path}")

path.write_text(text)
print(
    f"[patch-qwen] {path.name}: "
    f"DEFAULT={model}/{provider}, MINI={mini_model}/{mini_provider}"
)
PY
  done
}

patch_openai_lca_guard() {
  local openai_ts="${ROOT}/lobehub-ui/packages/model-runtime/src/providers/openai/index.ts"
  [[ -f "${openai_ts}" ]] || return 0

  python3 - "${openai_ts}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
marker = "/* LCA: solo/team always chat/completions */"
if marker in text:
    print(f"[patch-qwen] openai LCA guard already patched in {path.name}")
    raise SystemExit(0)

needle = "      if (isResponsesAPIModel(model) || enabledSearch) {"
if needle not in text:
    raise SystemExit(f"LCA guard anchor not found in {path}")

replacement = (
    "      const isLcaGatewayModel = ['solo', 'team', 'auto'].includes(model);\n"
    f"      {marker}\n"
    "      if (!isLcaGatewayModel && (isResponsesAPIModel(model) || enabledSearch)) {"
)
text = text.replace(needle, replacement, 1)
path.write_text(text)
print(f"[patch-qwen] openai provider: LCA models skip Responses API in {path.name}")
PY
}

patch_provider_order() {
  local providers_ts="${ROOT}/lobehub-ui/packages/model-bank/src/modelProviders/index.ts"
  [[ -f "${providers_ts}" ]] || return 0

  python3 - "${providers_ts}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()

if "/* LCA: OpenAI first */" in text:
    print(f"[patch-qwen] provider order already patched in {path.name}")
    raise SystemExit(0)

needle = "  ...(ENABLE_BUSINESS_FEATURES ? [LobeHubProvider] : []),\n"
if needle not in text:
    raise SystemExit(f"LobeHub spread anchor not found in {path}")

text = re.sub(r"\n  OpenAIProvider,\n", "\n", text, count=1)
text = text.replace(
    needle,
    needle + "  OpenAIProvider, /* LCA: OpenAI first */\n",
    1,
)
path.write_text(text)
print("[patch-qwen] moved OpenAIProvider to top of DEFAULT_MODEL_PROVIDER_LIST")
PY
}

patch_already_applied() {
  local llm_ts="${ROOT}/lobehub-ui/packages/business/const/src/llm.ts"
  local openai_ts="${ROOT}/lobehub-ui/packages/model-runtime/src/providers/openai/index.ts"
  [[ -f "${MARKER}" && -f "${llm_ts}" && -f "${openai_ts}" ]] || return 1
  grep -q "DEFAULT_MINI_PROVIDER = '${LCA_DEFAULT_MINI_PROVIDER}'" "${llm_ts}" 2>/dev/null \
    && grep -q "LCA: solo/team always chat/completions" "${openai_ts}" 2>/dev/null
}

main() {
  if [[ ! -d "${ROOT}/lobehub-ui" ]]; then
    log "跳过：lobehub-ui/ 不存在"
    exit 0
  fi

  patch_business_const
  patch_openai_lca_guard
  patch_provider_order
  date -u +%Y-%m-%dT%H:%M:%SZ >"${MARKER}"
  log "完成"
}

main "$@"
