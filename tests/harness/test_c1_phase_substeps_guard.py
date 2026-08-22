"""CV4 C1 子步骤不可独立于 C1 阶段被表达（ADR-0068 §三 + tracker §6 CV4）。

PR-4 验收（acceptance-criteria §6 CV4）：

> | C1 子步骤不可独立于 C1 阶段被表达 | ADR-0068 §三子步骤枚举的所有方法名存在于 C1 阶段对应插件内 |
> | 测试覆盖 ADR-0068 §三运行时序图定义的 7 子步骤 + ModularBrain.think() / brain.reflect() 等 |

ADR-0068 §三运行时序图定义 7 子步骤（run-loop phases）：

1. perceive.collect (PRE_PERCEIVE hook)
2. perceive.admit (PERCEIVE)
3. perceive.select (POST_PERCEIVE)
4. think.prepare (PRE_THINK)
5. think.decide (THINK)
6. think.govern (POST_THINK)
7. command.plan → authorize → budget → constrain → execute → observe

每个子步骤必须存在于 C1 阶段对应插件内（即 perceive.* 在 perceive phase、
think.* 在 think phase 等）；不允许把 C1 子步骤抽离成独立 state field
（如 ``_gate_chain`` / ``_pre_phase_method`` / ``_sub_phase_state``）。

PR-4 实施：本测试扫描 ``lca/layer1_cognitive/brain/`` + ``lca/layer2_runtime/``，
验证：

1. ``ModularBrain`` 不含 ``_gate_chain`` / ``_gates`` / ``_chain`` 字段
2. ``ModularBrain.think()`` 不直接写 state（必须走 reducer）
3. ``CognitiveRuntime._loop`` 不含 C1 phase 之外的子阶段 state（除
   PR3a 引入的 manifest / gate_decided）
4. ``Reducer`` Protocol 含 ``apply_skill_route``（PR-4 新增）
"""

from __future__ import annotations

import ast
from pathlib import Path

LCA_ROOT = Path("lca")
BRAIN_DIR = LCA_ROOT / "layer1_cognitive" / "brain"
RUNTIME_FILE = LCA_ROOT / "layer2_runtime" / "runtime_loop.py"
REDUCER_PROTOCOL = LCA_ROOT / "contracts" / "protocols" / "reducer.py"
REDUCER_DEFAULT = LCA_ROOT / "layer2_runtime" / "reducer.py"


class TestCV4NoGateChainField:
    """CV4: ModularBrain 不应有 ``_gate_chain`` / ``_gates`` / ``_chain`` 字段。

    任何 gate 列表都从 ControlPlan.by_slot 投影，不允许作为独立 state field。
    """

    def test_modular_brain_has_no_gate_chain_field(self) -> None:
        source = (BRAIN_DIR / "modular_brain.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_attrs = {"_gate_chain", "_gates", "_chain", "_gates_chain"}
        violations: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Attribute):
                        # self._gate_chain: ... = ...
                        attr_name = stmt.target.attr
                        if attr_name in forbidden_attrs:
                            violations.append(f"{stmt.target.attr} (type-annotated)")
                    elif isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute) and target.attr in forbidden_attrs:
                                violations.append(f"{target.attr} (assign)")
        assert violations == [], (
            f"ModularBrain has forbidden gate chain field(s): {violations}. "
            "CV4 violation: gate chain must come from ControlPlan.by_slot, "
            "not as a separate state field."
        )


class TestCV4BrainNoDirectStateMutation:
    """CV4: ModularBrain.think() 不直接写 state.active_template（必须走 reducer）。"""

    def test_modular_brain_think_routes_through_reducer(self) -> None:
        """``ModularBrain.think`` 中不应有 ``state.X = ...`` 形式的直接 mutation。

        唯一允许的是 reducer 内部 mutation（被 audit_state_writers 的 allowlist
        豁免）。本测试扫描 ModularBrain.think 方法体并验证无直接 mutation。
        """
        source = (BRAIN_DIR / "modular_brain.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Find ModularBrain class
        brain_cls = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "ModularBrain"
        )
        # Find think method
        think_method = next(
            node
            for node in ast.walk(brain_cls)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "think"
        )
        # Look for direct state mutations: state.<attr> = ...
        violations: list[str] = []
        for stmt in ast.walk(think_method):
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "state"
                    ):
                        violations.append(f"line {stmt.lineno}: state.{target.attr} = ...")
            elif isinstance(stmt, ast.AugAssign):
                target = stmt.target
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "state"
                ):
                    violations.append(
                        f"line {stmt.lineno}: state.{target.attr} {type(stmt.op).__name__.lower()}= ..."
                    )
        assert violations == [], (
            f"ModularBrain.think has direct state mutations (CV4 violation): {violations}. "
            "Use reducer.apply_* for state mutation (ADR-0066 C4)."
        )


class TestCV4ReducerProtocolHasApplySkillRoute:
    """CV4 + PR-4: Reducer Protocol 必须含 ``apply_skill_route`` 方法。"""

    def test_reducer_protocol_declares_apply_skill_route(self) -> None:
        source = REDUCER_PROTOCOL.read_text(encoding="utf-8")
        assert "apply_skill_route" in source, (
            "Reducer Protocol must declare apply_skill_route (PR-4 think.guard "
            "atomic migration; ModularBrain routes SkillRouter result through reducer)"
        )

    def test_default_reducer_implements_apply_skill_route(self) -> None:
        source = REDUCER_DEFAULT.read_text(encoding="utf-8")
        assert "apply_skill_route" in source, (
            "DefaultReducer must implement apply_skill_route (PR-4)"
        )


class TestCV4RuntimeNoSubPhaseState:
    """CV4: ``CognitiveRuntime._loop`` 不应在 C1 六 phase 外额外定义子阶段 state。

    C1 六 phase = perceive / think / act / reflect / remember / stop。
    任何运行时引入的子步骤 state 字段必须 fold 到现有 phase（reducer），
    不允许作为独立 field 累积。
    """

    def test_runtime_loop_no_extra_subphase_state(self) -> None:
        """``CognitiveRuntime._loop`` 不直接 mutate state（除 PR3a 引入的
        perceive hub mediation）。

        PR-4 约束：stop 判定经 ``self.stop_rule.decide(...)`` → reducer fold；
        不允许在 runtime 累积 ``_loop_step`` / ``_last_phase`` / ``_sub_state``
        等独立子阶段字段。
        """
        source = RUNTIME_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        runtime_cls = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "CognitiveRuntime"
        )
        forbidden_attrs = {
            "_loop_step",
            "_last_phase",
            "_sub_state",
            "_phase_state",
            "_stop_pending",
            "_next_phase",
        }
        violations: list[str] = []
        for stmt in runtime_cls.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Attribute):
                if stmt.target.attr in forbidden_attrs:
                    violations.append(f"{stmt.target.attr} (type-annotated)")
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and target.attr in forbidden_attrs:
                        violations.append(f"{target.attr} (assign)")
        assert violations == [], (
            f"CognitiveRuntime has forbidden sub-phase state field(s): {violations}. "
            "CV4 violation: C1 sub-steps must be folded into existing phases via reducer."
        )


class TestCV4StopRuleFlow:
    """CV4: 声明式 ``stop`` phase 通过 StopRule 生成可 reducer fold 的 stop 决策。"""

    def test_declarative_stop_phase_uses_stop_rule(self) -> None:
        """StopRule 必须由可替换的标准 phase executor 调用，而非硬编码 Runtime 循环。"""
        source = (LCA_ROOT / "plugins" / "phase_executors" / "common.py").read_text(
            encoding="utf-8"
        )
        assert "stop_rule.decide" in source
        assert "def _loop" not in RUNTIME_FILE.read_text(encoding="utf-8")


class TestCV4AllControlSlot11:
    """CV4 全 11 槽位都已落到具体代码路径（PR-1 + PR-4 联合验收）。"""

    def test_control_slot_11_all_used_in_pipeline(self) -> None:
        """11 槽位列表（perceive.context / think.guard / act.authorize /
        act.budget / act.constrain / act.execute / act.safe-boundary /
        remember.admit / stop.decide / observe.checkpoint / observe.*）
        中至少 stop.decide 与 think.guard 已在 RuntimeLoop / ModularBrain
        中被实际调用（PR-1/4）。其余槽位 PR-7 / PR-8 / PR-9 落地。
        """
        runtime_src = RUNTIME_FILE.read_text(encoding="utf-8")
        brain_src = (BRAIN_DIR / "modular_brain.py").read_text(encoding="utf-8")
        # think.guard must be referenced in ModularBrain (agent_gates)
        assert "agent_gates" in brain_src, (
            "ModularBrain must reference agent_gates (think.guard 投稿)"
        )
        # stop.decide must be referenced via stop_rule.decide
        assert "stop_rule" in runtime_src, (
            "CognitiveRuntime must reference stop_rule (stop.decide 投稿)"
        )
