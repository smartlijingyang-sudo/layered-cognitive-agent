#!/usr/bin/env bash
# LCA 项目统计 — 代码量/测试/架构/git
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_c() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
_bold() { _c 1 "$1"; }
_cyan() { _c 36 "$1"; }
_green() { _c 32 "$1"; }
_dim() { _c 2 "$1"; }

_count_lines() {
  find "$@" -name '*.py' -not -path '*/__pycache__/*' -not -path '*/.venv/*' 2>/dev/null \
    | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}'
}

_count_files() {
  find "$@" -name '*.py' -not -path '*/__pycache__/*' -not -path '*/.venv/*' 2>/dev/null | wc -l
}

printf '\n%s\n' "$(_bold '── LCA 项目统计 ──')"

# ── Python 代码 ──
printf '\n%s\n' "$(_cyan 'Python 代码')"
total_lines=$(_count_lines "${ROOT}/lca" "${ROOT}/gateway" "${ROOT}/scripts" "${ROOT}/tests" "${ROOT}/deploy" "${ROOT}/tools")
total_files=$(_count_files "${ROOT}/lca" "${ROOT}/gateway" "${ROOT}/scripts" "${ROOT}/tests" "${ROOT}/deploy" "${ROOT}/tools")
printf '  总计:     %s 行 / %s 文件\n' "${total_lines}" "${total_files}"

printf '\n  %s\n' "$(_dim '按层分布:')"
for layer in contracts infrastructure cognition runtime agent application; do
  dir="${ROOT}/lca/${layer}"
  [[ -d "${dir}" ]] || continue
  lines=$(_count_lines "${dir}")
  files=$(_count_files "${dir}")
  printf '    %-24s %6s 行  %4s 文件\n' "${layer}" "${lines}" "${files}"
done

for extra in gateway scripts tests deploy tools; do
  dir="${ROOT}/${extra}"
  [[ -d "${dir}" ]] || continue
  lines=$(_count_lines "${dir}")
  files=$(_count_files "${dir}")
  printf '    %-24s %6s 行  %4s 文件\n' "${extra}" "${lines}" "${files}"
done

# ── 测试 ──
printf '\n%s\n' "$(_cyan '测试')"
test_count=$(grep -r 'def test_' "${ROOT}/tests" --include='*.py' 2>/dev/null | wc -l)
test_files=$(_count_files "${ROOT}/tests")
printf '  测试函数: %s\n' "${test_count}"
printf '  测试文件: %s\n' "${test_files}"

if [[ -f "${ROOT}/.coverage" ]]; then
  cov=$(cd "${ROOT}" && uv run coverage report --skip-covered 2>/dev/null | grep '^TOTAL' | awk '{print $NF}' || echo "N/A")
  [[ -z "${cov}" ]] && cov="N/A"
  printf '  覆盖率:   %s\n' "${cov}"
fi

# ── 架构 ──
printf '\n%s\n' "$(_cyan '架构')"
contract_count=$(grep -c '^\[\[tool.importlinter.contracts\]\]' "${ROOT}/pyproject.toml" 2>/dev/null || echo 0)
contract_count=$(grep -c 'name' "${ROOT}/pyproject.toml" 2>/dev/null | head -1 || echo "?")
adr_count=$(find "${ROOT}/docs/adr" -name '*.md' 2>/dev/null | wc -l)
role_count=$(find "${ROOT}/roles" -name '*.yaml' -o -name '*.yml' 2>/dev/null | wc -l)
scenario_count=$(find "${ROOT}/tests/fixtures/team_scenarios" -name '*.yaml' 2>/dev/null | wc -l)
printf '  ADR 文档:      %s\n' "${adr_count}"
printf '  角色定义:      %s\n' "${role_count}"
printf '  团队场景:      %s\n' "${scenario_count}"

# ── LobeHub 集成 ──
printf '\n%s\n' "$(_cyan 'LobeHub 集成')"
if [[ -f "${ROOT}/lobehub-ui/package.json" ]]; then
  lobe_ver=$(grep '"version"' "${ROOT}/lobehub-ui/package.json" | head -1 | sed 's/.*: *"//;s/".*//')
  printf '  版本:     %s\n' "${lobe_ver}"
else
  printf '  版本:     %s\n' "$(_dim '未同步')"
fi
patch_count=$(grep -c 'PatchMeta(' "${ROOT}/deploy/lobehub/patch_lobehub.py" 2>/dev/null || echo "?")
printf '  补丁数:   %s\n' "${patch_count}"
bridge_files=$(find "${ROOT}/gateway/lobehub_bridge" -name '*.py' 2>/dev/null | wc -l)
printf '  Bridge:   %s 文件\n' "${bridge_files}"

# ── Git ──
printf '\n%s\n' "$(_cyan 'Git')"
if [[ -d "${ROOT}/.git" ]]; then
  branch=$(git -C "${ROOT}" branch --show-current 2>/dev/null || echo "detached")
  commits=$(git -C "${ROOT}" rev-list --count HEAD 2>/dev/null || echo "?")
  last_commit=$(git -C "${ROOT}" log -1 --format='%h %s (%cr)' 2>/dev/null || echo "?")
  dirty=$(git -C "${ROOT}" status --porcelain 2>/dev/null | wc -l)
  printf '  分支:     %s\n' "${branch}"
  printf '  总提交:   %s\n' "${commits}"
  printf '  最新:     %s\n' "${last_commit}"
  printf '  未提交:   %s 文件\n' "${dirty}"
fi

# ── 依赖 ──
printf '\n%s\n' "$(_cyan '依赖')"
if [[ -f "${ROOT}/pyproject.toml" ]]; then
  dep_count=$(grep -c '^\s*"[a-zA-Z]' "${ROOT}/pyproject.toml" 2>/dev/null || echo "?")
  printf '  Python:   ~%s (pyproject.toml 中声明)\n' "${dep_count}"
fi
if [[ -d "${ROOT}/.venv" ]]; then
  installed=$(cd "${ROOT}" && uv pip list 2>/dev/null | wc -l || echo "?")
  printf '  已安装:   %s 包\n' "${installed}"
fi

printf '\n'
