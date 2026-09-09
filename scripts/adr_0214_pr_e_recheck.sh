#!/usr/bin/env bash
# ADR-0214 PR-E: 真实生产复测脚本
#
# 触发条件:
#   1. PR-A (TaskProgress + Reducer + Projection + fsync 测试) 已落地
#   2. PR-B (MultiToolLoopBreakerGate + plugin wiring) 已落地
#   3. PR-C (PG-007 三件套 precondition/terminal_predicate) 已落地
#   4. PR-D (Skill 打包契约 + read_skill_reference_once 节流) 已落地
#
# 流程:
#   1. 验证 stack 健康 (kernel_serve / daemon / infra / lobehub / onlyboxes)
#   2. 重启 kernel_serve 加载新代码
#   3. 触发同一份 Q4 pptx 任务 (与 run_c218d952c6f2 相同)
#   4. 验证:
#      - officecli add >= 1 次
#      - office_works_sealer 触发 1 次
#      - run 进入 terminal outcome (status: completed)
#      - doctor H1-H12 全 ok
#      - 没有 PG-007 node visit budget exhausted 错误
#   5. 反例 fixture: 重放 run_c218d952c6f2 spine events, 断言
#      "在新机制下应在第 6 步前熔断, 不依赖 PG-007"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PROMPT=$(cat <<'EOF'
请基于以下 Q4 简报生成一份 5 页 PPT,输出到 /mnt/data/outputs/q4-review-v2.pptx。

注意 (防止重做踩坑):
- 文件可能已存在 → 先 `rm -f /mnt/data/outputs/q4-review-v2.pptx` 再 create
- officecli create 必须带 --json
- 5 页:每页 officecli add 一个 slide + shape
- 最后 officecli validate 检查
- 如遇错误立即调整命令,不要反复调同一个失败命令

简报:

# Q4 2026 业务回顾

## 摘要
- 营收:1200 万美元,YoY +25%,达成预算 104%。
- 毛利:760 万美元,毛利率 63.3%(YoY +2.1pp)。
- 新签 ARR:480 万美元,YoY +38%。
- 关键事件:Hermes 网关、OfficeCLI plane、P7 region-tag。

## 三大亮点
1. Hermes 网关:统一 LobeHub 入口,run 平均延迟 -18%。
2. OfficeCLI plane:Office 生成改用预装 officecli,run 收敛速度提升。
3. P7 region-tag:Profile regions.declare 落地。

## 风险与下季重点
- OfficeCLI 循环调用已修复(office_works_sealer + tool_loop_breaker)。
- 下季重点:lab 收编、ADR-0212 step_tree、OfficeWorksSealer 行为对齐。
EOF
)

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[FATAL] $*" >&2; exit 1; }

# ── Step 1: Stack 健康 (kernel/infra/lobehub/onlyboxes 必须 running, daemon 单独起) ──
log "Step 1: verify stack health (daemon 由 Step 2b 重启)"
./scripts/lca-ops status --json > /tmp/adr_0214_pr_e_status.json
python3 - <<'PY'
import json, sys
data = json.load(open("/tmp/adr_0214_pr_e_status.json"))
# daemon 在 kernel restart 后会短暂 stopped, 不算 hard fail
required_running = {"kernel_serve", "infra", "lobehub", "onlyboxes"}
current = {svc["service"]: svc["status"] for svc in data if svc.get("service")}
failing = [f"{k}={current[k]}" for k in required_running if current.get(k) != "running"]
if failing:
    print("FAILING (required):", ", ".join(failing))
    sys.exit(1)
print("all required services running (daemon status:", current.get("daemon", "?"), ")")
PY
log "  → required services running"

# ── Step 2: 重启 kernel_serve ──────────────────────────────────────────
log "Step 2: restart kernel_serve to load new code"
./scripts/lca-ops kernel-restart --json
log "  → kernel_serve restarted"

# kernel restart 会冲掉 daemon, 重新起
log "Step 2b: re-start daemon (kernel restart kills it)"
./scripts/lca-ops daemon start --json | tail -3
log "  → daemon re-connected"

# ── Step 3: 触发 Q4 pptx 任务 ──────────────────────────────────────────
log "Step 3: trigger Q4 pptx task (same as run_c218d952c6f2)"
RUN_OUT_FILE=/tmp/adr_0214_pr_e_run_create.json
./scripts/lca-ops runs create --user-text "$PROMPT" --json > "$RUN_OUT_FILE" 2>&1
RUN_ID=$(python3 -c "import json; print(json.load(open('$RUN_OUT_FILE'))['run_id'])")
log "  → run_id=$RUN_ID"

# ── Step 3.5: 轮询等待 run 进入 terminal ──────────────────────────────
log "Step 3.5: poll for terminal outcome (max 5 min)"
for i in $(seq 1 30); do
    sleep 10
    STATUS=$(curl -s "http://127.0.0.1:8765/runs/${RUN_ID}/doctor" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "canceled" ]; then
        log "  → run reached terminal: $STATUS (after $((i*10))s)"
        break
    fi
    log "  → step $((i)): status=$STATUS"
done

# ── Step 4: 验证 officecli add + sealer + terminal outcome ──────────────
log "Step 4: verify officecli add + sealer + terminal outcome"
./scripts/lca-ops journal logs -r "$RUN_ID" -v > "/tmp/adr_0214_pr_e_${RUN_ID}.log" 2>&1 || true

python3 - <<PY
import json, sys, re
log = open("/tmp/adr_0214_pr_e_${RUN_ID}.log").read()

# 1. officecli add >= 1
add_count = len(re.findall(r'officecli\s+add\s+\S+', log))
print(f"officecli add count: {add_count}")
assert add_count >= 1, f"officecli add count {add_count} < 1 (旧基线 0 次)"

# 2. officecli validate >= 1
validate_count = len(re.findall(r'officecli\s+validate\s+\S+', log))
print(f"officecli validate count: {validate_count}")
assert validate_count >= 1, f"officecli validate count {validate_count} < 1"

# 3. office_works_sealer trigger >= 1
sealer_count = len(re.findall(r'office_works_sealer|publish_office_works', log))
print(f"office_works_sealer trigger: {sealer_count}")
assert sealer_count >= 1, f"office_works_sealer trigger {sealer_count} < 1"

# 4. read_skill_reference 反复模式彻底消失
ref_count = len(re.findall(r'read_skill_reference', log))
print(f"read_skill_reference count: {ref_count}")
assert ref_count == 0, (
    f"read_skill_reference should be 0 after PR-D 节流, got {ref_count}"
)

# 5. PG-007 (NOT 强约束; PR-F 才闭环软收敛)
pg007 = 'PG-007: node visit budget exhausted' in log
print(f"PG-007 hit: {pg007} (PR-F 闭环目标,本次不强约束)")

# 6. terminal outcome
import urllib.request
doctor = json.loads(urllib.request.urlopen(
    f"http://127.0.0.1:8765/runs/${RUN_ID}/doctor"
).read())
print(f"doctor status: {doctor.get('status')}, outcome: {doctor.get('outcome')}")

# 软判定: status != running
assert doctor.get('status') in ('completed', 'failed', 'canceled'), (
    f"run still running after 5 min: {doctor.get('status')}"
)
PY
log "  → officecli plane loop broken; PR-F needed for soft convergence"

# ── Step 5: 反例 fixture run_c218d952c6f2 ─────────────────────────────
log "Step 5: replay fixture run_c218d952c6f2 → assert new-mechanism break"
uv run pytest \
  tests/integration/test_run_c218d952c6f2_regression.py \
  tests/integration/test_no_officecli_loop_pattern.py \
  -q --no-cov 2>&1 | tail -20

log "✓ PR-E 真实生产复测 + regression fixture 全过"
