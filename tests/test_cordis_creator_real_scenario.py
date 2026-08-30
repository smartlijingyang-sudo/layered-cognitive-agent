"""Creator 四面端到端：CSV 统计 plugin 由 agent 自己创作、验证、发布并使用。

场景故事
--------
一个 cordis-creator agent 接到任务：「分析 sales.csv 的 monthly_total 列
统计信息」。环境里没有 csv_stats 工具 —— creator 必须：

1. think → 没有 csv_stats 工具；
2. cordis_control.inspect → 看到当前 Context 派生能力图；
3. file_write → 把 csv_stats.py 插件源码写到 preset 目录；
4. cordis_control.author → 读取 plugin 源并创建 DRAFT artifact；
5. cordis_control.validate → 将 artifact 转为 VERIFIED；
6. cordis_control.promote → 发布 artifact 并挂入 cordis Context；
7. csv_stats → 用刚挂载的新工具算 mean / median / std；
8. respond → 把结果输出给用户。

然后 **重启 session**（preset 自动加载），同一个 agent 接到同一任务：
- 不需要任何 Creator control 调用；
- 直接 csv_stats 工具已在 Context 中。

为什么这是真场景
-----------------
- **真实 plugin 源码**：写到磁盘 → 动态 import → factory() 实例化 → 注入 ctx；
- **真实数值计算**：csv_stats 用 Python statistics 库算 mean / median / std，
  不是 fake 数据；
- **真实 preset 复用**：第二个 session 真的从 preset 目录加载 bundle.yaml → 动态
  import → factory() 实例化 → 注入 ctx（不依赖任何 cordis_control 调用）；
- **真实 journal**：每次 Creator face 都落对应的 typed JournalEvent
  到 in-memory journal（可被 read_journal() 反序列化）；
- **真实 Tool 链路**：cordis_control.execute() → CreatorRuntime.promote() → Composer.mount() →
  ctx.provide() → ctx.own_bindings[plugin:xxx] 可被下一行代码读取。

驱动方式
--------
Agent 的 LLM 用脚本化 ``SequenceScriptedLLM``：按调用次序返回硬编码的
``use_tool(...)`` 决策；agent 的 think → act → reflect → remember → stop
循环据此驱动。**没有 mock 替代 Composer / Tool / preset 路径的任何一环**。
"""

from __future__ import annotations

import asyncio
import csv
import json
from collections.abc import AsyncIterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, NativeToolCall
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.observability.facade import BoundObservability, bind_backends
from lca.infrastructure.observability.journal_backend import MemoryJournal
from lca.application.preset_authoring import PresetAuthoring
from lca.plugins.providers.composition_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.roles.cordis_creator import build_cordis_creator_role_profile
from lca.plugins.tools.bash import build_bash_tool
from lca.plugins.tools.cordis_control import build_cordis_control_tool
from lca.plugins.tools.file_write import build_file_write_tool

# 测试隔离 scratch —— 避免写到用户 ~/.agent-presets
SCRATCH = Path(__file__).resolve().parent / ".scratch_cordis_creator_real"
SCRATCH.mkdir(exist_ok=True)


# ── 脚本化 LLM：按调用次序返回硬编码 use_tool 决策 ─────────────────


class SequenceScriptedLLM(LLMAdapter):
    """按调用次序返回 ``LLMResponse`` 列表的 LLMAdapter（用于 Creator 流程驱动）。

    - 每个 role 一个 script list；list 内每个 ``LLMResponse`` 是一次 LLM 调用结果。
    - role 从 prompt 中的 ``ROLE: <name>`` 头部提取（与既有 ScriptedLLMAdapter 一致）。
    - 列表耗尽后：若 ``default_respond=True`` 返回最后一次响应；否则抛 ``LookupError``。
    """

    name = "sequence-scripted-llm"

    def __init__(
        self,
        scripts: dict[str, list[LLMResponse]],
        *,
        default_respond: bool = True,
    ) -> None:
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self._cursors: dict[str, int] = {}
        self._default_respond = default_respond
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        role = self._extract_role(prompt) or "*"
        self.calls.append((role, prompt[:200]))
        seq = self._scripts.get(role) or self._scripts.get("*") or []
        idx = self._cursors.get(role, 0)
        if idx >= len(seq):
            if self._default_respond and seq:
                return seq[-1]
            raise LookupError(f"SequenceScriptedLLM exhausted for role={role!r}")
        self._cursors[role] = idx + 1
        return seq[idx]

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(prompt, **kwargs)
        if response.tool_calls:
            for tc in response.tool_calls:
                args_json = json.dumps(tc.arguments, ensure_ascii=False)
                yield LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=tc.call_id,
                    tool_name=tc.name,
                    arguments_delta=args_json,
                )
        else:
            for char in response.text:
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=char)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

    @staticmethod
    def _extract_role(prompt: str) -> str | None:
        import re

        m = re.search(r"^ROLE:\s*(.+)$", prompt, re.MULTILINE)
        return m.group(1).strip() if m else None


def _respond(text: str) -> LLMResponse:
    return LLMResponse(text=text, model="sequence-scripted-llm")


def _use_tool(name: str, args: dict[str, Any]) -> LLMResponse:
    return LLMResponse(
        text="",
        model="sequence-scripted-llm",
        tool_calls=[NativeToolCall(call_id=f"call_{name}", name=name, arguments=args)],
    )


# ── CSV + plugin 源（真实业务场景） ──────────────────────────────


def _write_sales_csv(path: Path) -> None:
    """造一份真实销售数据：monthly_total 数值列。"""
    rows = [
        ("month", "monthly_total"),
        ("2024-01", 12500),
        ("2024-02", 13200),
        ("2024-03", 11800),
        ("2024-04", 14000),
        ("2024-05", 15300),
        ("2024-06", 14750),
        ("2024-07", 16000),
        ("2024-08", 15500),
        ("2024-09", 16800),
        ("2024-10", 17200),
        ("2024-11", 16500),
        ("2024-12", 18900),
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


_CSV_STATS_PLUGIN_SOURCE = '''
plugin_meta = {
    "name": "csv_stats",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["tool_fs.read"],
    "side_effects": "none",
    "policy_class": "execute",
    "test_suite": "tests/test_csv_stats.py",
}


def factory():
    """返回一个对 CSV 列计算 mean / median / std 的工具函数。

    调用：``csv_stats(path="sales.csv", column="monthly_total")`` →
    返回 ``{"count": 12, "mean": 15204.17, "median": 15400.0, "stdev": 2070.84}``。
    """
    import csv as _csv
    import statistics as _stats
    from pathlib import Path as _P

    def _stats_for(path: str, column: str) -> dict[str, object]:
        p = _P(path)
        values: list[float] = []
        with p.open(encoding="utf-8", newline="") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                raw = row.get(column)
                if raw is None or raw == "":
                    continue
                values.append(float(raw))
        return {
            "path": path,
            "column": column,
            "count": len(values),
            "mean": round(_stats.mean(values), 2),
            "median": round(_stats.median(values), 2),
            "stdev": round(_stats.stdev(values), 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
        }

    return _stats_for
'''


@contextmanager
def bind_journal():
    journal = MemoryJournal()
    with bind_backends(BoundObservability(journal=journal)):
        yield journal


# ── 真场景 ──────────────────────────────────────────────────────


_SAFE_EXECUTORS: list[Any] = []  # 全局 safe_executor 注册（on_mounted 用）


def _register_safe_executor(safe_executor: Any) -> None:
    """让 on_mounted 回调能找到当前 session 的 safe_executor 以扩展 manifest。"""
    if safe_executor is not None and safe_executor not in _SAFE_EXECUTORS:
        _SAFE_EXECUTORS.append(safe_executor)


def _sync_safe_executor_manifest(*, tool_name: str) -> None:
    """把 ``tool_name`` 追加到所有已知 safe_executor 的 manifest.allowed_tools。"""
    for safe_executor in _SAFE_EXECUTORS:
        manifest = getattr(safe_executor, "permission_manifest", None)
        if manifest is not None and tool_name not in manifest.allowed_tools:
            manifest.allowed_tools = sorted(set(manifest.allowed_tools) | {tool_name})


def _install_tool_registry(*, agent: Any, tool_registry: Any) -> None:
    """把 ``tool_registry`` 装到 agent 的 body + action_handlers + 注册 safe_executor。

    计划绑定的 BodyComposer 根据编译后的行动权限和注入的 handler registry
    构造 ActionRegistry，并把同一份工具 registry 交给 ``UseToolOperation`` 与
    ``body.tool_registry``；safe executor 再按 RoleProfile.tool_permission_manifest
    的允许工具列表执行权限闸。

    同步四个引用：
    1. body.tool_registry —— body 自身的 registry；
    2. action_handlers._tool_registry —— 旧版 UseToolOperation 的直接引用；
    3. action_handlers._batch_executor._tool_registry —— 批次执行接缝的实际引用；
    4. safe_executor 注册到全局，让 on_mounted 动态扩展 manifest。
    """
    body = agent._agent.runtime.body
    body.tool_registry = tool_registry
    action_registry = getattr(body, "action_registry", None)
    if action_registry is not None:
        for action in action_registry._entries.values():
            inner = getattr(action, "_tool_registry", None)
            if inner is not None:
                action._tool_registry = tool_registry
            batch_executor = getattr(action, "_batch_executor", None)
            if batch_executor is not None:
                batch_executor._tool_registry = tool_registry
    safe_executor = getattr(body, "safe_executor", None)
    _register_safe_executor(safe_executor)
    # 同步 safe_executor manifest：把 tool_registry 当前所有 tool 的 name 全部并入
    if safe_executor is not None:
        manifest = getattr(safe_executor, "permission_manifest", None)
        if manifest is not None:
            try:
                tool_names = list(tool_registry.names())
            except Exception:
                tool_names = []
            existing = set(manifest.allowed_tools)
            for tool_name in tool_names:
                if tool_name not in existing:
                    existing.add(tool_name)
            manifest.allowed_tools = sorted(existing)


def _build_creator_toolkit(preset_root: Path):
    """构造 creator 工具集（cordis_control + file_write + bash + csv_stats preset）。

    返回 ``(tools_list, composer_instance, tool_registry)``，调用方在
    ``bind_journal()`` 块内使用以让 record() 落到 journal。

    on_mounted 回调：promote 成功后把新挂载的 instance 包成 Tool 并注册到
    ``tool_registry``（与 spawn_agent 的 fork_for_run 输出同一份 ToolsService），
    这样 agent 的下一次 ``use_tool("csv_stats", ...)`` 能命中。
    """
    from cordis import Context

    from lca.infrastructure.capability.tools import ToolsService

    ctx = Context()
    composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())

    # 公用的 ToolsService：cordis_control + file_write + bash + 新挂载的 csv_stats
    tool_registry = ToolsService()

    caller_grant = (
        "cordis_control.inspect",
        "cordis_control.author",
        "cordis_control.validate",
        "cordis_control.promote",
        "tool_fs.read",
        "tool_fs.write",
        "tool_bash",
        "file_write",
    )

    def _on_mounted(name: str, instance: Any, meta: dict[str, Any]) -> None:
        """把新挂载的 plugin 包成 Tool 并注册到 tool_registry。

        设计决策：mount 阶段已经过 cordis_control 的 C5 / PR12 / §23.2
        Creator 校验与 Composer policy 检查，safe_executor 的 permission_manifest.allowed_tools 检查是
        二级防御；对 Creator 模式而言新挂载的 tool 自动视为已授权
        （动态扩展 manifest 由 :func:`_sync_safe_executor_manifest` 兜底）。
        """
        tool_obj = _wrap_plugin_as_tool(name=name, instance=instance, meta=meta)
        tool_registry.register(tool_obj)
        # 动态扩展：每次 promote 后立即尝试扩展 safe_executor manifest
        _sync_safe_executor_manifest(tool_name=name)

    cordis_control = build_cordis_control_tool(
        composer=composer,
        caller_grant=caller_grant,
        actor_role="cordis-creator",
        preset_root=preset_root,
        on_mounted=_on_mounted,
    )
    file_write = build_file_write_tool()
    bash = build_bash_tool()

    tool_registry.register(cordis_control)
    tool_registry.register(file_write)
    tool_registry.register(bash)

    return [cordis_control, file_write, bash], composer, tool_registry


def _build_creator_toolkit_with_preset(preset_id: str, preset_root: Path):
    """第二 session：preset 已经 boot-loaded，cordis_control 不在工具集。

    返回 ``(tools_list, composer, tool_registry)`` —— 新 session 的 cordis
    Context 是全新构造；preset 在 boot 阶段通过 Composer.mount 注入，agent
    的工具集直接含 csv_stats（无需 cordis_control）。
    """
    from cordis import Context

    from lca.contracts.mechanisms.composition import PluginFactory
    from lca.infrastructure.capability.tools import ToolsService

    ctx = Context()
    composer = CordisComposer(ctx, invariant_checker=build_default_invariant_checker())
    tool_registry = ToolsService()

    # 读 preset bundle.yaml + 动态 import + 走 composer.mount（不调 cordis_control）
    bundle_path = preset_root / preset_id / "bundle.yaml"
    text = bundle_path.read_text(encoding="utf-8")
    import yaml

    entries = (yaml.safe_load(text) or {}).get("entries") or []
    assert entries, f"preset 无 entry：{preset_id}"
    entry = entries[0]
    plugin_name = entry["name"]
    plugin_path = preset_root / preset_id / entry["config"]["source_path"]

    import sys

    preset_root_str = str(preset_root)
    sys.path.insert(0, preset_root_str)
    try:
        module_name = entry["$module"]
        import importlib.util

        spec = importlib.util.spec_from_file_location(module_name, str(plugin_path))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        factory_callable = getattr(module, "factory", None) or getattr(
            module, f"{plugin_name}_factory", None
        )
        plugin_meta = dict(getattr(module, "plugin_meta", {}))
        composer.mount(
            PluginFactory(
                name=plugin_name,
                factory=factory_callable,
                plugin_meta=plugin_meta,
                source_path=str(plugin_path),
            ),
            caller_grant=("tool_fs.read",),  # preset mount 也走 C5 闸
            actor_role="preset-bootstrap",
        )

        # 第二 session 不再有 cordis_control —— preset 已自挂，agent 直接用 csv_stats
        file_write = build_file_write_tool()
        bash = build_bash_tool()

        # 把 preset 自挂的 csv_stats 注册到工具集（让 agent 的 use_tool 能命中）
        csv_instance = composer._ctx.own_bindings.get(f"plugin:{plugin_name}")
        assert csv_instance is not None
        csv_stats_tool = _wrap_plugin_as_tool(
            name=plugin_name, instance=csv_instance, meta=plugin_meta
        )
        tool_registry.register(csv_stats_tool)
        tool_registry.register(file_write)
        tool_registry.register(bash)
        # preset bootstrap 也调用 _sync_safe_executor_manifest 把 csv_stats 加入
        # 已知 safe_executor 的 manifest（_install_tool_registry 在 agent 构造后
        # 才会注册 safe_executor，所以这里手动同步）
        _sync_safe_executor_manifest(tool_name=plugin_name)
        return [file_write, bash], composer, tool_registry
    finally:
        with suppress(ValueError):
            sys.path.remove(preset_root_str)


def _wrap_plugin_as_tool(*, name: str, instance: Any, meta: dict[str, Any]) -> Any:
    """把 cordis Context 里的 plugin instance 包成 Tool Protocol 对象。

    PR12 要求 plugin_meta.implements 至少含 ``["Plugin"]``；这里我们额外
    加 ``["Tool"]`` 以让 SimpleBody 能 ``tool_registry.get(name)`` 命中。
    """
    from typing import ClassVar

    from lca.contracts.protocols import Tool

    description = str(meta.get("description") or f"plugin {name}")

    # 用 default-arg 技巧把外部 name 捕获进类作用域（Python 类体内不能直接
    # 读闭包变量；必须通过 default-arg 走一层）。
    def _plugin_as_tool_factory(
        plugin_name: str = name,
        plugin_instance: Any = instance,
        plugin_meta: dict[str, Any] = meta,
        plugin_description: str = description,
    ) -> type[Tool]:
        class _PluginAsTool(Tool):
            """把 plugin instance 包装成 Tool Protocol；execute() 直接调用。"""

            _name: ClassVar[str] = plugin_name
            _instance: ClassVar[Any] = plugin_instance

            @property
            def name(self) -> str:  # type: ignore[override]
                return self._name

            description: ClassVar[str] = plugin_description
            parameters: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    k: {"type": "string"}
                    for k in (
                        plugin_instance.__annotations__
                        if hasattr(plugin_instance, "__annotations__")
                        else []
                    )
                },
                "required": [],
            }
            is_idempotent: ClassVar[bool] = bool(plugin_meta.get("is_idempotent", True))
            default_timeout_s: ClassVar[int] = 30

            async def execute(self: Tool, args: dict[str, Any]) -> Any:
                from lca.contracts.atoms.ids import new_id
                from lca.contracts.models.core.decision import Observation

                if not args:
                    payload = plugin_instance()
                elif len(args) == 1:
                    value = next(iter(args.values()))
                    payload = plugin_instance(value)
                else:
                    payload = plugin_instance(**args)
                return Observation(
                    observation_id=new_id("obs"),
                    success=True,
                    payload=payload,
                )

            def validate(self: Tool, args: dict[str, Any]) -> str | None:
                return None

        return _PluginAsTool

    tool_cls = _plugin_as_tool_factory()
    instance_obj = tool_cls()
    instance_obj._name = name  # type: ignore[attr-defined]
    return instance_obj


class TestCreatorRealScenario:
    """§13.3 真场景：CSV stats plugin 由 agent 自创作 → mount → 使用 → preset 复用。"""

    def setup_method(self, _) -> None:
        """每个 test 前清空跨用例的 _SAFE_EXECUTORS 全局状态。"""
        _SAFE_EXECUTORS.clear()

    def test_creator_writes_csv_stats_plugin_and_uses_it(self) -> None:
        """单 session 端到端：creator 写 plugin → mount → csv_stats 真算统计。"""
        preset_root = SCRATCH / "real_session1"
        preset_root.mkdir(parents=True, exist_ok=True)
        sales_csv = SCRATCH / "sales.csv"
        _write_sales_csv(sales_csv)

        # Agent 期望 plugin 文件写到这里（preset 根目录 = preset_root）
        plugin_target = preset_root / "csv_stats" / "plugins" / "csv_stats.py"

        # ScriptedLLM：think → inspect → write → author → validate → promote → csv_stats → respond
        script = [
            _use_tool("cordis_control", {"action": "inspect"}),
            _use_tool(
                "file_write",
                {
                    "path": str(plugin_target),
                    "content": _CSV_STATS_PLUGIN_SOURCE,
                },
            ),
            _use_tool(
                "cordis_control",
                {"action": "author", "name": "csv_stats", "path": str(plugin_target)},
            ),
            _use_tool("cordis_control", {"action": "validate", "name": "csv_stats"}),
            _use_tool(
                "cordis_control",
                {
                    "action": "promote",
                    "name": "csv_stats",
                    "target_scope": "release",
                    "preset_id": "csv_stats",
                },
            ),
            _use_tool(
                "csv_stats",
                {"path": str(sales_csv), "column": "monthly_total"},
            ),
            _respond(
                "sales.csv monthly_total 统计完成：mean=15204.17, "
                "median=15400, stdev=2070.84, count=12."
            ),
        ]
        llm = SequenceScriptedLLM({"cordis-creator": script})

        # 构造工具集 + composer + in-memory journal
        with bind_journal() as journal:
            tools, composer, tool_registry = _build_creator_toolkit(preset_root)

            # 直接构造 CognitiveAgent：role=cordis-creator，goal/backstory 与
            # build_cordis_creator_role_profile() 对齐
            from lca.application.api import Agent

            role_profile = build_cordis_creator_role_profile()
            # 把 csv_stats 通过 on_mounted 注册到 tool_registry；agent 的
            # use_tool("csv_stats", ...) 会通过 spawn_agent → ToolsService 查找
            # —— 这条路径与 spawn_agent 的 fork_for_run 等价（同一份 ToolsService）
            agent = Agent(
                role=role_profile.role,
                goal=role_profile.goal,
                backstory=role_profile.backstory,
                tools=tools,
                llm=llm,
                observability=BoundObservability(journal=journal),
                max_steps=10,
            )
            _install_tool_registry(agent=agent, tool_registry=tool_registry)

            result = asyncio.run(
                agent.run(
                    f"分析 {sales_csv} 的 monthly_total 列的 mean / median / std。"
                    "如果环境里没有 csv_stats 工具，自己写一个。"
                )
            )

        # ── 行为断言 ──
        assert result.status == "completed", (
            f"agent 未完成：status={result.status}, error={result.error}"
        )
        assert result.output is not None and "15204.17" in result.output, (
            f"agent 输出不含统计结果：{result.output!r}"
        )

        # ── 真实副作用断言 ──
        # 1) plugin 源文件被写到磁盘（不是 in-memory 假数据）
        assert plugin_target.is_file(), f"plugin 源未落盘：{plugin_target}"
        written = plugin_target.read_text(encoding="utf-8")
        assert "csv_stats" in written and "factory()" in written

        # 2) release promote 通过 PresetAuthoring 写入 bundle.yaml
        bundle_path = preset_root / "csv_stats" / "bundle.yaml"
        assert bundle_path.is_file(), "preset bundle.yaml 未生成"
        bundle_text = bundle_path.read_text(encoding="utf-8")
        assert "csv_stats" in bundle_text
        assert "lca_agent_presets.csv_stats.plugins.csv_stats" in bundle_text

        # 3) composer 的 ctx.own_bindings 真有挂入的 plugin
        instance = composer._ctx.own_bindings.get("plugin:csv_stats")
        assert instance is not None, "plugin 未注入 cordis Context"
        result_payload = instance(str(sales_csv), "monthly_total")
        assert result_payload["count"] == 12
        assert result_payload["mean"] == 15204.17
        assert result_payload["min"] == 11800.0
        assert result_payload["max"] == 18900.0

        # 4) journal 含完整 audit 链
        ev_types = {s.event_type for s in journal.store.events}
        assert "PluginInspected" in ev_types  # Step 1 inspect
        assert "PluginAuthored" in ev_types  # Step 3 author（file_write 触发）
        assert "PluginMounted" in ev_types  # promote
        assert "PresetPublished" in ev_types  # release promote
        assert "ToolInvoked" in ev_types  # csv_stats 调用

        # 5) csv_stats ToolInvoked 事件 payload 含正确 tool_name + ok=true
        csv_invoked = [
            s
            for s in journal.store.events
            if s.event_type == "ToolInvoked" and getattr(s.event, "tool_name", "") == "csv_stats"
        ]
        assert len(csv_invoked) == 1
        ev = csv_invoked[0].event
        assert ev.ok is True
        # ADR-0101 PR-2:arguments_preview 字段已删除;真实参数走
        # ``arguments_ref`` evidence 平面或 inline ``arguments``。
        # 在 csv_stats 调用中 arguments 应含 ``column=monthly_total``。
        args_blob = ev.arguments or {}
        assert args_blob.get("column") == "monthly_total", (
            f"ToolInvoked.arguments 缺 column=monthly_total: {args_blob!r}; "
            f"arguments_ref={ev.arguments_ref!r}"
        )

        # ── 落 audit + journal walk 证据 ──
        _dump_session_evidence(
            journal=journal,
            session="real_session1",
            stage="creator-first-write",
        )

    def test_preset_reuse_in_new_session_no_cordis_control_needed(self) -> None:
        """第二 session：preset 已自挂，agent 直接用 csv_stats，不调 Creator control。

        关键约束：
        - 不调 cordis_control（preset 在 boot 阶段已自动挂入 csv_stats）；
        - agent 直接 use_tool("csv_stats", ...) 应成功。
        """
        preset_root = SCRATCH / "real_session2"
        preset_root.mkdir(parents=True, exist_ok=True)
        sales_csv = SCRATCH / "sales.csv"
        if not sales_csv.exists():
            _write_sales_csv(sales_csv)

        # ── 阶段 0：先用真实 composer 写一个 preset（模拟上次 session 留下的产物）──
        bootstrap_preset_dir = preset_root / "csv_stats" / "plugins"
        bootstrap_preset_dir.mkdir(parents=True, exist_ok=True)
        plugin_path = bootstrap_preset_dir / "csv_stats.py"
        plugin_path.write_text(_CSV_STATS_PLUGIN_SOURCE, encoding="utf-8")
        # 把 PresetAuthoring 的 bundle.yaml 也写好
        PresetAuthoring.publish(
            preset_id="csv_stats",
            plugin_name="csv_stats",
            plugin_id="csv_stats",
            plugin_source=_CSV_STATS_PLUGIN_SOURCE,
            plugin_meta={
                "name": "csv_stats",
                "capabilities": ["tool_fs.read"],
                "policy_class": "execute",
            },
            actor_role="preset-bootstrap",
            root=preset_root,
        )

        # ── 阶段 1：第二 session —— agent 用 csv_stats 不需要 cordis_control ──
        # 关键差异：脚本里只有 use_tool("csv_stats", ...) + respond；没有 Creator control 步骤
        script = [
            _use_tool(
                "csv_stats",
                {"path": str(sales_csv), "column": "monthly_total"},
            ),
            _respond(
                "重读 sales.csv monthly_total：count=12, mean=15204.17, "
                "median=15400.0, stdev=2070.84。"
            ),
        ]
        llm = SequenceScriptedLLM({"cordis-creator": script})

        with bind_journal() as journal:
            # 这一 session 的 cordis Context 是全新的，但 preset 在 boot 阶段已注入
            tools, composer, tool_registry = _build_creator_toolkit_with_preset(
                "csv_stats", preset_root
            )
            # 关键断言工具集不含 cordis_control —— 因为新 session 不再需要它
            tool_names = [t.name for t in tools]
            assert "cordis_control" not in tool_names, (
                f"新 session 工具集应不含 cordis_control（preset 自动挂载已足够），got={tool_names}"
            )
            assert "csv_stats" not in tool_names, (
                "csv_stats 是 preset 挂入 ctx 的 instance 后再 wrap 进 tool_registry"
            )

            from lca.application.api import Agent

            agent = Agent(
                role="cordis-creator",
                goal="分析 CSV 统计",
                backstory="",
                tools=tools,
                llm=llm,
                observability=BoundObservability(journal=journal),
                max_steps=5,
            )
            # 注入 preset 自挂后的 tool_registry（已含 csv_stats + file_write + bash）
            _install_tool_registry(agent=agent, tool_registry=tool_registry)
            result = asyncio.run(agent.run(f"再分析一次 {sales_csv} 的 monthly_total 列统计"))

        # ── 断言 ──
        assert result.status == "completed", f"agent 未完成：{result.status}, {result.error}"
        assert result.output is not None
        assert "15204.17" in result.output

        # journal 里 csv_stats ToolInvoked 至少出现 1 次
        csv_invoked = [
            s
            for s in journal.store.events
            if s.event_type == "ToolInvoked" and getattr(s.event, "tool_name", "") == "csv_stats"
        ]
        assert len(csv_invoked) == 1
        assert csv_invoked[0].event.ok is True

        # journal 里 **不**应有 cordis_control ToolInvoked（关键反证）
        cordis_invoked = [
            s
            for s in journal.store.events
            if s.event_type == "ToolInvoked"
            and getattr(s.event, "tool_name", "") == "cordis_control"
        ]
        assert cordis_invoked == [], (
            f"新 session 不应再调用 cordis_control，但 journal 含 {len(cordis_invoked)} 条"
        )

        # preset-bootstrap 期间 Composer.mount 是内部动作（不走 cordis_control），
        # 故 PluginMounted 事件不会自动落；这是设计：PluginMounted 是 user-facing
        # 边界事件（Tool 层 emit），preset bootstrap 是 system-level mount。
        # 但 composer 的内部状态应反映挂载：ctx.own_bindings 应有 plugin:csv_stats。
        composer_ctx = composer._ctx.own_bindings
        assert composer_ctx.get("plugin:csv_stats") is not None, (
            "preset bootstrap 应把 csv_stats 注入 cordis Context"
        )

        _dump_session_evidence(
            journal=journal,
            session="real_session2",
            stage="preset-reuse",
        )


def _dump_session_evidence(*, journal: MemoryJournal, session: str, stage: str) -> None:
    """把 captured journal dump 到 SCRATCH，便于 verifier 复核 / 调试回溯。"""
    import dataclasses

    out_dir = SCRATCH / "evidence"
    out_dir.mkdir(exist_ok=True)
    jsonl_path = out_dir / f"{session}__{stage}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for stamped in journal.store.events:
            record = {
                "schema": "journal.v1",
                "seq": stamped.seq,
                "ts": stamped.ts,
                "scope": dataclasses.asdict(stamped.scope),
                "event_type": stamped.event_type,
                "event": dataclasses.asdict(stamped.event),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
