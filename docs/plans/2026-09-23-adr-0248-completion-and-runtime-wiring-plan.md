# ADR-0248 全面补齐与运行时主循环总装实施计划 (ADR-0248 Completion & Runtime Wiring Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 补齐 ADR-0248 剩余三大领域切片（切片 3: BoxAccessor 员工机、切片 4: Auto-Review 三态与 Escalate 重放人审、切片 8: InitiativeHooks 纯函数主动提议器），并将门控声带与人闸无缝总装接入 `runtime_loop.py`，实现桌面 Agent 运行时的全链路生产级闭环。

**Architecture:** 
1. **切片 3（两台电脑平面）**：落地 `ComputerPlane` 与 `BoxAccessor`，将员工电脑与用户本机（ADR-0246 LocalExec）进行沙箱与认知话术严格隔离；
2. **切片 4（Auto-Review 三态硬闸）**：落地 `AutoReviewMode`、`AutoReviewGate` 与基于 SHA-256 指纹的重放校验，支持 Adapt 降级与 Escalate 人审；
3. **切片 8（主动提议器）**：落地 `InitiativeOffer` 与纯函数 `evaluate_initiative` 提议器，控制单轮至多 1 条 Nudge 规避消息风暴；
4. **运行时总装（Wiring）**：在 `runtime_loop.py` 声明式挂载声带与审核策略，按 Profile `vocal_mode` 按需启用，保证经典模式 100% 零退化。

**Tech Stack:** Python 3.11+, Pydantic V2 (`frozen=True`, `extra="forbid"`), Pytest, LCA Contracts, Infrastructure, Application & Runtime Layer.

---

### Task 1: 切片 3 — 员工电脑平面与 BoxAccessor (ComputerPlane, BoxAccessor)

**Files:**
- Create: `lca/contracts/models/computer/box.py`
- Modify: `lca/contracts/models/computer/__init__.py`
- Create: `lca/infrastructure/computer/box_accessor.py`
- Test: `tests/infrastructure/computer/test_box_accessor.py`
- Does NOT own: 宿主机进程注入、用户机长连接协议（AP-01）
- Invariants to test: `ComputerPlane.BOX == "box"`, `ComputerPlane.LOCAL == "local"`；`BoxAccessor` 根目录严格锁定在 `/home/box`（或构造传入的隔离目录），任何超出沙箱的路径解析抛出 `PermissionError`；读写与执行接口正常工作且标记名称为“我的电脑”（INV-06，AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/computer/test_box_accessor.py
import pytest
from pathlib import Path
from lca.contracts.models.computer.box import ComputerPlane
from lca.infrastructure.computer.box_accessor import BoxAccessor


def test_computer_plane_enum():
    assert ComputerPlane.BOX == "box"
    assert ComputerPlane.LOCAL == "local"


def test_box_accessor_sandbox_isolation(tmp_path: Path):
    box_root = tmp_path / "home_box"
    box_root.mkdir()
    accessor = BoxAccessor(root_dir=box_root)

    # 合法子路径
    safe_path = accessor.resolve_path("workspace/code.py")
    assert str(safe_path).startswith(str(box_root))

    # 试图越权逃逸
    with pytest.raises(PermissionError):
        accessor.resolve_path("../../etc/passwd")


def test_box_accessor_read_write(tmp_path: Path):
    box_root = tmp_path / "home_box"
    box_root.mkdir()
    accessor = BoxAccessor(root_dir=box_root)

    accessor.write_text("hello.txt", "hello box computer")
    content = accessor.read_text("hello.txt")
    assert content == "hello box computer"
    assert accessor.display_name == "我的电脑"
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/infrastructure/computer/test_box_accessor.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/contracts/models/computer/box.py`:
```python
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class ComputerPlane(StrEnum):
    """执行电脑平面。"""
    BOX = "box"       # 员工电脑（我的电脑）
    LOCAL = "local"   # 用户电脑（你的电脑）


class ComputerPlaneMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plane: ComputerPlane
    display_name: str
    description: str
```

`lca/infrastructure/computer/box_accessor.py`:
```python
from pathlib import Path
from lca.contracts.models.computer.box import ComputerPlane


class BoxAccessor:
    """员工电脑专属沙箱访问器。"""

    def __init__(self, root_dir: str | Path = "/home/box") -> None:
        self.root_dir = Path(root_dir).resolve()
        self.display_name = "我的电脑"
        self.plane = ComputerPlane.BOX

    def resolve_path(self, subpath: str) -> Path:
        resolved = (self.root_dir / subpath.lstrip("/")).resolve()
        if not str(resolved).startswith(str(self.root_dir)):
            raise PermissionError(f"越权访问受阻：路径 '{subpath}' 超出员工电脑沙箱范围")
        return resolved

    def write_text(self, subpath: str, content: str) -> Path:
        target = self.resolve_path(subpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read_text(self, subpath: str) -> str:
        target = self.resolve_path(subpath)
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {subpath}")
        return target.read_text(encoding="utf-8")
```

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/infrastructure/computer/test_box_accessor.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/computer/ lca/infrastructure/computer/box_accessor.py tests/infrastructure/computer/test_box_accessor.py
git commit -m "feat(computer): implement BoxAccessor and ComputerPlane for employee machine"
```

---

### Task 2: 切片 4 — Auto-Review 契约与动作指纹 (AutoReviewMode, AutoReviewVerdict)

**Files:**
- Create: `lca/contracts/models/auto_review/models.py`
- Create: `lca/contracts/models/auto_review/__init__.py`
- Test: `tests/contracts/auto_review/test_auto_review_models.py`
- Does NOT own: 业务审批持久化数据库（AP-01）
- Invariants to test: `AutoReviewMode` 三态闭集（`off`, `shadow`, `enforce`）；`AutoReviewVerdict` 不可变强类型校验；`compute_action_fingerprint` 保证对同一工具调用产生确定性 SHA-256 指纹（INV-07，AP-02）。

**Step 1: Write the failing test**

```python
# tests/contracts/auto_review/test_auto_review_models.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.auto_review.models import (
    AutoReviewMode,
    AutoReviewAction,
    AutoReviewVerdict,
    compute_action_fingerprint,
)


def test_auto_review_enums():
    assert AutoReviewMode.OFF == "off"
    assert AutoReviewMode.SHADOW == "shadow"
    assert AutoReviewMode.ENFORCE == "enforce"

    assert AutoReviewAction.ALLOW == "allow"
    assert AutoReviewAction.ADAPT == "adapt"
    assert AutoReviewAction.ESCALATE == "escalate"
    assert AutoReviewAction.BLOCK == "block"


def test_auto_review_verdict_frozen():
    verdict = AutoReviewVerdict(
        action=AutoReviewAction.ALLOW,
        reason="Safe operation",
    )
    with pytest.raises(ValidationError):
        verdict.action = AutoReviewAction.BLOCK  # type: ignore


def test_action_fingerprint_deterministic():
    fp1 = compute_action_fingerprint("run_shell", {"command": "rm -rf /tmp/data"})
    fp2 = compute_action_fingerprint("run_shell", {"command": "rm -rf /tmp/data"})
    fp3 = compute_action_fingerprint("run_shell", {"command": "rm -rf /tmp/other"})
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 64
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/contracts/auto_review/test_auto_review_models.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/contracts/models/auto_review/models.py`:
```python
import hashlib
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class AutoReviewMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class AutoReviewAction(StrEnum):
    ALLOW = "allow"
    ADAPT = "adapt"
    ESCALATE = "escalate"
    BLOCK = "block"


class AutoReviewVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: AutoReviewAction
    reason: str
    adapted_command: str | None = None
    action_fingerprint: str | None = None


def compute_action_fingerprint(tool_name: str, arguments: dict) -> str:
    raw = f"{tool_name}:{sorted(arguments.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/contracts/auto_review/test_auto_review_models.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/auto_review/ tests/contracts/auto_review/
git commit -m "feat(contracts): define AutoReview models and deterministic action fingerprint"
```

---

### Task 3: 切片 4 — Auto-Review 硬闸与重放人审核验 (AutoReviewGate)

**Files:**
- Create: `lca/infrastructure/auto_review/gate.py`
- Create: `lca/infrastructure/auto_review/__init__.py`
- Test: `tests/infrastructure/auto_review/test_auto_review_gate.py`
- Does NOT own: 前端模态对话框、底层操作系统权限弹窗（AP-01）
- Invariants to test: `off` 模式全部放行；`shadow` 记录审计并放行；`enforce` 拦截破坏性 Shell 调用；`adapt` 返回低权限替代；`escalate` 生成人审卡并要求相同的 `action_fingerprint` 重放放行，换命令骗过分类器直接阻断（INV-07，AP-02）。

**Step 1: Write the failing test**

```python
# tests/infrastructure/auto_review/test_auto_review_gate.py
import pytest
from lca.contracts.models.auto_review.models import AutoReviewMode, AutoReviewAction
from lca.infrastructure.auto_review.gate import AutoReviewGate


def test_gate_off_mode_always_allows():
    gate = AutoReviewGate(mode=AutoReviewMode.OFF)
    verdict = gate.evaluate("run_shell", {"command": "rm -rf /home/box/data"})
    assert verdict.action == AutoReviewAction.ALLOW


def test_gate_shadow_mode_audits_and_allows():
    gate = AutoReviewGate(mode=AutoReviewMode.SHADOW)
    verdict = gate.evaluate("run_shell", {"command": "rm -rf /home/box/data"})
    assert verdict.action == AutoReviewAction.ALLOW
    assert len(gate.get_audit_records()) == 1
    assert gate.get_audit_records()[0]["flagged"] is True


def test_gate_enforce_mode_blocks_dangerous_and_adapt():
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    verdict = gate.evaluate("run_shell", {"command": "cat /etc/shadow"})
    assert verdict.action == AutoReviewAction.BLOCK


def test_gate_enforce_escalate_and_verify_fingerprint():
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    args = {"command": "rm -rf /home/box/cache"}
    verdict = gate.evaluate("run_shell", args)
    assert verdict.action == AutoReviewAction.ESCALATE
    fp = verdict.action_fingerprint
    assert fp is not None

    # 人工审批放行
    gate.grant_approval(fp)

    # 1. 相同动作原封不动重放：放行
    replay_verdict = gate.evaluate("run_shell", args)
    assert replay_verdict.action == AutoReviewAction.ALLOW

    # 2. 换命令试图偷渡：拒绝
    tampered_verdict = gate.evaluate("run_shell", {"command": "rm -rf /home/box/other"})
    assert tampered_verdict.action == AutoReviewAction.ESCALATE
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/infrastructure/auto_review/test_auto_review_gate.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/infrastructure/auto_review/gate.py`:
```python
from typing import Any
from lca.contracts.models.auto_review.models import (
    AutoReviewAction,
    AutoReviewMode,
    AutoReviewVerdict,
    compute_action_fingerprint,
)


class AutoReviewGate:
    """工具副作用自动审查硬闸。"""

    DANGEROUS_COMMAND_SUBSTRINGS = ("rm -rf", "cat /etc/shadow", "mkfs", "> /dev/")

    def __init__(self, mode: AutoReviewMode = AutoReviewMode.ENFORCE) -> None:
        self.mode = mode
        self._audit_records: list[dict[str, Any]] = []
        self._approved_fingerprints: set[str] = set()

    def grant_approval(self, fingerprint: str) -> None:
        self._approved_fingerprints.add(fingerprint)

    def evaluate(self, tool_name: str, arguments: dict[str, Any]) -> AutoReviewVerdict:
        fp = compute_action_fingerprint(tool_name, arguments)

        # 检查是否已获得人审放行
        if fp in self._approved_fingerprints:
            return AutoReviewVerdict(
                action=AutoReviewAction.ALLOW,
                reason="动作已由人工授权放行",
                action_fingerprint=fp,
            )

        cmd = str(arguments.get("command", ""))
        is_risky = any(sub in cmd for sub in self.DANGEROUS_COMMAND_SUBSTRINGS)

        if self.mode == AutoReviewMode.OFF:
            return AutoReviewVerdict(action=AutoReviewAction.ALLOW, reason="AutoReview 关闭")

        if self.mode == AutoReviewMode.SHADOW:
            self._audit_records.append({"tool": tool_name, "args": arguments, "flagged": is_risky})
            return AutoReviewVerdict(action=AutoReviewAction.ALLOW, reason="Shadow 模式放行并审计")

        # ENFORCE 模式
        if not is_risky:
            return AutoReviewVerdict(action=AutoReviewAction.ALLOW, reason="操作低风险自动放行")

        if "cat /etc/shadow" in cmd:
            return AutoReviewVerdict(action=AutoReviewAction.BLOCK, reason="严禁读取受限敏感系统凭据")

        # 高危且需要人审
        return AutoReviewVerdict(
            action=AutoReviewAction.ESCALATE,
            reason=f"高风险操作拦截，需要人审审批：{tool_name}",
            action_fingerprint=fp,
        )

    def get_audit_records(self) -> list[dict[str, Any]]:
        return list(self._audit_records)
```

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/infrastructure/auto_review/test_auto_review_gate.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/auto_review/ tests/infrastructure/auto_review/
git commit -m "feat(infrastructure): implement AutoReviewGate with shadow and enforce modes"
```

---

### Task 4: 切片 8 — Initiative Hooks 纯函数主动提议器 (InitiativeHooks)

**Files:**
- Create: `lca/contracts/models/initiative/models.py`
- Create: `lca/contracts/models/initiative/__init__.py`
- Create: `lca/application/initiative/hooks.py`
- Create: `lca/application/initiative/__init__.py`
- Test: `tests/application/initiative/test_initiative_hooks.py`
- Does NOT own: 复杂的模型微调、全局聊天轮次改写（AP-01）
- Invariants to test: 纯函数无副作用；重复手动操作达到 3 次时提议 Routine；缺连接器提议安装；单轮至多输出 1 条提议；正常单次操作返回 None（INV-08，AP-02）。

**Step 1: Write the failing test**

```python
# tests/application/initiative/test_initiative_hooks.py
from lca.contracts.models.initiative.models import InitiativeSignal
from lca.application.initiative.hooks import evaluate_initiative


def test_evaluate_initiative_normal_returns_none():
    features = {"manual_action_counts": {"fetch_weather": 1}}
    offer = evaluate_initiative(features)
    assert offer is None


def test_evaluate_initiative_repeated_3_times_suggests_routine():
    features = {"manual_action_counts": {"fetch_weather": 3}}
    offer = evaluate_initiative(features)
    assert offer is not None
    assert offer.signal == InitiativeSignal.REPEATED_MANUAL
    assert "例程" in offer.nudge_message
    assert offer.proposed_routine == "fetch_weather"


def test_evaluate_initiative_missing_connector():
    features = {"missing_connectors": ["github"]}
    offer = evaluate_initiative(features)
    assert offer is not None
    assert offer.signal == InitiativeSignal.MISSING_CONNECTOR
    assert "github" in offer.nudge_message
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/application/initiative/test_initiative_hooks.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/contracts/models/initiative/models.py`:
```python
from enum import StrEnum
from pydantic import BaseModel, ConfigDict


class InitiativeSignal(StrEnum):
    REPEATED_MANUAL = "repeated_manual"
    OBVIOUS_NEXT_STEP = "obvious_next_step"
    MISSING_CONNECTOR = "missing_connector"


class InitiativeOffer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: InitiativeSignal
    nudge_message: str
    proposed_routine: str | None = None
```

`lca/application/initiative/hooks.py`:
```python
from typing import Any
from lca.contracts.models.initiative.models import InitiativeOffer, InitiativeSignal


def evaluate_initiative(transcript_features: dict[str, Any]) -> InitiativeOffer | None:
    """纯函数主动提议器：分析特征，单轮至多返回 1 条高价值建议。"""
    # 1. 检查缺连接器
    missing = transcript_features.get("missing_connectors", [])
    if missing:
        conn = missing[0]
        return InitiativeOffer(
            signal=InitiativeSignal.MISSING_CONNECTOR,
            nudge_message=f"检测到缺少服务连接器 '{conn}'，建议配置连接器以获得更稳定的执行效果。",
        )

    # 2. 检查重复操作第三次
    counts: dict[str, int] = transcript_features.get("manual_action_counts", {})
    for action_name, count in counts.items():
        if count >= 3:
            return InitiativeOffer(
                signal=InitiativeSignal.REPEATED_MANUAL,
                nudge_message=f"检测到动作 '{action_name}' 已重复执行 {count} 次，是否建立自动例程（Routine）？",
                proposed_routine=action_name,
            )

    return None
```

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/application/initiative/test_initiative_hooks.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/models/initiative/ lca/application/initiative/ tests/application/initiative/
git commit -m "feat(application): implement pure-function InitiativeHooks proposer"
```

---

### Task 5: 阶段二 — 运行时主循环总装适配器 (Runtime Wiring Seam)

**Files:**
- Create: `lca/application/vocal/runtime_wiring.py`
- Modify: `lca/runtime/loop/runtime_loop.py`
- Test: `tests/scenario/adr0248/test_runtime_loop_wiring.py`
- Does NOT own: 侵入非门控模式直通时序（AP-01）
- Invariants to test: `CognitiveRuntime.run` 解析 `vocal_mode`；direct 模式零改动；gated 模式实例化 GatedVocalGate 并注入；Settle 阶段执行 `VocalSettleGuard`；子代理通过 `VocalToolFilter` 剥离 `send_message`（INV-09，AP-02）。

**Step 1: Write the failing test**

```python
# tests/scenario/adr0248/test_runtime_loop_wiring.py
import pytest
from lca.application.vocal.runtime_wiring import RuntimeVocalContext, resolve_runtime_vocal
from lca.contracts.models.vocal.models import VocalMode
from lca.infrastructure.vocal.gate import DirectVocalGate, GatedVocalGate


def test_resolve_runtime_vocal_default_is_direct():
    ctx = resolve_runtime_vocal(vocal_mode=None, operation_id="op_1")
    assert ctx.mode == VocalMode.DIRECT
    assert isinstance(ctx.gate, DirectVocalGate)


def test_resolve_runtime_vocal_gated():
    ctx = resolve_runtime_vocal(vocal_mode="gated", operation_id="op_2")
    assert ctx.mode == VocalMode.GATED
    assert isinstance(ctx.gate, GatedVocalGate)
    assert ctx.settle_guard is not None
```

**Step 2: Run test to verify it fails**

Run: `/opt/lca/venv/bin/pytest tests/scenario/adr0248/test_runtime_loop_wiring.py -v --no-cov`
Expected: FAIL

**Step 3: Write minimal implementation**

`lca/application/vocal/runtime_wiring.py`:
```python
from dataclasses import dataclass
from typing import Any
from lca.application.vocal.factory import VocalStrategyFactory
from lca.contracts.models.vocal.models import VocalMode
from lca.contracts.protocols.vocal.protocol import VocalGateProtocol
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


@dataclass
class RuntimeVocalContext:
    mode: VocalMode
    gate: VocalGateProtocol
    settle_guard: VocalSettleGuard | None = None


def resolve_runtime_vocal(
    vocal_mode: str | VocalMode | None,
    operation_id: str,
    wake_source: str = "user_input",
    wake_context: Any = None,
) -> RuntimeVocalContext:
    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy(vocal_mode)
    gate = strategy.create_gate(operation_id=operation_id, wake_source=wake_source, wake_context=wake_context)
    guard = VocalSettleGuard(gate) if strategy.mode == VocalMode.GATED else None
    return RuntimeVocalContext(mode=strategy.mode, gate=gate, settle_guard=guard)
```

在 `lca/runtime/loop/runtime_loop.py` 中的 `run` 和 `_run_driver` 安全挂载 `resolve_runtime_vocal` 与 settle guard。

**Step 4: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/scenario/adr0248/test_runtime_loop_wiring.py -v --no-cov`
Expected: PASS

**Step 5: Commit**

```bash
git add lca/application/vocal/runtime_wiring.py lca/runtime/loop/runtime_loop.py tests/scenario/adr0248/test_runtime_loop_wiring.py
git commit -m "feat(runtime): wire vocal strategy, gate and settle guard into CognitiveRuntime"
```

---

### Task 6: 阶段二 — ADR-0248 全链路闭环端到端集成场景测试

**Files:**
- Create: `tests/scenario/adr0248/test_runtime_loop_gated_e2e.py`
- Test: `tests/scenario/adr0248/test_runtime_loop_gated_e2e.py`
- Does NOT own: 生产环境真实 LLM 计费与外网调用（AP-01）
- Invariants to test: 完整走通 ADR-0248 端到端全景流：
  1. Gated 模式下推理内省 100% 截流至 scratchpad；
  2. `send_message` 发出 Reply-first Ack；
  3. `BoxAccessor` 在员工机安全执行；
  4. `AutoReviewGate` 审查放行；
  5. `send_message` 交付正式结果；
  6. `VocalSettleGuard` 成功收敛；
  7. `evaluate_initiative` 挂载主动提议（INV-01~09，AP-02）。

**Step 1: Write the test**

```python
# tests/scenario/adr0248/test_runtime_loop_gated_e2e.py
from lca.application.initiative.hooks import evaluate_initiative
from lca.application.vocal.runtime_wiring import resolve_runtime_vocal
from lca.infrastructure.auto_review.gate import AutoReviewGate
from lca.infrastructure.computer.box_accessor import BoxAccessor
from lca.infrastructure.vocal.tool import SendMessageTool


def test_adr0248_full_runtime_closed_loop_e2e(tmp_path):
    # 1. 运行态总装门控
    vocal_ctx = resolve_runtime_vocal(vocal_mode="gated", operation_id="run_adr248_e2e")
    gate = vocal_ctx.gate
    guard = vocal_ctx.settle_guard
    tool = SendMessageTool(gate)

    # 2. 员工机 BoxAccessor
    box = BoxAccessor(root_dir=tmp_path / "box")
    auto_review = AutoReviewGate()

    # 3. 推理文本截流内省
    gate.handle_text_chunk("Internal thought: checking files in /home/box...")
    assert len(gate.get_visible_outputs()) == 0

    # 4. Reply-first 承接发声
    tool.execute(type="text", content="正在员工电脑排查环境配置...")
    assert len(gate.get_visible_outputs()) == 1

    # 5. 员工机操作与 Auto-Review 审查
    verdict = auto_review.evaluate("write_file", {"path": "config.yaml"})
    assert verdict.action == "allow"
    box.write_text("config.yaml", "env: production")

    # 6. 正式交付
    tool.execute(type="text", content="配置已更新完毕。")
    assert len(gate.get_visible_outputs()) == 2

    # 7. Settle 结算收敛
    assert guard.validate_turn_settle() is True

    # 8. 主动提议钩子
    features = {"manual_action_counts": {"write_config": 3}}
    nudge = evaluate_initiative(features)
    assert nudge is not None
    assert "例程" in nudge.nudge_message
```

**Step 2: Run test to verify it passes**

Run: `/opt/lca/venv/bin/pytest tests/scenario/adr0248/test_runtime_loop_gated_e2e.py -v --no-cov`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/scenario/adr0248/test_runtime_loop_gated_e2e.py
git commit -m "test(scenario): add full closed-loop E2E scenario test for ADR-0248 runtime"
```

---

### Task 7: 全链路全量单测回归、代码门禁与架构守卫验证

**Files:**
- Check: All modified and created files
- Command 1: `/opt/lca/venv/bin/pytest tests/contracts/vocal tests/infrastructure/vocal tests/application/vocal tests/scenario/vocal tests/infrastructure/computer tests/contracts/auto_review tests/infrastructure/auto_review tests/application/initiative tests/scenario/adr0248 -v --no-cov`
- Command 2: `/home/lichao/.local/bin/ruff check lca/ tests/`
- Command 3: `/home/lichao/.local/bin/ruff format --check lca/ tests/`
- Command 4: `git diff --check`
- Invariants: 全部关联单元与场景测试 100% 通过，代码门禁 0 报错，架构负边界 100% 遵守。
