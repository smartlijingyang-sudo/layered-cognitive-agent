# ADR-0211 — Worker Contract 收紧：execute 签名、Config 边界、错误三态、register_worker / seams / body_provider 退役契约

> **状态：** **Proposed — 2026-09-09**
>
> **一句话**：把 ADR-0209 §1.2「节点即 LCA plugin」从「模块形态」落到「签名契约」—— Worker `execute(*, ctx)` keyword-only、typed 入出、`Config` 仅放静态值且不放端口名、错误三态(Success / Skip / raise)、`register_worker` / `Seams` / `body_provider.get_body` 三个旧入口一次性退役；与 ADR-0206 C13 信息血统闭合、ADR-0093 持续执行控制面、ADR-0110 插件合约统一化、ADR-0209 lab 收编形成同一决策的执行切片。
>
> **Review：** 待评审。
>
> **落地切片（2026-09-09）：** 本 ADR 是 ADR-0209 §1.6 删除清单的**契约层**收口（0209 给文件清单，本 ADR 给签名清单）；代码改动与 ADR-0209 PR-D final 2/2 同一系列推进。
>
> **Accepted 闸门：**
> 1. §5 Worker 三原则全部落到 `lca/plugins/lab/**/plugin.py` 真实 carrier（act 5 个 + think 4 个 + reflect 3 个 + remember 4 个 + perceive 6 个 + control 14 个 + 其它 53 个，89 个 carrier 全部对齐）
> 2. §6 退役清单 5 条全部 delete(同 PR 系列收口；不留跨 PR 后门)
> 3. §7 错误三态全部节点支持 `Config.on_error` 字段；runner / interpreter 读 on_error 决定 fail/retry/route
> 4. §8 lint-imports `lab-worker-purity` 规则落地;`rg "execute\\(self, node, inputs" lca/plugins/lab/` = 0;`rg "register_worker\\|Seams\\|body_provider\\|get_body" lca/plugins/lab/` = 0
> 5. ADR-0209 §6 delete-when 全 7 条满足(本 ADR 是 §1.6 + §1.7 退役清单的契约层收口)
> 6. ADR-0209 升 Accepted

**编号**：0211(0206 / 0207 / 0208 / 0209 / 0210 已占用;0209 §"Required follow-ups" 未显式列本 ADR,但 §1.2 / §1.6 是本 ADR 的契约层依赖)。

**关系**：

- **Builds on**：ADR-0004 Protocol-First、ADR-0015 contracts 无行为、ADR-0061 Manifest Resolve/Boot、ADR-0062 Plugin 运行时收口、ADR-0093 持续控制面、ADR-0110 插件合约统一化、ADR-0186 Session SSOT、ADR-0194 Loop 收敛、ADR-0195 平台架构收敛、ADR-0206 信息图内核、ADR-0209 agent_lab → LCA plugin 体系收编、ADR-0210 阶段闭集迁移。
- **Refines**：ADR-0209 §1.2「节点即 LCA plugin」(从模块形态到签名契约)、§1.3「装配唯一 = Profile/Bundle」(从图层到 execute 调用层)、§1.6 删除清单(从文件清单到签名清单)。
- **Supersedes**：无(无 ADR 决定过 Worker.execute 签名形态;本 ADR 是首次立契约)。
- **Reject**：「`execute(self, node, inputs, seams=None)` 继续存在只是少传 seams」;「在 `__init__` 里塞 typed handles」;「用 `if ctx is None: raise` 兜底」;「Config 里放端口名(`from`/`to`)」;「Worker 自己写 try/except 折 receipt」;「`register_worker` 当 fallback 留 compat shim」;「`Seams` 当 runtime typed handle 留 compat shim」;「`body_provider.get_body()` 当函数留 compat shim」(以上三条直接违反 ADR-0209 §1.6 / §7 Reject 「deprecated 不删除 = 跨 PR 后门」)。

**理由**：ADR-0209 已规定「节点即 LCA plugin、Profile/Bundle 是装配根、节点正文不许 new 装配品」,但只规定了**模块形态**(一个 `@plugin` 文件 = 一个 Worker),**没规定 execute 签名形态**。当前 89 个 carrier 全部走 `execute(self, *, ctx: PluginContext)` 或 `execute(self, node, inputs, seams=None)`,signature 不诚实、Config 与端口名混杂、错误处理散落;既违反 ADR-0093 §验收「capability grant 不扩大」、ADR-0110 §"PluginContract 真正成为插件侧唯一合约"、ADR-0206 §3 C13「信息血统闭合」,也让 §5 Worker 三原则无法落地。本 ADR 把 0209 §1.2 落到契约层:Worker signature / Config / 错误 / 退役 四件一组,一次性收口。

---

## 0. 第一性原理:问题本质

### 0.1 现状的三类不清晰

| 维度 | 现状(89 个 carrier 的真实形态) | 问题 | 不变量违反 |
|---|---|---|---|
| **execute 签名** | `execute(self, node, inputs, seams=None)`(act 6/6、perceive 6/6、think 4/4) 或 `execute(self, *, ctx: PluginContext)`(control 14/14、passthrough 18/18) | 签名不诚实;`seams` 写进签名但 4/6 worker 不用;`node` / `inputs` 是「框架容器」藏 typed args;读者一眼看不出函数**真**依赖什么 | ADR-0110 §"PluginContract 真正成为插件侧唯一合约"、ADR-0206 §3 C13 |
| **Config 内容** | `Config` 既放白名单(`allow: tuple[str, ...]`)、又放端口名(`from: str = "intent"` / `to: str = "authorized"`)、又放错误策略(`on_error: str = "fail"`) | 静态值 + 端口名 + 行为开关混杂;Config 不应感知端口名(那是图的事) | ADR-0061 Manifest 契约、ADR-0209 §1.3 |
| **错误处理** | Worker 自己 try/except(act.execute 折 receipt、act.observe 三态 if-elif、act.dispatch 自己当路由器) | 「错误策略」散在每个 worker;同图错误风格不统一 | ADR-0206 §5.6「错误处理是路由边,不是 try/catch」、ADR-0093 §持续执行控制面 |

### 0.2 本质命题

1. **签名 = 真实依赖**:Worker.execute 的所有参数 keyword-only、每个入参是 typed Protocol / frozen dataclass;`seams` / `node` / `inputs` / `ctx` 这种「框架容器」在**签名外**由 framework 投影成命名参数。
2. **Config ≠ 端口名**:`Config` 是 Pydantic frozen + `extra="forbid"`,**只放静态值**(白名单、阈值、模式);端口名(`from` / `to`)由图 spec 表达,不放 Config。
3. **错误策略在图,不在 worker**:Worker 只表达三种情况之一(`Success(value)` / `Skip(reason)` / raise);framework 按 `Config.on_error` 把 raise 转成 fail/retry/route(对应 ADR-0206 §5.6 错误路由边)。
4. **`register_worker` / `Seams` / `body_provider.get_body` 一次性退役**:三件都属于「让 worker / runner / 装配根知道框架协议」的债;同 PR 系列删除,不留 compat shim(ADR-0209 §1.6 / §7 Reject 已禁止跨 PR 后门)。
5. **Worker 不感知上下文层级**:Worker 拿到的入参是「已投影 + 已类型化」的值;framework 在调用前负责类型校验、scope 投影、redact、缺值 fail-loud;Worker 内部不写 `if x is None: ...` / `getattr(x, "content", {})` 这类防御代码。

### 0.3 删除条件

若全部满足:
1. §5 Worker 三原则全部 89 个 carrier 落地(`execute(self, *, ...)` keyword-only、typed 入出、Config 不放端口名)
2. §6 退役清单 5 条全部 delete(同 PR 系列收口)
3. §7 错误三态全部节点支持 `Config.on_error`
4. §8 lint-imports `lab-worker-purity` 规则落地
5. ADR-0209 §6 delete-when 全 7 条满足
6. ADR-0209 升 Accepted

本文降为附录。

---

## 1. 决策(最终采纳什么)

### 1.1 Worker.execute 签名契约

```python
# lca/plugins/lab/act/shape/plugin.py —— 完整文件示例
"""act.shape — Decision → Intent。

做什么:把上游 Decision 字典重排成本阶段 Intent schema。
不做什么:不算 verdict、不调框架、不产出 Observation。
"""
from __future__ import annotations
from dataclasses import dataclass

from lca.contracts.act.intent import Intent
from lca.contracts.act.decision import Decision


class Config(BaseModel):
    """act.shape 节点的静态配置。

    不放端口名(那是图的事);不放行为开关(on_error 是 §7 框架字段,framework 读)。
    """
    model_config = {"extra": "forbid"}
    # 静态值示例:暂无;未来若加 schema 选择器放这里。


@plugin(
    id="lab.act.shape",
    provides=["lab.act.shape.out:intent"],
    requires=["lab.act.execute.in:decision"],   # 同图上游;framework 自动连
    layer="L4",
    effects=EffectClass.NONE,
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(...),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    ctx.provide("lab.act.shape", _ShapeWorker(config))


class _ShapeWorker:
    def __init__(self, config: Config) -> None:
        self._config = config

    def execute(self, *, decision: Decision) -> Intent:
        # ─── 全 keyword-only、typed 入出、纯协议调用 ───
        c = decision.content
        return Intent(
            action_type=c.get("action_type", ""),
            tool=c.get("tool"),
            args=dict(c.get("args", {})),
            effect_kind=c.get("effect_kind", "use_tool"),
        )
```

**强约束(必须满足,违反 = lint 失败):**

1. **全部 keyword-only**(`*,` 必现)。
2. **每个入参是 typed 类型**:`Decision` / `Intent` / `BodyHandle` / `Observation` 等 frozen dataclass 或 typed Protocol;**不写 `dict` / `Any`**(允许 `dict[str, object]` 这种 typing 泛型)。
3. **返回值是 typed 类型**:`Intent` / `Observation` / `Receipt` 等;**不返回 `dict[str, Artifact]`**。
4. **`ctx: PluginContext` / `seams: Seams` / `node: InfoNode` / `inputs: dict[str, Artifact]` 不进 Worker.execute 签名**;framework 在调用前完成投影。
5. **`on_error` / `from` / `to` 等框架字段不进 Config**;framework 从图 spec 读 on_error、从图 spec 读 from/to。

### 1.2 Config 收紧

```python
class Config(BaseModel):
    model_config = {"extra": "forbid"}
    # 只放静态值
    allow: tuple[str, ...] = ()             # 白名单(act.authorize 用)
    on_error: Literal["fail", "retry", "route"] = "fail"   # §7 框架字段
    max_retries: int = 3                    # on_error=retry 时用
    route_to: str | None = None             # on_error=route 时用
```

**强约束:**

1. `model_config = {"extra": "forbid"}`(Pydantic frozen)。
2. **不放端口名**:`from: str = "intent"` / `to: str = "authorized"` 这种字段**禁止**;端口名由图 spec 表达(`node.ins` / `node.outs`)。
3. **不放 framework 句柄**:`body: Body` / `seams: Seams` / `ctx: PluginContext` 这种字段**禁止**;framework 通过 `@plugin(requires=...)` 声明,setup 阶段 `ctx.require(...)` 拿。
4. **on_error / max_retries / route_to 是 §7 错误三态框架字段**,由 framework 读,Worker execute **不读**(违反 = lint)。
5. **不放行为开关/全局状态**;静态值 = 白名单 / 阈值 / 模式字符串。

### 1.3 错误三态

| 状态 | Worker 表达 | framework 处理 |
|---|---|---|
| **Success** | `return Success(value)` 或直接 `return value` | 写 `node_end(status="ok")`;继续 |
| **Skip** | `return Skip(reason="verdict_skip")` | 写 `node_end(status="skipped", reason=...)`;继续(下一节点) |
| **Raise** | 任意异常 | 读 `Config.on_error`:<br>- `fail` → 写 `node_end(status="error")` + raise;<br>- `retry` → 按 `Config.max_retries` 重试(transient 退避,deterministic 不重试,见 ADR-0206 §5.6);<br>- `route` → 写 EXCEPTION artifact → 投到 `Config.route_to` 节点的第一个 IN |

**强约束:**

1. Worker **不写 try/except**;异常自然冒到 framework(违反 = lint)。
2. Worker **不折 receipt / EXCEPTION**;framework 收口(违反 = lint)。
3. `Config.on_error` 默认 `"fail"`;`retry` / `route` 必须显式声明。
4. `route` 必须显式 `route_to: str`;不声明 = 编译失败(防漏配)。
5. `Skip` 是**主动**跳过(verdict=skip / no_effect);framework 区分 Skip 与 Raise(前者继续,后者按 on_error)。

### 1.4 旧入口退役清单

| 入口 | 退役原因 | 同 PR 替代 |
|---|---|---|
| `lca/plugins/lab/internal/worker.py::_WORKERS` 全局表 | 「Worker 如何被发现」是框架职责,不该在 worker 模块写 `register_worker(...)` | framework 用 `discover_worker(module_path)` + `@plugin` 装饰器读 `id` / `provides` / `requires` |
| `register_worker(factory, cls)` 函数 | Worker 模块不再做注册 | `@plugin` 装饰器 + cordis setup 是唯一注册路径 |
| `lookup_worker(factory)` / `bind_factory_aliases` / `_ALIAS_TO_CANONICAL` / `_CANONICAL_TO_ALIASES` | `factory:` 字段值直接 = `@plugin` 的 `id`;不需要别名解析 | graph compile `resolve_plugin_id(factory)` 直接查 `@plugin` registry |
| `agent_lab/runtime/seams.py::Seams` typed handle | 「runner 给 worker 句柄」违反 §5 原则 1(签名 = 真实依赖);Worker 不该知道 runner 协议 | framework 在调用前完成 typed 投影;Worker 拿 typed 入参 |
| `agent_lab/runtime/runner.py::_default_seams()` | runner 偷偷懂 body_provider | framework 的 `_build_ctx_for_node(node_id)` 按 §1.5 cordis_bridge 投影 |
| `lca/plugins/lab/act/body_provider/plugin.py::get_body()` 函数 | 「装配品构造在节点外函数」违反 ADR-0209 §1.3 / §5 Worker 原则 3 | `act.compose` 节点化;`@plugin(requires=["lab.tool_registry", "lab.safe_executor", "lab.transport", "lab.plan_ref"])` 在 setup 阶段装配,execute 阶段只 `body.act(decision=...)` |
| `if seams is None: raise RuntimeError(...)` 模式(act.execute / act.body / act.dispatch) | Worker 不该校验 runner 协议 | framework 在调用前 fail-loud(类型校验失败 → raise);Worker 不感知 |

### 1.5 cordis_bridge:framework 投影层

```python
# lca/plugins/lab/internal/cordis_bridge.py —— framework 职责
def build_execute_kwargs(worker: Worker, *, ctx: PluginContext) -> dict[str, Any]:
    """按 Worker.execute 签名 + @plugin.requires,自动从 ctx 取 typed values。

    强约束:
    1. 读 inspect.signature(worker.execute),按参数名查 ctx
    2. ctx.get(name) 在 §5 原则 1 保证 typed(framework require 阶段已 enforce)
    3. 缺值 → fail-loud(MissingCapabilityError,与 ADR-0093 §6 一致)
    4. 不做类型强转(Worker 拿到的是 typed 值,不是 raw ctx/Artifact)
    """
    sig = inspect.signature(worker.execute)
    kwargs: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            raise WorkerContractError(
                f"worker {type(worker).__name__}.execute 参数 {name!r} 非 keyword-only"
            )
        if name not in ctx:
            raise MissingCapabilityError(
                f"worker {type(worker).__name__}.execute 声明要 {name!r},"
                f"ctx 缺该 capability(检查 @plugin(requires=...))"
            )
        kwargs[name] = ctx[name]
    return kwargs
```

**强约束:**

1. Worker.execute 签名必现 `*` 之前的 keyword-only;否则 `WorkerContractError` 编译失败。
2. Worker.execute 入参名必须在 `@plugin(requires=...)` 里声明;否则 `MissingCapabilityError` 启动失败。
3. framework 不做 `if x is None` / `getattr(x, "content", {})` 这类兜底;fail-loud。
4. framework 不做 dict → typed 的强转;typed 校验由 Pydantic / Protocol 在 require 阶段完成。

---

## 2. 词汇表(受控命名)

| 词根 | 定义 | 不变量 |
|---|---|---|
| **Worker.execute signature** | `execute(self, *, arg1: Type1, arg2: Type2) -> ResultType` | keyword-only、typed 入出、无框架容器 |
| **Config** | Pydantic frozen + `extra="forbid"`,只放静态值 | 不放端口名 / framework 句柄 / 行为开关 |
| **Success / Skip / Raise** | Worker 三态返回值或行为 | Worker 不写 try/except;framework 按 on_error 处理 Raise |
| **`on_error`** | `Config.on_error: Literal["fail", "retry", "route"]` | framework 读,Worker 不读;默认 `"fail"` |
| **`cordis_bridge`** | framework 投影层,按 Worker.execute 签名自动从 ctx 取 typed values | 缺值 fail-loud;不做类型强转 |
| **`discover_worker`** | framework 读 `@plugin` 装饰器的 `id` / `provides` / `requires` 元数据 | 不调 `register_*`;唯一发现路径 |
| **退役入口** | `register_worker` / `Seams` / `body_provider.get_body` 三件 | 同 PR 删除,不留 compat shim |

---

## 3. 不变量

| ID | 不变量 | 落点 |
|---|---|---|
| **W-1** | Worker.execute **全 keyword-only**(必现 `*,`);任一参数非 keyword-only = lint 失败 | ruff 自定义规则 + `cordis_bridge` 启动校验 |
| **W-2** | Worker.execute 入参必是 typed 类型(`dict` / `Any` 禁);返回必是 typed 类型 | ruff 自定义规则 + mypy |
| **W-3** | `ctx` / `seams` / `node` / `inputs` / `Artifact` **不进** Worker.execute 签名 | ruff 自定义规则 + `cordis_bridge` 启动校验 |
| **W-4** | Config 不放端口名(`from` / `to` / `port` 等);端口名由图 spec 表达 | ruff 自定义规则 + Pydantic `extra="forbid"` |
| **W-5** | Config 不放 framework 句柄(`body` / `seams` / `ctx`);framework 通过 `@plugin(requires=...)` 声明 | ruff 自定义规则 |
| **W-6** | `Config.on_error` 默认 `"fail"`;`retry` / `route` 必显式声明;`route` 必声明 `route_to` | Pydantic validator + framework 启动校验 |
| **W-7** | Worker.execute **不写 try/except**;异常自然冒到 framework | ruff 自定义规则 + code review |
| **W-8** | Worker.execute **不折 receipt / EXCEPTION**;framework 收口 | ruff 自定义规则 + code review |
| **W-9** | `register_worker` / `Seams` / `body_provider.get_body` **三件同 PR 删除**;不留 compat shim | rg 检查 + ADR-0209 §1.6 + §7 Reject |
| **W-10** | framework 不做 `if x is None` / `getattr(x, "content", {})` 兜底;fail-loud | ruff 自定义规则 + `cordis_bridge` 实现 |

---

## 4. act 节点迁移示例(`act.execute` Before / After)

### 4.1 Before(`lca/plugins/lab/act/execute/plugin.py` 当前形态)

```python
class Config(BaseModel):
    model_config = {"extra": "forbid"}
    on_error: str = "fail"                       # Config 放行为开关(违反 W-4)


@plugin(
    id="lab.act.execute",
    provides=["lab.act.execute.out:receipt"],
    requires=[
        "lab.act.authorize.out:authorized",
        "lab.body",                              # 旧:要 framework 句柄
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
    ],
    layer="L4",
    effects=EffectClass.WORLD,
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    register_worker("act.execute", _ActExecute)             # 违反 W-9
    register_worker("lab.act.execute", _ActExecute)


class _ActExecute(Worker):
    factory = "lab.act.execute"

    def execute(self, node, inputs, seams=None):             # 违反 W-1 / W-2 / W-3
        if seams is None:                                     # 违反 W-10
            raise RuntimeError(
                "lab.act.execute requires a typed Seams handle from the runner"
            )
        intent_a = inputs.get("authorized")                   # 违反 W-2(用 dict)
        content = (
            intent_a.content                                  # 违反 W-2 / W-3(用 Artifact.content)
            if intent_a is not None and isinstance(intent_a.content, dict)
            else {}
        )
        tool_name = content.get("tool")
        try:                                                  # 违反 W-7 / W-8
            result = seams.body.act(intent=content, plan_ref=seams.plan_ref)
            return {
                "receipt": Artifact(...)                      # 违反 W-2(返回 dict[str, Artifact])
            }
        except Exception as exc:                              # 违反 W-7
            return {
                "receipt": Artifact(
                    kind=ArtifactKind.RECEIPT,
                    content={"status": "error", ...},         # 违反 W-8
                    schema_ref="tool.receipt.v1",
                )
            }
```

### 4.2 After(本 ADR 落地后)

```python
"""act.execute — BodyHandle → Observation(world 效应唯一出口)。

做什么:对一次授权意图调一次 handle。
不做什么:不装配、不处理异常、不写 receipt、不调其它 worker。
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

from lca.contracts.act.body_handle import BodyHandle
from lca.contracts.act.intent import Intent
from lca.contracts.act.observation import Observation
from lca.harness.plugin_api import PluginContext, plugin, PluginKind
from lca.contracts.harness.composition.plugin_contract import (
    PluginContract, PluginIdentity, ArchitectureContract,
    AuthorityContract, LifecycleContract, EvidenceContract,
)
from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.atoms.enums.effects import EffectClass


class Config(BaseModel):
    """act.execute 节点的静态配置。

    不放端口名(那是图的事);不放行为开关(on_error 是 §7 框架字段)。
    """
    model_config = {"extra": "forbid"}
    on_error: Literal["fail", "retry", "route"] = "fail"
    max_retries: int = 3
    route_to: str | None = None


@plugin(
    id="lab.act.execute",
    provides=["lab.act.execute.out:observation"],
    requires=[
        "lab.act.authorize.out:authorized",     # 同图上游(framework 自动连)
        "lab.act.compose.out:body_handle",      # 同图装配节点(framework 自动连)
    ],
    layer="L4",
    effects=EffectClass.WORLD,
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.ACT_EXECUTE,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("lab.act.execute.out:observation",)),
        observability=EvidenceContract(
            descriptors=("lab.act.execute.completed", "lab.act.execute.failed"),
        ),
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Cordis 终态:Worker 实例在 boot 已被 cordis 构造好,execute 时通过 ctx 拿 typed values。"""
    ctx.provide("lab.act.execute", _ExecuteWorker(config))


class _ExecuteWorker:
    def __init__(self, config: Config) -> None:
        self._config = config

    def execute(
        self,
        *,
        intent: Intent,                          # keyword-only、typed 入参
        body: BodyHandle,                        # keyword-only、typed 入参
    ) -> Observation:                            # typed 返回
        # ─── 全 keyword-only、typed 入出、纯协议调用 ───
        # 异常自然冒到 framework,framework 按 Config.on_error 处理
        return body.act(decision=intent)
```

**对比清单:**

| 维度 | Before | After | 不变量 |
|---|---|---|---|
| execute 签名 | `(self, node, inputs, seams=None)` | `(self, *, intent: Intent, body: BodyHandle) -> Observation` | W-1 / W-2 / W-3 |
| Config 内容 | 放 `on_error` 但不放 route_to / max_retries | 放 `on_error` + `max_retries` + `route_to`,不放端口名 | W-4 / W-5 / W-6 |
| 错误处理 | 自己 try/except 折 receipt(2 个 return 路径) | 不写 try/except;framework 按 on_error 处理 | W-7 / W-8 |
| 入口 | `register_worker` 双写 + `if seams is None` 兜底 + `body_provider` 间接 | `@plugin` 单写 + framework fail-loud + act.compose 节点化 | W-9 / W-10 |
| 返回值 | `dict[str, Artifact]`(自己包 Artifact) | `Observation` typed | W-2 |
| 装配 | `seams.body.act(intent=..., plan_ref=seams.plan_ref)` | `body.act(decision=intent)`(BodyHandle 自己拿 plan_ref) | W-3 / W-9 |

---

## 5. Worker 三原则(写进 ADR / docs / lint)

### 5.1 原则 1:签名 = 真实依赖

```python
# ✅ 清晰
def execute(self, *, decision: Decision, body: BodyHandle) -> Observation:
    ...

# ❌ 现在这种
def execute(self, node, inputs, seams=None):    # 全是 Any,什么都不敢说
    ...
```

### 5.2 原则 2:Config ≠ 端口名 ≠ 框架句柄

```python
# ✅ Config 只放静态值
class Config(BaseModel):
    model_config = {"extra": "forbid"}
    allow: tuple[str, ...] = ()
    on_error: Literal["fail", "retry", "route"] = "fail"
    max_retries: int = 3
    route_to: str | None = None

# ❌ Config 放端口名
class Config(BaseModel):
    from_port: str = "intent"     # 端口名是图的事
    to_port: str = "authorized"   # 端口名是图的事

# ❌ Config 放 framework 句柄
class Config(BaseModel):
    body: Body                    # framework 句柄走 @plugin(requires=...)
    seams: Seams                  # 同上
```

### 5.3 原则 3:错误三态(Success / Skip / Raise)

```python
# ✅ Worker 只表达三种情况之一
return Success(observation)                       # 成功
return Skip(reason="verdict_skip")                # 主动跳过
# 异常 —— 不写 try/except,让它冒到 framework,framework 按 on_error 处理

# ❌ Worker 自己写 try/except 折 receipt
try:
    result = body.act(decision=intent)
    return {"receipt": Artifact(kind=RECEIPT, content={"status": "ok", ...})}
except Exception as exc:
    return {"receipt": Artifact(kind=RECEIPT, content={"status": "error", ...})}
```

---

## 6. 退役清单(同 PR 删除,不留跨 PR 后门)

| # | 文件 / 符号 | 删什么 | 同 PR 替代 |
|---|---|---|---|
| 1 | `lca/plugins/lab/internal/worker.py` 整文件 | `_WORKERS` / `_ALIAS_TO_CANONICAL` / `_CANONICAL_TO_ALIASES` / `register_worker` / `get_worker` / `lookup_worker` / `bind_factory_aliases` / `reset_workers` / `reset_aliases` | `lca/plugins/lab/internal/discover_worker.py`:只读 `@plugin` 元数据 |
| 2 | `agent_lab/runtime/seams.py` 整文件 | `Seams` dataclass + `_SimpleBodyProtocol` + `_default_seams()` | framework 的 `cordis_bridge.build_execute_kwargs(worker, *, ctx)` 自动投影 |
| 3 | `lca/plugins/lab/act/body_provider/plugin.py::get_body` 函数 | 整函数(`plan_ref_default()` 保留为 provider 的 config 默认值) | `lca/plugins/lab/act/compose/plugin.py` 节点化;`@plugin(requires=["lab.tool_registry", "lab.safe_executor", "lab.transport", "lab.plan_ref"])` 在 setup 阶段装配,execute 阶段只 `body.act(decision=...)` |
| 4 | `agent_lab/runtime/runner.py::_default_seams()` 函数 | runner 不再懂 body_provider | runner._run_node 调 `cordis_bridge.build_execute_kwargs(worker, *, ctx)` |
| 5 | `if seams is None: raise RuntimeError(...)` 模式(act.execute / act.body / act.dispatch 当前 3 处) | 3 处全删 | framework 在调用前 fail-loud;Worker 不感知 |

**不留 compat shim**:遵循 ADR-0209 §1.6 / §7 Reject「deprecated 不删除 = 跨 PR 后门;同 PR 必须删」。

---

## 7. 错误三态详细规范

### 7.1 Success

```python
def execute(self, *, intent: Intent, body: BodyHandle) -> Observation:
    return body.act(decision=intent)
```

framework 行为:
- 写 `node_end(status="ok", value=observation)`
- 继续下一节点

### 7.2 Skip

```python
def execute(self, *, intent: Intent, body: BodyHandle) -> Observation | Skip:
    if intent.verdict == "skip":
        return Skip(reason="verdict_skip")
    return body.act(decision=intent)
```

framework 行为:
- 写 `node_end(status="skipped", reason="verdict_skip")`
- 继续下一节点(下一节点的 IN 端口拿空 Artifact / typed None)

### 7.3 Raise

```python
def execute(self, *, intent: Intent, body: BodyHandle) -> Observation:
    return body.act(decision=intent)              # 异常自然冒到 framework
```

framework 行为(读 `Config.on_error`):

| on_error | 行为 |
|---|---|
| `fail`(默认) | 写 `node_end(status="error", error=str(exc))` + raise(phase 失败) |
| `retry` | 按 `Config.max_retries` 重试(transient 退避,deterministic 不重试,见 ADR-0206 §5.6);最后一次仍失败 → 写 error + raise |
| `route` | 写 EXCEPTION artifact → 投到 `Config.route_to` 节点的第一个 IN → 继续 |

### 7.4 路由目标(`on_error=route`)

```python
class Config(BaseModel):
    on_error: Literal["fail", "retry", "route"] = "fail"
    route_to: str | None = None                  # on_error=route 时必填
    max_retries: int = 3                         # on_error=retry 时用

    @model_validator(mode="after")
    def _check_route_to(self):
        if self.on_error == "route" and self.route_to is None:
            raise ValueError("on_error=route requires Config.route_to")
        return self
```

**强约束:**

1. `route_to` 不存在或不可达 = 编译失败(防漏配)。
2. `route_to` 节点的第一个 IN 必须是 EXCEPTION 兼容类型;否则 `WorkerContractError`。
3. `route_to` 与当前节点不能形成环;否则 `CycleError` 编译失败。

---

## 8. lint-imports 新规则 `lab-worker-purity`

```python
# scripts/lint_imports/rules/lab_worker_purity.py
"""Lab Worker purity rules — enforce ADR-0211 §3 W-1 ~ W-10。

规则清单:
W-1: Worker.execute 全 keyword-only(必现 *,)
W-2: Worker.execute 入参必是 typed 类型(dict / Any 禁)
W-3: ctx / seams / node / inputs / Artifact 不进 Worker.execute 签名
W-4: Config 不放端口名
W-5: Config 不放 framework 句柄
W-6: Config.on_error 默认 fail;retry / route 必显式;route 必 route_to
W-7: Worker.execute 不写 try/except
W-8: Worker.execute 不折 receipt / EXCEPTION
W-9: register_worker / Seams / body_provider.get_body 三件在 lca/plugins/lab/** 不出现
W-10: Worker.execute 不写 if x is None / getattr 兜底
"""
```

**强约束:**

1. 新增 ruff 自定义规则(或 AST 静态扫描脚本),`scripts/lint_imports/` 注册。
2. pre-push 检查:`rg "execute\\(self, node, inputs" lca/plugins/lab/` = 0。
3. pre-push 检查:`rg "register_worker\\|Seams\\|body_provider\\|get_body" lca/plugins/lab/` = 0。
4. pre-push 检查:`rg "from agent_lab.runtime.seams" lca/plugins/lab/` = 0。
5. CI 门禁:`./scripts/lca-ops lint-imports` 必须包含本规则且通过(无新增失败)。

---

## 9. delete-when(本 ADR 升 Accepted 时,全部满足)

1. §5 Worker 三原则全部 89 个 carrier 落地
2. §6 退役清单 5 条全部 delete
3. §7 错误三态全部节点支持 `Config.on_error`
4. §8 lint-imports `lab-worker-purity` 规则落地;pre-push 4 项 rg 检查通过
5. ADR-0209 §6 delete-when 全 7 条满足
6. ADR-0209 升 Accepted

---

## 10. Reject(显式拒绝)

| 提议 | 拒绝理由 |
|---|---|
| `execute(self, node, inputs, seams=None)` 继续存在只是少传 seams | 签名不诚实未解决;读者仍看不出真依赖;违反 W-1 / W-3 |
| 在 `__init__` 里塞 typed handles(`self.body = ctx.require("lab.body")`) | 副作用搬到 init,问题没解决;Worker 仍感知 framework 句柄;违反 W-3 / W-5 |
| 用 `if ctx is None: raise` 兜底 | Worker 不该校验 runner 协议;framework fail-loud;违反 W-10 |
| Config 里放端口名(`from` / `to`) | 端口名是图的事;Config 不应感知;违反 W-4 |
| Worker 自己写 try/except 折 receipt | 错误策略在图,不在 worker;违反 W-7 / W-8 |
| `register_worker` 当 fallback 留 compat shim | 违反 ADR-0209 §1.6 / §7 Reject「deprecated 不删除 = 跨 PR 后门」;违反 W-9 |
| `Seams` 当 runtime typed handle 留 compat shim | 同上;违反 W-9 |
| `body_provider.get_body()` 当函数留 compat shim | 违反 ADR-0209 §1.6;违反 W-9 |
| 把 `on_error` / `max_retries` / `route_to` 放 Config 但 framework 不读,Worker 自己读 | on_error 是框架字段,Worker 不该读;违反 W-6 |
| 让 `cordis_bridge` 做 `if x is None: ...` 兜底 | framework 不做兜底;fail-loud;违反 W-10 |

---

## 11. 验收(PR 实施前/中/后)

**每个 PR 完成时**:

| # | 验证 | 命令 |
|---|---|---|
| 1 | lint-imports(含 `lab-worker-purity`) | `./scripts/lca-ops lint-imports`(无新增失败) |
| 2 | plugin shape | `./scripts/lca-ops audit-plugin-shape`(89 个 carrier 全部通过 Manifest 校验) |
| 3 | capability 闭包 | `python -m agent_lab.run --describe --target graph:act` 列出所有 `requires` / `provides` |
| 4 | Worker 签名纯度 | `rg "execute\\(self, node, inputs" lca/plugins/lab/` = 0 |
| 5 | Worker 签名纯度 | `rg "execute\\(self, \\*" lca/plugins/lab/ \| wc -l` = 89(全部 keyword-only) |
| 6 | Config 纯度 | `rg "from_port\\|to_port" lca/plugins/lab/` = 0(无端口名) |
| 7 | 错误处理纯度 | `rg "except Exception" lca/plugins/lab/` 仅在 framework(无 Worker 折 receipt) |
| 8 | 退役清单 | `rg "register_worker\\|Seams\\|body_provider\\|get_body" lca/plugins/lab/` = 0 |
| 9 | 第二 plugin 体系 | `rg "from agent_lab.plugins.base" lca/plugins/lab/` 仅在 helper 内部使用 |
| 10 | lab CLI 自检 | `python -m agent_lab.run act` 通过;`python -m agent_lab.run --describe --target graph:agent_loop` 列出全部 capability 关系 |
| 11 | 错误三态 | `python -m agent_lab.run act --error-policy=fail/retry/route` 三种策略全部触发对应路径 |
| 12 | 节点纯度 | `rg "from lca\\.cognition\\|executor\\|session" lca/plugins/lab/` = 0 |

**ADR 升 Accepted 条件**(同 PR 系列全部完成时):
- §6 退役清单全 5 条满足
- §9 delete-when 全 6 条满足
- §11 验收 1-12 全部绿
- ADR-0209 升 Accepted

---

## 12. 后果

**正**:
- Worker signature = 真实依赖,读者一眼看清节点真依赖(无 seams/node/inputs 容器)
- Config 收紧 = 静态值与端口名/框架句柄分离,Config 可静态分析
- 错误三态 = 错误策略在图,Worker 只表达三种情况之一;同图错误风格统一
- register_worker / Seams / body_provider 退役 = 「框架协议」彻底从 Worker / 节点文件移除
- cordis_bridge = framework 投影层,把 typed 入参从 ctx 取出;Worker 不感知 ctx/Artifact
- lint-imports `lab-worker-purity` = 强约束由机器守护,不是约定

**代价**:
- 一轮 89 个 carrier codemod(每个 Worker 重写为 typed signature + 收紧 Config)
- 新增 `cordis_bridge.py` / `discover_worker.py` 两个 framework 模块
- 新增 ruff 自定义规则 `lab-worker-purity`
- 测试更新:每个 Worker 的 unit test 改用 typed 入参

**风险与缓解**:
- 迁移中破坏 89 个 carrier 兼容 → **逐 phase 迁移 PR**(perceive → think → reflect → remember → control → act → passthrough → llm → model_eye → model_visible → lineage → event → session_log),每 PR 仅影响 1 个 phase,web-standard 不动
- typed signature 漏改 → ruff `lab-worker-purity` 规则 + pre-push grep 守护
- on_error / route_to 漏配 → Pydantic validator + framework 启动校验
- 旧路径 compat shim 复活 → §10 Reject 显式禁止 + pre-push grep 守护
- cordis_bridge 性能开销(inspect.signature 反射)→ 启动期一次性 build_execute_kwargs 缓存到 `Worker._kwargs_resolver`;运行期 O(1) lookup

---

## 13. 决策记录

**Adopt**:
- §1.1 Worker.execute 签名契约(keyword-only、typed 入出、无框架容器)
- §1.2 Config 收紧(只放静态值 + on_error 框架字段;不放端口名/框架句柄)
- §1.3 错误三态(Success / Skip / Raise)
- §1.4 旧入口退役清单(`register_worker` / `Seams` / `body_provider.get_body` 三件同 PR 删)
- §1.5 cordis_bridge framework 投影层
- §3 不变量 W-1 ~ W-10
- §4 act.execute Before / After 完整示例
- §5 Worker 三原则
- §6 退役清单
- §7 错误三态详细规范
- §8 lint-imports `lab-worker-purity` 规则
- §9 delete-when
- §10 Reject
- §11 验收

**Refines**:
- ADR-0209 §1.2「节点即 LCA plugin」(从模块形态到签名契约)
- ADR-0209 §1.3「装配唯一 = Profile/Bundle」(从图层到 execute 调用层)
- ADR-0209 §1.6 删除清单(从文件清单到签名清单)

**Supersedes**:无(无 ADR 决定过 Worker.execute 签名形态;本 ADR 是首次立契约)

**Required follow-ups**:
- spec `docs/specs/lab-worker-contract.md`(待建)详细记录 §1.1 / §1.2 / §1.3 / §5 三原则的工程示例
- spec `docs/specs/cordis-bridge-design.md`(待建)详细记录 §1.5 framework 投影层的实现细节
- ruff 自定义规则 `lab_worker_purity.py`(待写)实现 §8 lint-imports 规则
- 89 个 carrier codemod PR 系列(per phase,见 §12 风险与缓解)

**Accepted 条件**:
- §6 退役清单全 5 条满足
- §9 delete-when 全 6 条满足
- §11 验收 1-12 全部绿
- ADR-0209 升 Accepted
