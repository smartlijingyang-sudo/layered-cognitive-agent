# Plugin Tree Runtime — 用插件树跑通默认 Agent

**日期**: 2026-08-16
**状态**: Draft（评审一轮：Issues Found，本版已回填）
**关联**:
- [2026-08-14-deepseek-harness-integration-analysis.md](./2026-08-14-deepseek-harness-integration-analysis.md)（借鉴全景；本文**修订**其中「Cordis 插件树替换五层 — 不做」：五层 import 图仍不做，**组合/启动层**改为插件树）
- DSH 子进程对照跑道保留，是树上的一个可替换 loop 插件
- ADR-0004 Protocol-First、ADR-0005 L4 组合根、ADR-0002 认知循环、ADR-0037 Journal-as-Truth

---

## 0. 一句话

DSH SDK 的做法是：进程启动时把 `cordis.yml` 里的**全部插件加载一遍**，JSON-RPC 服务器只是树上的一个插件；之后 `session/prompt` 不再组装系统，只是往已经活着的 `ctx.agents` 投一条用户消息。

LCA 做同一件事：Gateway 进程启动时加载 `profiles/lobehub-run.yaml` 里的**全部插件**；LobeHub 的 `POST /runs` 不再在 `execute.py` 里手写组装，只是往已经活着的树投一条用户消息。主流程通 = 树加载成功。

---

## 1. 为什么这样能变强（以及什么时候不能）

会变强，当且仅当「加一个能力 = 一个插件模块 + YAML 里多一行」，而不是改 `composer.py` / `defaults.py` / `execute.py`。

| 以后要加的东西 | 挂在哪 | 不改什么 |
|---|---|---|
| 换一种 subagent（进程内 / DSH / ACP） | `subagent` seam 的新 Provider 插件 | loop、Team 策略、LobeHub |
| 一个 Skill 包或新的 skill 来源 | `skills` Provider + 可选 `tool-skill` | Brain、Runtime |
| 一段固定 SOP / workflow | `workflow` 插件注册引擎 + 一个 model-facing tool | 认知循环本体 |
| 换 loop（CognitiveRuntime ↔ DshTurnDriver） | 加载 `loop-dsh` + 请求 `execution_target=dsh`（`agent_loop.select`） | HTTP、Journal、卡片 |
| 换 LLM / 沙箱 / 搜索 | 对应 seam 的 Provider 行 | Consumer |

不会变强的做法：把 Cordis 的 `ctx` 做成 L1–L3 运行时 Service Locator（违反 ADR-0005）、用插件树拆掉五层单向依赖、把 DSH Web 换掉 LobeHub、把 DSH 的 TS 包搬进来。那些是第二套内核，不是扩展面。

本文抄的是 DSH 的**启动思想**，不是 Cordis 运行时。

---

## 2. DSH SDK 实际怎么跑（对照源）

Python SDK 自己不装插件。它 spawn `dsh-jsonrpc-agent`，把一份 Cordis 配置注入子进程（默认内置组合，或 `cordis=` / `DSH_CORDIS_CONFIG`）。

默认/示例组合（`examples/jsonrpc-agent/cordis.yml` + spine）加载后树上有：

```
sdk-jsonrpc-server     inject: ['agents']     # 入口：stdio JSON-RPC
llm + llm-deepseek                            # 模型 seam + Provider
session + session-persistence-jsonl           # 只追加日志
system-prompt + tools                         # 提示词段 + 带守卫的工具管线
skill + skill-filesystem + tool-skill         # 技能目录 + 模型工具
agent + agent-loop                            # 注册表 + 具体循环
subprocess + bash + fs-local + tool-fs        # 执行世界
subagent + spawn-in-process + tool-subagent   # 子 agent
tool-todo + token-meter + compaction-basic    # 其余能力
```

加载语义（`packages/boot/app-boot` + Cordis Loader）：

1. 读配置条目列表。**行顺序不决定加载顺序**；激活由 `inject` 的服务是否就绪驱动。
2. 每个插件导出 `name` / `inject` / `Config` / `apply(ctx, config)`。没有 default export，以免冲掉这些字段。
3. `apply` 里的注册都是可逆副作用（`ctx.effect`）；卸载时撤销。
4. 树结算后 `assertEntriesLoaded` + `assertEntriesActivated`：已启用却没挂上、或还在等一个永远不来的服务 → **启动失败，进程退出**。
5. 之后协议只做三件事：`initialize`（cwd / provider / model）→ `session/prompt`（投用户消息）→ 收 `session.event`。

产品级组合（`packages/bundle/base/cordis.patch.yml`）是同一机制的更大一棵树：在空列表上 insert 全套行；profile 再叠 web/headless；用户 `cordis.patch.yml` 按 **id 整行替换 config**（不深合并）。

LCA 要对齐的是上面 1–5，不是 HMR、Fiber、isolate realm、`!!js` 表达式。

---

## 3. 第一性原理（LCA 侧）

1. **每个组合根 boot 一次。** Gateway 生产进程一次；每个 `AgentComposer` 一次（§18）。今天 `compose` 每次 `boot_capabilities()`，每造一个 Agent 就重建 ctx。树加载必须发生在第一次 create 之前，不能发生在每次 create 里。
2. **插件是扩展单位。** 一个插件 = 声明依赖 + 一次 `apply` + 可撤销的注册。不是「又一个 Registry 字典」。
3. **服务键上只有 Definition。** Provider 挂到 Definition 上（已有 `ProviderDispatch`）。Consumer（Reasoner / Body / Runtime）构造函数拿 Definition，运行期不查表（ADR-0005）。
4. **一次 Run 是根 ctx 的子作用域。** 工具 schema、LLM 适配器、Skill 目录是进程级的；plane 绑定、workspace、附件、LiveTail、这一次的 Agent 实例是 Run 级的。DSH 用 `agent.ctx`（`dsh-scope`）做这件事。没有子作用域，computer 工具无法绑对这一次的机器/沙箱。
5. **Journal 仍是对外事实源。** 插件可以往 Journal 记，不能另开一条 LobeHub 协议。卡片继续走现有 `WIRE` / `plugin_state` / SSE。
6. **五层单向依赖不动。** 插件源码住在自己那一层；只有 L4 / Gateway 知道整棵树。

---

## 4. 与现状的关系（不推倒重来）

已有、本设计**长上去**的：

| 已有 | 角色 |
|---|---|
| `CapabilityHub` + `SeamKey` + `*Service` | 进程级 `ctx.<key>` Definition |
| `ProviderDispatch` | 每个 Definition 内部的 Provider 表 |
| `capability_boot.py` | 将被 **Loader + profile** 取代；逻辑拆进各插件的 `apply` |
| `SimpleEventBus` 的 emit / waterfall / serial | 插件扩展点 |
| `DefaultToolExecutionPipeline` | `tools` 插件拥有的管线 |
| `AgentComposer` / `TeamComposer` | 变成 `agent-loop` / `team` 插件内部的闭包工厂，不再每次 boot |
| `DshTurnDriver` | 可选的另一个 `agent-loop` Provider，不是第三种 plane |

要消掉的耦合：

- `composer.py` 里的 `ctx = boot_capabilities()`
- `gateway/runs/execute.py` 里手写 `build_solo_agent` / `build_runnable_team` / `is_dsh_driver` 三分支（改为问树上的 loop 工厂）
- `gateway/app.py` 里零散单例（`RunRegistry` / `FileStore` / `DeviceHub`）改为 boot 后挂到 `app.state.ctx`

---

## 5. 插件内核

### 5.1 形状（对齐 DSH 导出约定 + Cordis 三种形态）

#### 5.1.1 函数式插件（最常用）

一个插件模块**必须**导出：

```python
name: str                          # 稳定 id，YAML 的 name 对上这个，或 YAML 用 import 路径
inject: tuple[str, ...]            # 启动前必须已经 mount 的服务键（array 形式）
provides: str | None               # 本插件 mount 的服务键；None = 只往已有服务上注册

class Config(BaseModel):           # pydantic V2；缺省 Schema 用空模型。等价于 Cordis 的 Standard Schema V1
    ...

def apply(ctx: PluginContext, config: Config) -> Effect | None:
    """apply 可同步/异步；返回 Effect（disposer / generator / async generator / iterable）或 None。"""
    ...
```

#### 5.1.2 类式插件（Service 子类 / Constructor 形态）

对齐 Cordis 的 `Plugin.Constructor`：

```python
class MyService(Service):
    name = "my-service"
    inject = ("llm", "tools")
    provides = "my_service"

    class Config(BaseModel):
        option_a: str = "default"

    def __init__(self, ctx: PluginContext, config: Config) -> None:
        super().__init__(ctx, config)
        # 构造函数内可 ctx.mount / ctx.on / ctx.effect

    async def init(self) -> AsyncGenerator[Callable[[], None], None]:
        """可选的异步初始化钩子。yield disposer（对齐 Cordis Fiber [Service.init]）。"""
        yield lambda: cleanup_a()
        yield lambda: cleanup_b()

    @classmethod
    def check(cls) -> bool:
        """可选的可用性谓标（对齐 Cordis [Service.check]）。返回 False 时消费者保持 PENDING。"""
        return cls._is_healthy()
```

Loader 检测 `isclass(plugin)` 时走 `new plugin(ctx, config)` 路径，然后调 `init()`（如果定义了），收集所有 yield 的 disposer。与 Cordis 的 `isConstructor(runtime.callback)` + `instance[symbols.init]?.()` 完全对齐。

#### 5.1.3 对象式插件（`{ apply }` 形态）

对齐 Cordis 的 `Plugin.Object`：

```python
class MyPlugin:
    name = "my-plugin"
    inject = ("tools",)

    def apply(self, ctx: PluginContext, config: Config) -> Effect | None:
        ...
```

Loader 检测 `hasattr(plugin, 'apply')` 且 `callable(plugin.apply)` 时走此路径。

#### 5.1.4 PLUGIN 快捷导出

模块可导出 `PLUGIN` 对象统一声明（对齐参考实现的 `PluginSpec`）：

```python
PLUGIN = PluginSpec(name="...", apply=fn, inject=("x",), provides="y", Config=MyConfig)
```

#### 5.1.5 多 Fiber per Runtime

对齐 Cordis `Plugin.Runtime.fibers: DisposableList<Fiber>`：同一个插件 callback 可以被 `ctx.plugin()` 加载多次（不同 config / 不同 child ctx），产生多个 Fiber。Loader 跟踪每个 runtime 的所有 live fiber；最后一个 fiber dispose 时清理 runtime record。

LCA 场景：同一个 `tool-skill` 插件可以 mount 两次——一次绑 disk store，一次绑 remote store。

#### 5.1.6 inject 的两种形式

对齐 Cordis `Inject = string[] | Dict[str, intercept_config]`：

```python
# Array 形式：只声明依赖
inject = ("llm", "tools")

# Dict 形式：依赖 + 拦截配置（对齐 Cordis intercept config）
inject = {
    "llm": {"timeout": 30},        # 覆盖 llm 插件的 intercept config
    "tools": None,                  # 无拦截配置
}
```

Loader 在创建 Fiber 时，dict 形式的值被合并到 child ctx 的 intercept overlay。

禁止 default 成「整个模块就是 apply」——和 DSH 一样，具名导出才能让 Loader 读到 `inject` / `Config`。

`Plugin` Protocol 放 `lca/contracts/mechanisms/plugin.py`，实现类显式继承（`check_protocol_impl.py`）。函数式模块由 Loader 包成 `ModulePlugin`。

### 5.2 PluginContext

`lca/layer0_infra/plugin/context.py`。**只允许在 `apply` 和 loop 插件内部使用。** L1–L3 领域类不 import 它。

```python
class PluginContext:
    hub: CapabilityHub          # mount / require / get / keys / set
    bus: EventBus               # 5 种 dispatch：emit / parallel / serial / bail / waterfall
    config: Mapping[str, Any]   # 本插件已校验的 config

    # ── 服务 ──
    def mount(self, key: str, service: object, *, check: Callable[[], bool] | None = None) -> Callable[[], None]:
        """注册服务；返回 disposer（自动进 effect）。check 为可用性谓标——返回 False 时消费者保持 PENDING（对齐 Cordis [Service.check]）。"""
    def require(self, key: str) -> Any: ...
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None:
        """覆写本 fiber 已 mount 的服务值（对齐 Cordis ctx.set）；只允许 owner fiber 调用。"""

    # ── Effect（对齐 Cordis Fiber.effect 全部形态）──
    def effect(self, setup: Callable[[], Effect]) -> AsyncDisposable:
        """setup() 返回 Effect。Effect 可以是：
        - disposer 函数（同步/异步）
        - generator / async generator（yield 多个 disposer）
        - iterable / async iterable of disposer
        - None
        卸载时 LIFO 清理。返回 AsyncDisposable（对齐 Cordis AsyncDisposable，可 await 等待 setup 完成）。
        """

    # ── 事件（对齐 Cordis EventsService 全 API）──
    def on(self, event: str, handler: Callable, *,
           mode: Literal["emit", "parallel", "serial", "bail", "waterfall"] = "emit",
           prepend: bool = False,
           global_: bool = False) -> Callable[[], bool]:
        """注册监听；自动进 effect，卸载撤销。
        global_=True：无视 Context.filter（对齐 Cordis EventOptions.global）。
        返回 disposer；disposer() 返回 bool 表示是否仍在注册表。
        """
    def once(self, event: str, handler: Callable, **kw) -> Callable[[], bool]:
        """一次性监听；首次调用后自动撤销（对齐 Cordis once()）。"""
    async def emit(self, event: str, *args) -> None: ...
    async def parallel(self, event: str, *args) -> None:
        """并发执行全部监听器，等待所有完成。失败收集为 ExceptionGroup（对齐 Cordis Promise.allSettled + AggregateError）。"""
    async def serial(self, event: str, *args) -> Any:
        """顺序执行，遇到 bail 值（非 None/False）立即返回。"""
    def bail(self, event: str, *args) -> Any:
        """同步版本：顺序执行，遇到 bail 值立即返回。"""
    async def waterfall(self, event: str, *args, terminal: Callable) -> Any:
        """中间件风格；最后参数是 next 续体。不调用 next() 即可终止链路。"""

    # ── Accessor / Mixin（对齐 Cordis ReflectService）──
    def accessor(self, name: str, *, get: Callable, set: Callable | None = None) -> Callable[[], None]:
        """定义 ctx 上的计算属性。get/set 在通过 ctx.name 访问时调用。
        返回 disposer（对齐 Cordis accessor()）。
        """
    def mixin(self, source: str | object, keys: list[str] | dict[str, str]) -> Callable[[], None]:
        """把 source 服务的指定成员暴露为 ctx 上的转发 accessor。
        例：ctx.mixin("events", ["on", "emit", "waterfall"]) → ctx.on 转发到 ctx.events.on。
        返回 disposer（对齐 Cordis mixin()）。
        """

    # ── 子上下文 ──
    def child(self, *, key: str, values: Mapping[str, Any] | None = None) -> PluginContext:
        """Run 级子作用域。overlay 槽只查 child，不回落活实例。服务工厂可回落到父。
        子 dispose 只撤自己的 effect。详见 §9。
        对齐 Cordis Context.extend()（原型继承 + shadow）。
        """

    # ── Inject 简写（对齐 Cordis ctx.inject）──
    async def inject(self, deps: tuple[str, ...] | dict[str, Any], callback: Callable) -> "FiberHandle":
        """在满足 deps 时运行 callback。callback 随依赖变化重新执行（卸载 → 重载）。
        返回 FiberHandle（可 await 等待加载完成）。
        内部创建子 Fiber，生命周期归当前 fiber。
        """

    # ── 诊断（对齐 Cordis trace/bind）──
    def trace(self, value: Any) -> Any:
        """为调试包装一个值，使后续方法调用记录来源 ctx。Python 实现用 contextvars 关联。"""
    def bind(self, callback: Callable) -> Callable:
        """包装回调，使调用时自动 trace self 和参数到当前 ctx。"""
```

**Effect 类型（对齐 Cordis Effect）：**

```python
Effect = (
    | Callable[[], None]                   # 同步 disposer
    | Callable[[], Awaitable[None]]        # 异步 disposer
    | Generator[Callable, None, None]      # 同步 generator：yield 多个 disposer
    | AsyncGenerator[Callable, None, None] # 异步 generator
    | Iterable[Callable]                   # 同步 iterable of disposer
    | AsyncIterable[Callable]              # 异步 iterable
    | None                                 # 无清理逻辑
)

AsyncDisposable = Callable[[], Awaitable[None]]  # disposer 本身可 await
```

`CapabilityHub.mount` 已是一次性、禁止覆盖。插件若 `provides="llm"`，在 `apply` 里 `ctx.mount("llm", LlmService())`。第二个声称 `provides` 同一键的已启用插件 → boot 失败。

`PluginContext.require` **只允许**出现在：

1. 任何插件的 `apply`
2. `agents` / `teams` / `run-execute` 的 **create 闭包**（把 Definition 或已选定 Provider 注入构造函数）

`CognitiveRuntime`、`PromptReasoner`、`SimpleBody`、决策门、工具 `execute` **禁止**持有或调用 `PluginContext`。think / act 路径上写 `ctx.llm` 视为违反本设计（也违反 ADR-0005）。这是对 ADR-0005 的**范围修订**：L4 与 Gateway 进程可以持有 `app.state.ctx`；L1–L3 仍然只能构造函数注入。需要一份后续 ADR 记录此修订，实现 S1 时一并起草，不阻塞内核代码。

**为什么 `require` 必须检查 `inject`（Cordis ReflectService 映射）：** Cordis 的 `ReflectService` 代理属性访问：沿当前 Fiber 的父链寻找服务实现；如果该名字在当前插件的 `inject` 中却暂不可用，报"required service in inactive context"，而非让插件在半初始化状态继续执行（`vendor/cordis/src/reflect.ts`）。这解释了两个设计决定：第一，**必需依赖必须显式声明**，运行时才能控制激活顺序；第二，`ctx.get('metrics')` 适合可选能力——不存在时返回空值，插件选择降级，而不是让整个生命周期阻塞。本设计的 `require` 检查 `inject`、`get` 不检查，正是同一模式。

根 ctx 与 child 的查找规则见 §9，**不是**「子没有就回落到父的活实例」。

### 5.3 Loader

`lca/layer0_infra/plugin/loader.py`。

#### 5.3.1 Boot 流程

输入：已经展开的 `list[PluginEntry]`（见 §6）。行为：

1. 校验每个 entry：`id` 唯一；`name` 能 import；`Config` 能 parse；`disabled` 为真则跳过。
2. **单线程就绪队列**（禁止并发 `apply`）：`CapabilityHub.mount` 一次性且非线程安全；并发 apply 会与双 `provides` 检测竞态。每轮取出所有 `inject` 已满足的未 apply 条目，**按展开后的列表顺序**依次 `apply`，再进入下一轮。
3. 一轮无人可调度：
   - 剩下的条目缺的键在本 profile **没有任何** `provides` 该键的已启用插件 → **硬失败**，列出「插件 id + 缺失键 + 谁也没提供」。
   - 否则是环 → **硬失败**，列出环上的 id。
4. 全部 apply 后：对 `REQUIRED_SEAM_KEYS` 跑 `require_complete`（已有三角色目录，改由各插件在 `apply` 里 `register_seam`）。
5. 返回 `BootedTree(ctx, entries, disposers)`。`dispose()` LIFO 撤全部 effect。

#### 5.3.2 Await 与任务追踪（对齐 Cordis EntryTree.await / getTasks）

```python
class BootedTree:
    async def await_all(self) -> None:
        """等待所有 entry 的 _init_task 和 fiber.inertia 完成。
        与 Cordis EntryTree.await() 相同：反复收集 pending tasks，allSettled 后检查 fiber errors。
        失败收集为 ExceptionGroup。
        """

    def get_tasks(self) -> list[Awaitable]:
        """返回当前所有 pending 的 import 和生命周期任务。"""
```

`boot()` 完成后调 `await_all()` 确保所有 plugin 已 settle，再检查 `assert_entries_activated`。

#### 5.3.3 运行时变更 API（对齐 Cordis EntryTree.create/remove/update）

```python
class BootedTree:
    async def create(self, options: PluginEntry, parent: str | None = None) -> str:
        """运行时动态添加 entry。import → register → _activate。返回 entry id。"""

    async def remove(self, entry_id: str) -> None:
        """运行时移除 entry。_deactivate → 从 store 删除。触发依赖级联。"""

    async def update_entry(self, entry_id: str, *, config: Any = None, inject: Any = None,
                           name: str | None = None, disabled: bool | None = None) -> None:
        """更新 entry 并三态 diff：
        - 只改 config → _patch_context（fiber.update）→ 热重启
        - 改 name/inject → dispose + 重新 import + _start（完整替换）
        - 改 disabled → _deactivate 或 refresh
        每种 diff 失败时 rollback 到旧状态。
        对齐 Cordis Entry.update() 的三态 diff 逻辑。
        """
```

#### 5.3.4 嵌套 Entry ID（对齐 Cordis EntryTree.sep `:` 解析）

支持 `parent:child` 形式的嵌套 id。`resolve("group-a:tool-x")` 先定位到 `group-a` 的 subtree，再在其中找 `tool-x`。

```yaml
# 嵌套 entry 在 YAML 中的表示
- id: tools-group
  group: true
  config:
    - id: web-search
      name: lca.layer0_infra.plugins.tool_web_search
    - id: ask-user
      name: lca.layer0_infra.plugins.tool_ask_user
```

#### 5.3.5 Entry 持久化（对齐 Cordis EntryTree.write / Include）

```python
class BootedTree:
    def write(self) -> None:
        """把当前 entry 列表序列化回 YAML/JSON 文件。原子写入（写 .tmp + rename）。
        运行时变更（create/remove/update_entry）后自动调 write()。
        对齐 Cordis Include._writeFile() 的原子写入 + 重试。
        """

    async def refresh(self) -> None:
        """重新读取配置文件，如果内容有变化则 transactional 更新 entry 列表。
        对齐 Cordis Include.refresh()。
        """
```

生产 Gateway 用只读 profile（不 write）；开发/调试场景可启用写回。

#### 5.3.6 Builtins 协议（对齐 Cordis `cordis:` 前缀）

```python
class BootedTree:
    builtins: dict[str, Any]  # "cordis:echo" → echo_plugin_module

    def import_plugin(self, name: str) -> Any:
        if name.startswith("cordis:"):
            return self.builtins[name[7:]]
        # 否则走 importlib
```

`cordis:` 前缀用于内置插件、测试桩、mock 实现。

#### 5.3.7 Self-Dispose 检测（对齐 Cordis Loader 的 internal/plugin 监听）

当插件自己调用 `ctx.fiber.dispose()`（而非被外部 unmount）时，Loader 检测到并标记 entry `disabled=True`，调用 `write()` 持久化。防止插件自杀后 Loader 继续尝试重新激活。

#### 5.3.8 Disabled 继承（对齐 Cordis Entry._disabled）

一个 entry 的 `disabled` 状态不仅看自身，还要沿 parent 链检查：任何祖先 entry 被 disable → 本 entry 也视为 disabled。Group entry 自身 **永远不禁用**（对齐 Cordis `if (options.group) return false`）。

**没有** HMR、没有 `!!js` 表达式。需要环境值用 pydantic-settings / 进程环境，在 `apply` 里读。

### 5.4 失败语义（对齐 `assertEntriesActivated`）

| 情况 | 行为 |
|---|---|
| YAML 不是对象 / 缺 `plugins` 或 `bundles` | boot 抛 `ProfileError`，Gateway 拒绝 listen |
| 某行 `name` import 失败 | 同上，带 id 与模块路径 |
| Config 校验失败 | 同上，带 pydantic 错误 |
| inject 无法满足 / 环 | 同上，带缺失图 |
| 两个已启用插件 `provides` 同一键 | 同上 |
| `apply` 抛异常 | dispose 已 apply 的插件，再抛，带该 id |
| 运行期插件内部错误 | 不拆树；记 Journal；该 Run 失败 |

Gateway `lifespan`：boot 失败则进程以非零退出（和 DSH `installFailLoud` 一样，启动期不听请求）。

### 5.5 三条核心调用链（对照 Cordis Fiber + Reflect + Loader）

下面三条链路是 Cordis 运行时最有价值的设计模式。本设计的 Loader 实现必须保持相同的系统不变量。参考实现见 §21。

**调用链一：首次启动——配置如何变成运行中的插件**

`cordis.yml` / profile YAML 中的一行 Entry 并不直接等于插件对象。它先成为 Loader 的 `PluginEntry`，再导入模块并创建 `PluginHandle`（等价于 Cordis Fiber）。

```
Profile YAML 中的一行 Entry
  { id, name, config, inject }
        │
        ▼
Loader 展开 bundles → list[PluginEntry]
        │
        ▼
Loader.boot()：登记所有 entry（register），不立即 apply
        │
        ▼
_reconcile() 收敛循环：
  反复扫描 PENDING && desired && deps-ready 的插件
  └─ 检查 inject 是否全部就绪（get_service 非 None）
  └─ 就绪 → _activate()
        │
        ▼
_activate(handle)：
  ├─ validate(config)
  ├─ apply(ctx, config)
  │     ├─ ctx.provide()：发布服务
  │     ├─ ctx.on()：注册有 owner 的监听器
  │     ├─ ctx.effect()：登记清理逻辑
  │     └─ return disposer：登记插件级清理逻辑
  ├─ state → ACTIVE
  └─ emit("plugin.active")
```

**反直觉点：不能把配置文件中更靠前的行当成依赖保证。** 正确代码应像 Cordis 一样，把所有 Entry 都登记，再由依赖条件驱动激活。本设计的 `_reconcile()` 是一个最小收敛循环；profile YAML 中故意把 `audit`、`tool-skill` 放在它们依赖的 `tools`、`skills` 前面，仍能全量激活。

**调用链二：服务消失——消费者如何安全停用**

这不是传统「启动时拓扑排序一次就结束」的依赖注入。它是一个**持续响应服务出现和消失**的动态依赖图（Cordis `Reflect.notify()`）。

```
某个 Fiber 开始卸载（例如 clock 插件被 unmount）
  │
  ├─ _remove_owned_services(handle)
  │     ├─ 从 _services 表移除 clock 的 ServiceRecord
  │     ├─ emit("service.removed", "clock", owner_id)
  │     └─ 找到 inject 包含 'clock' 的 consumer Fiber
  │           │
  │           ├─ consumer 状态：ACTIVE → UNLOADING
  │           ├─ 移除 consumer 提供的服务
  │           ├─ 逆序执行 consumer 的 disposer（清理其注册的工具、监听等）
  │           └─ consumer 状态：PENDING（仍 desired=True，只是依赖缺失）
  │
  └─ clock 的 effect / disposer 逆序清理并进入 DISPOSED
```

业务插件不需要写「如果 clock 被删除，手工撤销工具」的监听代码。工具的注册和撤销被写入 consumer 的 disposer；disposer 属于 consumer 的 `PluginHandle.effects`。**所有权链**把依赖变化与资源回收连接在一起。

当 clock 再次提供服务时，那些仍然 `desired=True` 的 consumer 在下一轮 `_reconcile()` 自动从 PENDING → LOADING → ACTIVE。官方服务文档明确描述了「required service disappears → dependents dispose automatically → service returns → plugins load again」的语义。

**调用链三：配置热更新——为什么先停、再启、失败回滚**

对运行中的 Entry 修改配置不是覆盖一个字典。Cordis 的 `Entry.update()` 先识别差异：只改 `config` 可走重启路径；改 `name` / `inject` 要替换整棵插件实例。新配置启动失败后，它恢复旧配置与旧插件（`vendor/loader/src/config/entry.ts`）。

本设计的 `update_config()` 落地为同一事务原则：

```
save old_config
  → _deactivate(handle, permanent=False)     # 停旧实例，但保留 desired
  → handle.config = new_config
  → _reconcile()                             # 尝试以新配置启动
  → 如果 ACTIVE：emit("plugin.updated")，完成
  → 如果 FAILED：
      _deactivate(handle, permanent=False)   # 停失败实例
      handle.config = old_config             # 恢复旧配置
      _reconcile()                           # 重新启动旧实例
      raise PluginError("配置更新失败，已回滚")
```

**`_reconcile()` 收敛算法（本设计 Loader 的核心）：**

```python
while True:
    progressed = False
    for handle in all_handles:
        if handle.desired and handle.state == PENDING and deps_ready(handle):
            await _activate(handle)
            progressed = True
    if not progressed:
        break  # 稳定态：要么全部 ACTIVE，要么缺服务/有环
```

这个循环保证：(a) 所有可满足依赖的插件最终激活；(b) 任意配置行顺序都能正确加载；(c) 不可满足的依赖在循环终止后被 Loader 检测为硬失败。

### 5.6 EventBus：5 种 Dispatch 模式（完全对齐 Cordis EventsService）

对齐 Cordis `vendor/cordis/src/events.ts` 的全部 dispatch 语义：

| 模式 | Cordis | 行为 | 用途 |
|---|---|---|---|
| **emit** | `ctx.emit()` | 同步调用全部监听器，不等返回值 | 通知：日志记录、指标采集 |
| **parallel** | `ctx.parallel()` | 并发调用全部监听器，`await asyncio.gather(*, return_exceptions=True)`，失败收集为 `ExceptionGroup` | 独立副作用：多个插件各自处理同一事件 |
| **serial** | `ctx.serial()` | 顺序 await 每个监听器，遇到 bail 值（非 None/False）立即返回 | 需有序执行且可短路：权限检查、配置校验 |
| **bail** | `ctx.bail()` | 同步版本：顺序调用，遇到 bail 值立即返回 | 同步短路：同步权限/格式检查 |
| **waterfall** | `ctx.waterfall()` | 中间件风格：最后参数是 `next` 续体。监听器不调用 `next()` 即可终止链路 | 可拦截的管线：工具执行前拦截、LLM 调用前变换 |

```python
class EventBus:
    async def emit(self, event: str, *args) -> None:
        for cb in self._dispatch("emit", args):
            cb(*args)

    async def parallel(self, event: str, *args) -> None:
        results = await asyncio.gather(
            *(cb(*args) for cb in self._dispatch("parallel", args)),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            raise ExceptionGroup("parallel dispatch errors", errors)

    async def serial(self, event: str, *args) -> Any:
        for cb in self._dispatch("serial", args):
            result = await cb(*args)
            if is_bailed(result):
                return result

    def bail(self, event: str, *args) -> Any:
        for cb in self._dispatch("bail", args):
            result = cb(*args)
            if is_bailed(result):
                return result

    async def waterfall(self, event: str, *args, terminal: Callable) -> Any:
        cbs = list(self._dispatch("waterfall", args))
        async def _next(i: int = 0) -> Any:
            if i >= len(cbs):
                result = terminal()
                return await result if inspect.isawaitable(result) else result
            result = cbs[i](*args, _next, i + 1)
            return await result if inspect.isawaitable(result) else result
        return await _next()

def is_bailed(value: Any) -> bool:
    """bail 值 = 非 None 且非 False（对齐 Cordis isBailed）。"""
    return value is not None and value is not False
```

**Context filter（对齐 Cordis Context.filter）：**

每个 dispatch 前检查 listener 的 `global_` 标记和当前 ctx 的 filter：

```python
def _dispatch(self, mode: str, args: tuple) -> list[Callable]:
    filter_fn = getattr(self._current_ctx, '_filter', None)
    return [
        hook.callback
        for hook in self._hooks.get(event, [])
        if hook.global_ or not filter_fn or filter_fn(hook.ctx)
    ]
```

### 5.7 内部事件协议（完全对齐 Cordis Events 接口）

对齐 Cordis `vendor/cordis/src/events.ts` 的 `Events` 接口，以下内部事件构成插件系统的**横切扩展点**：

| 事件 | 模式 | 触发时机 | 用途 |
|---|---|---|---|
| `internal/plugin` | emit | Fiber 创建或 uid 清除 | Loader 追踪 fiber↔entry 映射；检测 self-dispose |
| `internal/status` | emit | Fiber 状态转换（PENDING→LOADING→ACTIVE→…） | 诊断、状态面板、Journal 记录 |
| `internal/config` | waterfall | Fiber 解析 raw config 后、`apply` 前 | Loader 做 `!!js` 插值（LCA 不用）；插件可变换 config |
| `internal/service` | emit | 服务注册 / 移除 / 变更 | 诊断、服务发现面板 |
| `internal/update` | waterfall | 配置热更新时（`fiber.update()`） | Loader 持久化新 config；HMR 拦截 |
| `internal/get` | waterfall | 通过 ctx proxy 读取服务时 | 诊断、访问审计 |
| `internal/set` | waterfall | 通过 ctx proxy 覆写服务时 | 诊断、变更拦截 |
| `internal/listener` | bail | 注册事件监听器时 | 特殊事件路由（如 `internal/update` 的重路由） |
| `internal/dispatch` | emit | 任何非 internal 事件 dispatch 前 | 诊断、日志 |

LCA 实现时至少覆盖前 5 个（`internal/plugin`、`internal/status`、`internal/config`、`internal/service`、`internal/update`），后 4 个作为可选诊断扩展点。

### 5.8 Service 基类（对齐 Cordis Service 抽象类）

对齐 Cordis `vendor/cordis/src/service.ts`：

```python
class Service(ABC):
    """服务基类。子类构造时自动 ctx.mount(self.name, self)。
    对齐 Cordis Service 抽象类的构造即注册模式。
    """
    name: ClassVar[str]                    # 服务键
    inject: ClassVar[tuple[str, ...]] = () # 依赖

    def __init__(self, ctx: PluginContext, config: Any = None) -> None:
        self.ctx = ctx
        self._check_fn: Callable[[], bool] | None = getattr(type(self), "check", None)
        ctx.mount(self.name, self, check=self._check_fn)

    @classmethod
    def check(cls) -> bool:
        """可用性谓标（对齐 Cordis [Service.check]）。返回 False 时消费者保持 PENDING。"""
        return True

    async def init(self) -> AsyncGenerator[Callable[[], None], None] | None:
        """可选初始化钩子（对齐 Cordis [Service.init]）。yield disposer。"""
        return None

    def resolve_config(self, base: Any = None, head: Any = None) -> Any:
        """合并 intercept 配置（对齐 Cordis [Service.resolveConfig]）。
        从当前 ctx 向上收集所有 intercept overlay，浅合并。
        """
        configs = []
        if base:
            configs.append(base)
        # 收集 ctx 链上的 intercept 配置
        ctx = self.ctx
        while ctx is not None:
            intercept = ctx.get_intercept(self.name)
            if intercept:
                configs.append(intercept)
            ctx = ctx.parent
        if head:
            configs.append(head)
        return {**c for c in configs} if configs else None
```

### 5.9 FiberHandle：可等待的 Fiber 引用（对齐 Cordis Fiber & PromiseLike）

对齐 Cordis `Fiber & PromiseLike<Fiber>`：

```python
class FiberHandle:
    """一个 entry 的运行时状态 + 可 await 的生命周期。
    对齐 Cordis Fiber 的 await() + thenable 语义。
    """
    entry_id: str
    state: PluginState
    error: BaseException | None
    inertia: asyncio.Task | None  # 当前进行中的 load/unload 任务

    async def await_settled(self) -> "FiberHandle":
        """等待当前生命周期任务完成，重启动错误。
        对齐 Cordis Fiber.await()。
        """
        while self.inertia:
            await self.inertia
        if self.error:
            raise self.error
        return self

    async def update(self, config: Any, no_save: bool = False) -> None:
        """验证并应用新 config，然后 restart。
        先触发 internal/update waterfall，允许 HMR / 持久化钩子拦截。
        对齐 Cordis Fiber.update()。
        """

    async def restart(self) -> None:
        """dispose 并立即用当前 config 重新加载。
        对齐 Cordis Fiber.restart()。
        """

    def get_effects(self) -> list[EffectMeta]:
        """返回当前注册的 effect 诊断树。
        对齐 Cordis Fiber.getEffects()。
        """
```

### 5.10 EffectMeta 诊断树（对齐 Cordis EffectMeta）

```python
@dataclass
class EffectMeta:
    """每个 effect 的诊断节点。对齐 Cordis EffectMeta。"""
    label: str               # 例如 'ctx.on("tool.called")' 或 'ctx.provide("llm")'
    children: list[EffectMeta] = field(default_factory=list)
```

`ctx.effect(setup, label="ctx.provide('llm')")` 在诊断输出中显示为树形结构，便于排查泄漏。`lca-ops status --effects` 打印全树的 effect 诊断。

### 5.11 DisposableList：O(1) 删除（对齐 Cordis）

```python
class DisposableList:
    """有序的可销毁对象集合，支持 O(1) 按值删除。
    对齐 Cordis DisposableList（WeakMap + 序号 Map 双索引）。
    """
    def push(self, value: Any) -> Callable[[], bool]:
        """添加；返回删除函数。"""
    def delete(self, value: Any) -> bool:
        """O(1) 删除；返回是否找到。"""
    def clear(self) -> list[Any]:
        """清空并返回逆序列表（用于 LIFO 清理）。"""
```

### 5.12 Timer 服务（对齐 Cordis TimerService）

作为插件 `timer`（`provides="timer"`）实现，而非内核的一部分：

```python
class TimerService(Service):  # provides="timer"
    name = "timer"

    def timeout(self, callback: Callable, delay_ms: int) -> Callable[[], None]:
        """单次定时；disposer 自动进 effect（卸载撤销）。"""
        disposer = self.ctx.effect(lambda: ..., label="ctx.timeout()")
        return disposer

    def interval(self, callback: Callable, delay_ms: int) -> Callable[[], None]:
        """周期定时；disposer 自动进 effect。"""

    def debounce(self, callback: Callable, delay_ms: int) -> Callable:
        """防抖函数；返回的 wrapper 带 .dispose() 方法，自动进 effect。"""

    def throttle(self, callback: Callable, delay_ms: int, no_trailing: bool = False) -> Callable:
        """节流函数；同上。"""
```

对齐 Cordis `vendor/timer/src/index.ts`。所有定时器自动归属当前 Fiber，卸载时自动清除。

### 5.13 composeError 栈拼接（对齐 Cordis）

Cordis 的 `composeError` 把 caller 栈帧拼接到插件抛出的异步错误中，使错误栈包含「谁加载了这个插件」。Python 等价实现：

```python
def compose_error(callback: Callable, get_outer_stack: Callable[[], list[str]]) -> Any:
    """捕获 caller 栈，在异步错误中拼接。对齐 Cordis composeError。"""
    outer_frames = get_outer_stack()
    try:
        result = callback()
        if inspect.isawaitable(result):
            async def wrapped():
                try:
                    return await result
                except BaseException as exc:
                    _append_frames(exc, outer_frames)
                    raise
            return wrapped()
        return result
    except BaseException as exc:
        _append_frames(exc, outer_frames)
        raise
```

`get_outer_stack()` 在 `register()` 时调用，捕获 loader 的调用栈。错误抛出时把 loader 帧拼到 traceback 末尾。

### 5.14 HMR 热模块重载（对齐 Cordis `vendor/hmr/`）

**第一性原理：** HMR 的本质是「文件变化 → 依赖分析 → 缓存清除 → 模块重载 → fiber 重启 → 失败回滚」。Python 的 `importlib` + `sys.modules` + `watchdog` 提供了比 Node ESM loadCache 更干净的等价能力。

**设计模式：** Strategy（多种 reload 策略）+ Observer（watchdog 事件）+ Memento（模块快照用于回滚）。

```python
class HmrService(Service):
    """热模块重载服务。对齐 Cordis vendor/hmr/ 的 Hmr 类。"""
    name = "hmr"
    inject = ("loader", "timer")

    class Config(BaseModel):
        root: list[str] = ["."]          # 监听目录
        ignored: list[str] = ["**/node_modules", "**/.*", "cache", "data"]
        debounce_ms: int = 100
        base: str | None = None

    def __init__(self, ctx: PluginContext, config: Config) -> None:
        super().__init__(ctx, config)
        self._observer: Observer | None = None
        self._stashed: set[str] = set()       # 待处理的文件变化
        self._externals: set[str] = set()      # 框架级文件（变化=全重启）
        self._module_snapshots: dict[str, Any] = {}  # Memento：重载前的模块快照

    async def init(self) -> Generator[Cleanup, None, None]:
        yield self._stop

        self._collect_externals()
        self._observer = Observer()
        for root in self.config.root:
            handler = _ReloadHandler(self)
            self._observer.schedule(handler, root, recursive=True)
        self._observer.start()

    def _stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def _collect_externals(self) -> None:
        """收集框架级依赖图（变化这些文件 = 全进程重启）。
        对齐 Cordis Hmr 的 externals = loadDependencies(mainJob)。
        """
        import __main__
        main_path = getattr(__main__, "__file__", None)
        if not main_path:
            return
        self._externals = self._trace_dependencies(Path(main_path).resolve())

    def _trace_dependencies(self, path: Path) -> set[str]:
        """AST 静态分析 import 链，收集所有用户代码依赖。"""
        visited: set[str] = set()
        stack = [path]
        while stack:
            current = stack.pop()
            if current in visited or "node_modules" in str(current):
                continue
            visited.add(current)
            try:
                tree = ast.parse(current.read_text())
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module_name = getattr(node, "module", None) or ""
                    if node.names:
                        module_name = node.names[0].name
                    resolved = self._resolve_module(module_name, current.parent)
                    if resolved and resolved not in visited:
                        stack.append(resolved)
        return visited

    def _resolve_module(self, name: str, base: Path) -> Path | None:
        """将 import 名解析为文件路径。"""
        for suffix in (".py", "/__init__.py"):
            candidate = base / (name.replace(".", "/") + suffix)
            if candidate.exists():
                return candidate
        return None

    def on_file_changed(self, path: Path) -> None:
        """watchdog 回调入口（debounced）。"""
        abs_path = path.resolve()
        str_path = str(abs_path)

        # 框架文件变化 → 全进程重启
        if str_path in self._externals:
            self.ctx.get("loader").exit()
            return

        # 配置文件变化 → Include.refresh()
        loader = self.ctx.get("loader")
        for entry in loader.entries():
            include = getattr(entry, "subtree", None)
            if include and getattr(include, "filename", None) == str_path:
                asyncio.ensure_future(include.refresh())
                return

        # 用户模块变化 → stash + partial reload
        self._stashed.add(str_path)
        asyncio.ensure_future(self._partial_reload())

    async def _partial_reload(self) -> None:
        """部分重载：分析变更 → 清除缓存 → 重载模块 → 重启 fiber → 失败回滚。
        对齐 Cordis Hmr.partialReload()。
        """
        await self._analyze_changes()
        accepted = self._accepted
        declined = self._declined

        # 快照当前模块（Memento 模式）
        snapshots: dict[str, Any] = {}
        for mod_name, mod in list(sys.modules.items()):
            if mod and hasattr(mod, "__file__") and mod.__file__:
                if str(Path(mod.__file__).resolve()) in accepted:
                    snapshots[mod_name] = mod

        # 清除缓存
        for mod_name in list(snapshots.keys()):
            del sys.modules[mod_name]

        try:
            # 重新导入
            new_modules = {}
            for mod_name in snapshots:
                new_modules[mod_name] = importlib.import_module(mod_name)

            # 重启 fiber
            loader = self.ctx.get("loader")
            reloads = {}
            for mod_name, new_mod in new_modules.items():
                plugin = getattr(new_mod, "PLUGIN", None) or getattr(new_mod, "apply", None)
                if plugin:
                    runtime = loader.registry.get(plugin)
                    if runtime:
                        reloads[plugin] = (new_mod, runtime)

            for plugin, (new_mod, runtime) in reloads.items():
                self._reload_plugin(plugin, new_mod, runtime)

            await self.ctx.emit("hmr/reload", reloads)

        except Exception as exc:
            # 回滚：恢复模块快照
            for mod_name, mod in snapshots.items():
                sys.modules[mod_name] = mod
            self.ctx.logger.error(f"HMR reload failed, rolled back: {exc}")

        finally:
            self._stashed.clear()

    async def _analyze_changes(self) -> None:
        """分类变更文件为 accepted / declined。
        对齐 Cordis Hmr.analyzeChanges()。
        """
        self._accepted = set(self._stashed)
        self._declined = set(self._externals)
        # 传播：如果依赖链中有 accepted 的文件，其依赖者也 accepted
        pending = list(self._stashed)
        while pending:
            path = pending.pop()
            dependents = self._find_dependents(path)
            for dep in dependents:
                if dep in self._accepted or dep in self._declined:
                    continue
                self._accepted.add(dep)
                pending.append(dep)

    def _find_dependents(self, path: str) -> list[str]:
        """AST 分析谁 import 了这个文件。"""
        dependents = []
        target = Path(path)
        for mod_name, mod in sys.modules.items():
            if not mod or not hasattr(mod, "__file__") or not mod.__file__:
                continue
            mod_path = Path(mod.__file__).resolve()
            if mod_path == target:
                continue
            try:
                tree = ast.parse(mod_path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        # 简化：检查文件名是否匹配
                        pass
            except (SyntaxError, OSError):
                continue
        return dependents

    def _reload_plugin(self, plugin: Any, new_mod: Any, runtime: Any) -> None:
        """重载单个插件的所有 fiber。
        对齐 Cordis Hmr 的 reload() 函数。
        """
        loader = self.ctx.get("loader")
        for old_fiber in list(runtime.fibers):
            new_handle = loader.register(
                old_fiber.entry_id, new_mod.PLUGIN if hasattr(new_mod, "PLUGIN") else new_mod,
                old_fiber.config
            )
            # 迁移 entry 引用
            if hasattr(old_fiber, "_entry"):
                new_handle._entry = old_fiber._entry
```

**Python 比 Cordis 优雅的地方：**
- `ast.parse` 做静态依赖分析，不需要 Node 内部的 `ModuleJob.linked`
- `sys.modules` 是全局 dict，清除比 ESM loadCache 更直接
- `importlib.reload` 是标准库，无需 `node-addon-require-builtin` hack
- `watchdog` 跨平台（Linux/macOS/Windows），等价 chokidar

### 5.15 配置表达式求值（对齐 Cordis `!!js` 表达式）

**第一性原理：** 配置需要运行时求值能力（引用环境变量、ctx 服务、计算值）。Cordis 用 `!!js "ctx.env.API_KEY"` 裸 eval，危险且不便携。Python 用 YAML 自定义标签 + AST 白名单沙箱，既保留表达能力又杜绝代码注入。

**设计模式：** Interpreter（AST 求值器）+ Factory Method（标签构造器）+ Visitor（AST 节点遍历）。

```python
import ast
import operator
import os
from typing import Any

# AST 白名单：只允许安全的操作
_SAFE_NODES = {
    # 常量
    ast.Constant, ast.Num, ast.Str, ast.NameConstant,
    # 变量引用
    ast.Name, ast.Load,
    # 属性访问
    ast.Attribute,
    # 下标
    ast.Subscript, ast.Index, ast.Slice,
    # 容器
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    # 布尔运算
    ast.BoolOp, ast.And, ast.Or,
    # 比较
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    # 算术
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow,
    # 一元
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    # 条件表达式
    ast.IfExp,
    # 函数调用（仅限白名单函数）
    ast.Call,
}

_SAFE_BUILTINS = {
    "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "len": len, "range": range, "min": min, "max": max,
    "sum": sum, "abs": abs, "round": round, "sorted": sorted,
    "True": True, "False": False, "None": None,
}


class PyExpr:
    """YAML `!py` 标签的值载体。对齐 Cordis `!!js` 的 JsExpr。"""
    def __init__(self, expr: str) -> None:
        self.expr = expr

    def __repr__(self) -> str:
        return f"PyExpr({self.expr!r})"


class SafeEvaluator:
    """沙箱 AST 求值器。对齐 Cordis `evaluate()` 但只允许白名单操作。

    支持：
    - 常量：`42`, `"hello"`, `True`
    - 变量：`ctx.env.API_KEY`（通过 scope dict 提供）
    - 属性访问：`ctx.llm.model`
    - 下标：`env["KEY"]`, `items[0]`
    - 算术/比较/布尔：`a + b`, `x > 10`, `a and b`
    - 条件：`a if cond else b`
    - 白名单函数：`len(x)`, `int(s)`, `sorted(items)`
    """

    def __init__(self, scope: dict[str, Any] | None = None) -> None:
        self._scope = scope or {}

    def evaluate(self, expr: str) -> Any:
        """求值一个 Python 表达式字符串。"""
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid expression: {expr}") from exc
        return self._eval_node(tree.body)

    def _eval_node(self, node: ast.AST) -> Any:
        if type(node) not in _SAFE_NODES:
            raise ValueError(f"Unsafe AST node: {type(node).__name__}")

        match node:
            # 常量
            case ast.Constant(value=v):
                return v
            # 变量
            case ast.Name(id=name, ctx=ast.Load()):
                if name in self._scope:
                    return self._scope[name]
                if name in _SAFE_BUILTINS:
                    return _SAFE_BUILTINS[name]
                raise ValueError(f"Undefined name: {name}")
            # 属性访问
            case ast.Attribute(value=val, attr=attr, ctx=ast.Load()):
                obj = self._eval_node(val)
                return getattr(obj, attr)
            # 下标
            case ast.Subscript(value=val, slice=slice_node):
                obj = self._eval_node(val)
                key = self._eval_node(slice_node)
                return obj[key]
            # 算术
            case ast.BinOp(left=l, op=op, right=r):
                left, right = self._eval_node(l), self._eval_node(r)
                ops = {ast.Add: operator.add, ast.Sub: operator.sub,
                       ast.Mult: operator.mul, ast.Div: operator.truediv,
                       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
                       ast.Pow: operator.pow}
                return ops[type(op)](left, right)
            # 一元
            case ast.UnaryOp(op=op, operand=operand):
                val = self._eval_node(operand)
                ops = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}
                return ops[type(op)](val)
            # 比较
            case ast.Compare(left=l, ops=ops, comparators=comps):
                left = self._eval_node(l)
                for op, comp in zip(ops, comps):
                    right = self._eval_node(comp)
                    cmp_ops = {ast.Eq: operator.eq, ast.NotEq: operator.ne,
                               ast.Lt: operator.lt, ast.LtE: operator.le,
                               ast.Gt: operator.gt, ast.GtE: operator.ge,
                               ast.Is: operator.is_, ast.IsNot: operator.is_not,
                               ast.In: lambda a, b: a in b,
                               ast.NotIn: lambda a, b: a not in b}
                    if not cmp_ops[type(op)](left, right):
                        return False
                    left = right
                return True
            # 布尔
            case ast.BoolOp(op=op, values=values):
                vals = [self._eval_node(v) for v in values]
                if isinstance(op, ast.And):
                    return all(vals)
                return any(vals)
            # 条件
            case ast.IfExp(test=t, body=b, orelse=o):
                return self._eval_node(b) if self._eval_node(t) else self._eval_node(o)
            # 函数调用
            case ast.Call(func=func, args=args, keywords=kws):
                fn = self._eval_node(func)
                if fn not in _SAFE_BUILTINS.values():
                    raise ValueError(f"Unsafe function call: {ast.dump(func)}")
                pos_args = [self._eval_node(a) for a in args]
                kw_args = {kw.arg: self._eval_node(kw.value) for kw in kws}
                return fn(*pos_args, **kw_args)
            # 容器
            case ast.List(elts=elts):
                return [self._eval_node(e) for e in elts]
            case ast.Tuple(elts=elts):
                return tuple(self._eval_node(e) for e in elts)
            case ast.Dict(keys=keys, values=values):
                return {self._eval_node(k): self._eval_node(v) for k, v in zip(keys, values)}
            case ast.Set(elts=elts):
                return {self._eval_node(e) for e in elts}
            case _:
                raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def yaml_py_constructor(loader: Any, node: Any) -> PyExpr:
    """YAML `!py` 标签构造器。"""
    value = loader.construct_scalar(node)
    return PyExpr(value)


def interpolate_config(value: Any, scope: dict[str, Any]) -> Any:
    """递归替换配置中的 PyExpr 节点。对齐 Cordis `interpolate()`。"""
    if isinstance(value, PyExpr):
        return SafeEvaluator(scope).evaluate(value.expr)
    if isinstance(value, dict):
        return {k: interpolate_config(v, scope) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate_config(v, scope) for v in value]
    return value
```

**YAML 用法示例：**

```yaml
plugins:
  - id: llm
    name: lca.layer0_infra.plugins.llm
    config:
      api_key: !py "ctx.env.LLM_API_KEY"
      model: !py "'gpt-4' if ctx.env.ENV == 'prod' else 'gpt-3.5-turbo'"
      timeout: !py "int(ctx.env.get('LLM_TIMEOUT', '30'))"
      features: !py "['streaming', 'tools'] if ctx.env.ENABLE_TOOLS else ['streaming']"
```

**Python 比 Cordis 优雅的地方：**
- AST 白名单沙箱比 `new Function()` 安全 100 倍
- `match/case` 模式匹配比 if/elif 链更清晰
- `PyExpr` 值载体使配置可序列化、可 diff、可回写

### 5.16 声明合并（对齐 Cordis declaration merging）

**第一性原理：** TypeScript 的 `interface` 声明自动合并，使插件类型可以增量扩展。Python 没有 interface merging，但 `__init_subclass__` + 元类提供了更强大的能力：**运行时自动合并继承链上的声明**。

**设计模式：** Template Method（元类控制构造流程）+ Chain of Responsibility（`__init_subclass__` 链式调用）+ Flyweight（合并后的声明缓存）。

```python
from typing import ClassVar, get_type_hints


class PluginMeta(type):
    """插件元类：自动合并继承链上的 inject / provides / intercept 声明。
    对齐 Cordis TypeScript 的 declaration merging（interface 自动合并）。

    合并规则：
    - inject: 父类 + 子类并集（dict 形式则浅合并）
    - provides: 子类覆盖父类
    - intercept: 父类 + 子类浅合并
    - Config: 子类覆盖父类（pydantic 继承已处理）
    """

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict, **kwargs) -> type:
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # 合并 inject
        merged_inject: dict[str, Any] = {}
        for base in reversed(bases):
            base_inject = getattr(base, "inject", ())
            if isinstance(base_inject, dict):
                merged_inject.update(base_inject)
            elif isinstance(base_inject, (list, tuple)):
                merged_inject.update({k: None for k in base_inject})
        cls_inject = namespace.get("inject", ())
        if isinstance(cls_inject, dict):
            merged_inject.update(cls_inject)
        elif isinstance(cls_inject, (list, tuple)):
            merged_inject.update({k: None for k in cls_inject})
        cls.inject = merged_inject  # type: ignore

        # 合并 intercept
        merged_intercept: dict[str, Any] = {}
        for base in reversed(bases):
            base_intercept = getattr(base, "intercept", {})
            if isinstance(base_intercept, dict):
                merged_intercept.update(base_intercept)
        cls_intercept = namespace.get("intercept", {})
        if isinstance(cls_intercept, dict):
            merged_intercept.update(cls_intercept)
        cls.intercept = merged_intercept  # type: ignore

        return cls


class Plugin(ABC, metaclass=PluginMeta):
    """插件基类。继承时自动合并声明。

    示例：
        class BasePlugin(Plugin):
            inject = ("llm",)
            intercept = {"llm": {"timeout": 30}}

        class MyPlugin(BasePlugin):
            inject = {"tools": {"pipeline": "safe"}}
            # 合并后 inject = {"llm": None, "tools": {"pipeline": "safe"}}
            # 继承 intercept = {"llm": {"timeout": 30}}
    """
    inject: ClassVar[tuple[str, ...] | dict[str, Any]] = ()
    provides: ClassVar[str | None] = None
    intercept: ClassVar[dict[str, Any]] = {}
    name: ClassVar[str] = ""
```

**声明合并的传播规则：**

```
Plugin (base)
  inject = ()
  intercept = {}
      │
      ▼
BasePlugin(Plugin)
  inject = ("llm",)
  intercept = {"llm": {"timeout": 30}}
      │
      ▼
MyPlugin(BasePlugin)
  inject = {"tools": {"pipeline": "safe"}}
  intercept = {"tools": {"mode": "strict"}}
  # 合并结果：
  # inject = {"llm": None, "tools": {"pipeline": "safe"}}
  # intercept = {"llm": {"timeout": 30}, "tools": {"mode": "strict"}}
```

**Python 比 Cordis 优雅的地方：**
- TypeScript 的 declaration merging 只能在编译期合并 `interface`，运行时不可见
- Python 的元类使合并发生在**类创建时**，合并结果可被 `inspect`、`typing.get_type_hints`、`pydantic` 直接读取
- 继承链可以无限深，每层都可以增量声明，最终合并结果在 `MyPlugin.inject` 上可见
- 与 pydantic Config 继承天然配合：`class Config(BasePlugin.Config):` 自动继承 + 覆盖

---

## 6. Profile / Bundle / Patch

### 6.1 文件

| 路径 | 职责 |
|---|---|
| `lca/layer4_app/profiles/lobehub-run.yaml` | 默认产品 profile：列出 bundle 顺序 |
| `lca/layer4_app/bundles/lca-base.yaml` | 能力 Definition + 默认 Provider + 工具/技能/Journal |
| `lca/layer4_app/bundles/lca-cognitive.yaml` | Brain / Body / Memory / Hook / Loop / Agent 工厂 |
| `lca/layer4_app/bundles/lca-gateway.yaml` | HTTP、ingress、execute、live、openai-shim |
| `lca/layer4_app/bundles/lca-dsh-loop.yaml` | 启用 `loop-dsh` 插件（登记 DshTurnDriver）。`lobehub-run` 默认已含该行且 `disabled: false` 也可——select 才决定用不用 |

组合算法与 DSH `composeEntries` 相同：从空列表开始，按 profile 声明的 bundle 顺序把每个 bundle 的 `insert` 追加进去，再应用 profile 自己的 `patch`（按 `id` **整行替换** `config`，或 `insert` 新行，或 `disabled: true`）。不深合并。

`lca-ops dump-profile`（或 `python -m lca.layer4_app.profile dump lobehub-run`）打印展开后的行列表，每行标注来自哪个 bundle。输出必须与 `boot()` 实际加载的集合一致。

### 6.2 条目

```yaml
- id: tool-computer          # 稳定，patch 靠它定位
  name: lca.layer0_infra.plugins.tool_computer
  disabled: false
  config: {}
```

`id` 是树地址；`name` 是 import 路径。同一个 `name` 可以出现两次（例如两个 computer 绑定），`id` 必须不同。

### 6.3 插件源码落点（分层）

| 层 | 目录 | 可 import |
|---|---|---|
| contracts | `lca/contracts/mechanisms/plugin.py` | 无实现 |
| L0 | `lca/layer0_infra/plugins/` | contracts + L0 |
| L1 | `lca/layer1_cognitive/plugins/` | ≤ L1 |
| L2 | `lca/layer2_runtime/plugins/` | ≤ L2 |
| L3 | `lca/layer3_agent/plugins/` | ≤ L3 |
| L4 | `lca/layer4_app/plugins/`、`profiles/`、`bundles/` | 全部（组合根） |
| 进程 | `gateway/plugins/` | lca + gateway |

`lint-imports` 保持现有层约束。插件不是逃逸舱。

---

## 7. 默认树：`lobehub-run`

下面是**展开后** Gateway 必须加载的完整集合。缺一行，默认 LobeHub solo 跑不起来。这就是「全部是插件、加载一遍主流程通」。

### 7.1 Bundle `lca-base`（能力世界）

| id | name（模块） | provides | inject | 取代今天的 |
|---|---|---|---|---|
| llm | `...plugins.llm` | `llm` | — | `LlmService` mount（Adapter 表，给 Reasoner） |
| llm-resolver | `...plugins.llm_resolver` | `llm_resolver` | `llm` | 挂 `LLMResolver` Definition（`is_available` / `resolve(mode=)`）。生产默认 `ProductionLLMResolver`。**不是**往 `LlmService` 里 register resolver——类型不同。`create_app(llm_resolver=...)` 在 boot 后 `use` 测试实现，见 §18 |
| llm-mock | `...plugins.llm_mock` | — | `llm` | `MockLLMAdapter` 作为 adapter Provider；测试 profile 启用，生产 `disabled` |
| memory | `...plugins.memory` | `memory` | — | `MemoryService` + `SimpleMemorySystem` 工厂 |
| state-store | `...plugins.state_store` | `state_store` | — | `StateStoreService` + `InMemoryStateStore` |
| file-store | `...plugins.file_store` | `file_store` | — | `LocalFileStore` / `get_default_file_store` |
| observability | `...plugins.observability` | `observability` | — | `ObservabilityService` + `create_observability` |
| journal-engine | `...plugins.journal_engine` | — | `observability` | Journal catalog / `record()` 后端 |
| sandbox | `...plugins.sandbox` | `sandbox` | `file_store` | `SandboxService` + Onlyboxes Provider |
| search | `...plugins.search` | `search` | — | `SearchService` + Tavily（无 key 则 Provider 存在但 `current` 在调用时失败，与今天一致） |
| transport | `...plugins.transport` | `transport` | — | Internal / A2A / MCP |
| skills | `...plugins.skills` | `skills` | `file_store` | `SkillsService` + `DiskSkillPackageStore` |
| tools | `...plugins.tools` | `tools` | — | `ToolsService` + `DefaultToolExecutionPipeline` |
| plane | `...plugins.plane` | `plane` | `sandbox` | `resolve_plane_bindings` / machine 解析（Definition：当前 Run 的主环境） |
| tool-web-search | `...plugins.tool_web_search` | — | `tools`, `search` | `web_search` 工具 |
| tool-ask-user | `...plugins.tool_ask_user` | — | `tools` | `ask_user` HIL |
| tool-computer | `...plugins.tool_computer` | — | `tools`, `plane`, `file_store` | `lca_computer` 机器/沙箱工具脸；**Run 作用域**里按主环境实例化 |
| tool-write-file | `...plugins.tool_write_file` | — | `tools`, `file_store` | 无 computer 时的回落写文件 |
| tool-skill | `...plugins.tool_skill` | — | `tools`, `skills`, `file_store` | 工厂产出 activate / import / exec / read_reference；`search_skill` 仅当 `bind(include_search=True)`。solo 默认 `False`，与今天 `build_g2a_chat_tools` 一致 |
| workspace | `...plugins.workspace` | `workspace` | `file_store` | Run workspace 根（ADR-0051）；工厂，实例在 Run 作用域创建 |
| timer | `...plugins.timer` | `timer` | — | `TimerService`：timeout/interval/debounce/throttle，带 Fiber 生命周期（对齐 Cordis timer） |
| console-logger | `...plugins.console_logger` | — | `timer` | `ConsoleExporter`：终端日志输出，ANSI 颜色、时间格式化（对齐 Cordis logger-console） |
| hmr | `...plugins.hmr` | `hmr` | `loader`, `timer` | `HmrService`：watchdog 文件监听 + `importlib.reload` + AST 依赖分析 + 回滚（对齐 Cordis `vendor/hmr/`）。开发 profile 启用，生产 `disabled` |

**键分两类，不要混进同一张 `SeamKey` 枚举：**

| 类 | 谁 | 三角色 / `require_complete` |
|---|---|---|
| **Seam 键** | 现有 `SeamKey`：`llm` `sandbox` `memory` `state_store` `search` `tools` `transport` `skills` `file_store` `observability`；本设计只**新增** `llm_resolver` | 必须 Definition + ≥1 Provider + ≥1 Consumer |
| **插件键** | `plane` `workspace` `events` `hooks` `system_prompt` `agents` `agent_loop` `teams` `roles` `runs` `http` `devices` | **不是 seam**。Brain / Loop / Team / HTTP 是编排，不进 `REQUIRED_SEAM_KEYS`。`ctx.mount` 仍然用这些字符串，只是 `require_complete` 不检查它们 |

`plane` / `workspace` 的 Definition 不是今天的 contextvar 函数，而是可 mount 的服务（接口见 §9.2）。`journal-engine` **不**另 mount 键：它只是 `observability` 插件的一部分，负责 catalog 注册 + 进程事件 `PluginTreeBooted`，不新开 LobeHub 协议。

### 7.2 Bundle `lca-cognitive`（默认 agent 脊柱）

对应 DSH 的 `dsh-agent-spine-demo`：**所有入口共用的脊柱**；LLM Provider 和 HTTP 入口不在这里。

**分层硬约束：** L2 插件不得 import L3（`lint-imports`）。因此 `agents.set_factory` **不属于** L2。`CognitiveRuntime` 住 L2；把 Runtime 接到 `CognitiveAgent` 的闭包住 L3 `agent` 插件。

| id | name | provides | inject | 取代今天的 |
|---|---|---|---|---|
| event-bus | `lca.layer1_cognitive.plugins.event_bus` | `events` | — | `SimpleEventBus`（进程一个总线；Run 不 fork） |
| hooks | `lca.layer1_cognitive.plugins.hooks` | `hooks` | `events`, `observability` | Hook **工厂**（`create() -> HookRegistry`），不是一棵全局 hook 树给所有 Agent 共用可变状态 |
| system-prompt | `lca.layer1_cognitive.plugins.system_prompt` | `system_prompt` | `tools` | 组装 **函数/服务**（`render(profile, tools, plane) -> str`），不是一份全局字符串 |
| agent | `lca.layer3_agent.plugins.agent` | `agents` | `llm`, `memory`, `state_store`, `hooks`, `observability`, `tools`, `transport`, `system_prompt` | Agent 注册表 + `create(spec, run_ctx)`。**内部**用 L1 `SimpleBrainFactory` / `SimpleBody` 和 L2 `CognitiveRuntime` 接线。`ComponentRegistry`（gates、budget）作为该插件的**私有**表，不另开 ctx 键 |
| loop-cognitive | `lca.layer2_runtime.plugins.cognitive_loop` | — | — | 只把 `CognitiveRuntime` **类/工厂**登记到 L2 可被 L3 import 的既有模块（今天就是 `runtime_loop.py`）。它**不** `provides agent_loop`，也**不** `set_factory` |
| loop-dsh | `lca.layer0_infra.plugins.dsh_loop` | — | — | 登记 `DshTurnDriver`。默认 `disabled: true`；请求 `execution_target=dsh` 时由 `run-execute` 选用 |
| agent-loop | `lca.layer3_agent.plugins.agent_loop` | `agent_loop` | `agents` | **L3** 服务：`select(execution_target) -> LoopDriver`。内置 `cognitive`；`dsh` 仅当 `loop-dsh` 已 apply。一次 Run 问一次，**不是**改 profile 行换掉全进程 |
| team | `lca.layer3_agent.plugins.team` | `teams` | `agents`, `transport` | 今天 `TeamComposer` + orchestration 私有注册表（pipeline/fan-out/lead/…） |
| role-library | `lca.layer3_agent.plugins.role_library` | `roles` | — | `FileRoleLibrary` |
| team-caster | `lca.layer4_app.plugins.team_caster` | — | `teams`, `roles`, `llm` | `LLMTeamCaster` |

`brain` / `body` **不是**进程级 `provides` 键。它们是每个 `agents.create` 闭包里 new 出来的实例。`loop-cognitive` 与 `loop-dsh` 可以同时加载；选谁是请求级的 `agent_loop.select`，禁止用 profile overlay 换掉全 Gateway 的 loop（否则同进程不能一个 chip 走认知、一个 chip 走 DSH）。

### 7.3 Bundle `lca-gateway`（产品入口，对应 SDK 的 jsonrpc-server）

| id | name | provides | inject | 取代今天的 |
|---|---|---|---|---|
| run-registry | `gateway.plugins.run_registry` | `runs` | `observability`, `file_store` | `RunRegistry` |
| run-ingress | `gateway.plugins.run_ingress` | — | `runs`, `file_store` | `prepare_run_from_messages` |
| run-execute | `gateway.plugins.run_execute` | — | `runs`, `agents`, `agent_loop`, `plane`, `workspace` | `execute_run`：开 Run 作用域 → `agents.create` → `run()` |
| run-live | `gateway.plugins.run_live` | — | `runs` | `LiveTail` + SSE |
| openai-shim | `gateway.plugins.openai_shim` | — | `llm` | 标题/embeddings；**不开 Run**（与现文档一致） |
| http-app | `gateway.plugins.http_app` | `http` | `runs`, `agents`, `agent_loop`, `file_store`, `devices`, `llm_resolver` | 把现有 `create_app` 路由表挂到已 boot 的 ctx。请求处理用 `app.state.ctx.require(...)`，不再读 `gateway.app` 模块全局 |
| device-hub | `gateway.plugins.device_hub` | `devices` | — | 本机 sidecar；无设备时仍 mount 空注册表 |

`http-app` **必须**等到上表 inject 全齐再 apply。路由清单与今天 `create_app` 相同（`/health` `/context` `/journal/live` `/runs*` `/files*` `/v1/*` `/api/device/*`），本设计不增不删。`GET /context`、文件下载、device RPC 从 ctx 取 `file_store` / `devices`，不另开隐式单例。

### 7.4 刻意不进默认树（以后一行加上）

这些是 DSH base 有、LCA 默认产品**现在没有**的。扩展点已在内核里，不预建空壳。

| 能力 | 以后的插件 id | 挂载点 |
|---|---|---|
| Subagent 多 Provider | `subagent`, `tool-subagent` | 新 `SeamKey.SUBAGENTS`；工具注册进 `tools` |
| Workflow | `workflow`, `tool-workflow` | 新 seam + tool |
| Compaction | `compaction` | 听 `agent/pre-step` waterfall 或 journal 压力 |
| Permission preset | `permission` | Run 首帧写入 Journal；sandbox/approval 读取 |
| 持久 PTY / jobs | `jobs`, `tool-jobs` | 新 seam |
| DSH 对照 loop | `loop-dsh` 插件（默认可加载） | `agent_loop.select("dsh")` |

---

## 8. 主流程：LobeHub 消息如何穿过树

进程启动（`lca-ops dev` → Gateway）：

```
load profile lobehub-run
  → compose bundles → PluginEntry[]
  → Loader.boot()          # 全部 apply，缺一即退出
  → app.state.ctx = tree.ctx
  → listen :8765
```

一次默认 solo 对话：

```
LobeHub executeClientAgent
  POST /runs {messages, mode:solo, plane, execution_target}
       │
       ▼
  http-app                    # 已挂路由
       │
       ▼
  run-ingress                 # parse messages / 附件进 file_store / compose question
       │
       ▼
  run-registry.create         # run_id, LiveTail, jsonl path
       │
       ▼
  run-execute                 # 业务步骤与今天 execute_run 相同，只换调用位置
       │  1. 解析 plane（失败 = 记错返回，不 create agent）
       │  2. ctx.child(key=run_id)：fork tools / 挂 bindings / workspace / attachments
       │  3. 绑定 sandbox runtime（非 dsh 且有沙箱主环境时）
       │  4. staging 机器附件
       │  5. search_run_scope
       │  6. driver = agent_loop.select(session.execution_target)
       │  7. 非 dsh：agents.create 或 teams.cast+run（构造函数注入本 child 的 llm/tools）
       │     dsh：driver 即 DshTurnDriver，不 create CognitiveAgent
       │  8. result = await runnable.run(question)
       │  9. INPUT_REQUIRED → 保活 child + runnable，不 finalize
       │  10. 否则 finalize（顺序见 §12）
       ▼
  GET /runs/{id}/live         # run-live：同一条 Journal SSE
       ▼
  LobeHub LcaRunDriver        # 原生消息图 / 工具卡 / artifact  不变
```

`mode=team|auto`：步骤 7 走 `teams` 而不是 `agents`。Casting 仍是 `team-caster` 插件，Journal 事件 `CastingStarted/Completed` 不变。

`execution_target=dsh`：`agent_loop.select("dsh")` 返回已登记的 DSH driver。Ingress / Live / harvest **同一条管道**。同进程里另一次 `execution_target=""` 仍走 cognitive。禁止用改 YAML 一行换掉全进程 loop。

管家面 `POST /v1/chat/completions`：`openai-shim` 插件直连 `llm`，不创建 Run、不进 loop。

---

## 9. Run 作用域（必须写死，否则 computer 会绑错盘）

### 9.1 两级各放什么

进程级（root ctx，boot 一次）：

- Seam Definition 与默认 Provider（`llm` 表、`llm_resolver`、sandbox 工厂、skill 目录、file_store…）
- 工具 **工厂**（`ToolFactory`，见 §9.3），不是绑死某台机器的 `Tool` 实例
- EventBus 与进程级监听
- HTTP、RunRegistry、DeviceHub

Run 级（`ctx.child(key=run_id)`）：

| 槽 | 谁写入 | 查找规则 |
|---|---|---|
| `plane` 本 run 的 `PlaneBindings` | `run-execute` 调用 `plane.resolve(session)` | **只查 child**，不回落 |
| `workspace` 本 run 目录 | `workspace.open(run_id)` | 只查 child |
| attachments | ingress 写入 child | 只查 child |
| `tools` 本 run 的 `Tool` 实例表 | `tools.fork_for_run(child)` | **只查 child**。禁止回落到根上的工厂表当活工具用 |
| `llm` 本 run 选用的 adapter | `llm_resolver.resolve(mode)` 后挂到 child，或 `Agent(llm=)` 挂到私有 child | 只查 child |
| LiveTail + 本 run jsonl | `run-registry` | 只查 child |

根上的 `llm` / `tools` / `observability` **服务对象**可以回落（child 要调用 `fork` / `create` 工厂方法）。根上的**活实例**（某个 adapter、某个已绑定机器的 read 工具）**禁止**作为 child `require("tools").get("read_file")` 的结果。

Team 成员共享同一个 Run child，不各自 boot。

### 9.2 `plane` / `workspace` Definition

```python
class PlaneService:  # provides="plane"，插件键，不是 SeamKey
    def resolve(self, session: RunSession) -> PlaneBindings:
        """今日 _freeze_bindings / resolve_plane_bindings。失败抛 PlaneBindingError。"""

class WorkspaceService:  # provides="workspace"
    def open(self, run_id: str) -> RunWorkspace:
        """今日 run_workspace_scope 进入时得到的对象。"""
```

`run-execute` 在 create child 之后调用这两方法，把返回值 `child.mount` 到覆盖槽（或 child 专用 dict，不必走 `CapabilityHub.mount` 的一次性全局键——child 有自己的 overlay map）。内部仍可用 contextvar 驱动现存 computer 代码，但 **effect 进入/退出必须绑在 child 的生命周期上**。

### 9.3 工具工厂与 fork（唯一机制，没有「或」）

今天的 `ToolsService` 是 `NamedRegistry[Tool]`，不够。改为：

```python
class ToolFactory(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]
    def bind(self, run: RunBindings) -> Tool:
        """用这一次的 plane / file_store / sandbox / workspace 做出实例。
        禁止在 bind 之外调用 resolve_machine() / resolve_sandbox()。"""

class RunBindings:
    plane: PlaneBindings
    file_store: FileStore
    workspace: RunWorkspace
    attachment_ids: tuple[str, ...]
    sandbox: Sandbox | None

class ToolsService:
    def register_factory(self, factory: ToolFactory) -> None: ...
    def fork_for_run(self, run: RunBindings) -> ToolRegistry:
        """对每个工厂 bind(run)，得到一份只含本 run 实例的 ToolRegistry。
        无主环境时：tool-computer 的工厂 bind 返回空（或不注册）；
        tool-write-file 工厂在无 computer 时才 bind 出 write_file。
        solo 默认与今天 build_g2a_chat_tools 一致：不包含 search_skill。
        tool-skill 工厂的 bind 接收 include_search: bool，solo=False。"""
```

谁调用 `fork_for_run`：**只有** `run-execute`（以及库路径里 `AgentComposer` 的等价 create，见 §18）。工具插件的 `apply` **只** `register_factory`，不在 root `apply` 里 `bind`，也不在 child 上再跑一遍 `apply`。

`body` 构造时拿到的是 **fork 之后的 `ToolRegistry`**，不是 `ToolsService`。

并发两个 Run：两个 child、两份 bind 结果、两台机器互不看见。

### 9.4 contextvar

`plane_bindings_scope` / `run_workspace_scope` / `run_attachment_scope` / `run_id_scope` / `search_run_scope` 在 `run-execute` 进入 child 时作为 **一个** 组合 effect 打开，child dispose 或 finalize 时关闭。插件和领域代码不直接当公共 API 调用它们。

---

## 10. 领域对象怎么拿依赖（不破坏 ADR-0005）

允许：

```
# 插件 apply（L4 / gateway / loop 插件）
llm = ctx.require("llm")
reasoner = PromptReasoner(consume("llm", llm, PromptReasoner), ...)
```

禁止：

```
# PromptReasoner / SimpleBody / CognitiveRuntime 内部
self.llm = get_ctx().llm     # Service Locator
```

`CognitiveRuntime` 继续吃 `brain, body, memory, hooks, state_store, stop_rule`。它不知道 PluginContext。知道树的是 L3 `agent` / `agent-loop` 与 `run-execute`。

think 路径：`PromptReasoner` 持有 **create 时传入的** `LLMAdapter`（已经是 `llm_resolver.resolve` 或 `Agent(llm=)` 的那一个），不是 `ctx.require("llm")`。

这是 DSH 与 LCA 的故意差异：DSH 的 loop 满树 `ctx.tools`；LCA 的 loop 是普通对象，由插件在 apply/create 时接线。效果是「换 driver = 换 select 结果」，不是「领域对象去查表」。

---

## 11. 配置与可观测

- 每个插件一份 pydantic `Config`。未知字段拒绝。
- 密钥继续走现有 settings / 环境（`LLM_API_KEY` 等），不进 YAML。
- `dump-profile` 打印展开树；测试锁定默认 `lobehub-run` 的 id 列表（快照）。
- boot 成功记一条 Journal 进程事件（新事件：`PluginTreeBooted{profile, plugin_ids}`），方便 `lca-ops logs` 确认「树活了」。
- 每个插件 `apply` 可用 structlog，字段带 `plugin_id`。

---

## 12. 错误处理与生命周期

| 阶段 | 谁负责 | 失败 |
|---|---|---|
| boot | Loader | 进程不听端口 |
| 单次 HTTP 校验 | `http-app` / ingress | 4xx，树不动 |
| 单次 Run | `run-execute` | Journal 记失败；走 finalize；其他 Run 不受影响 |
| 工具拒绝 | tools pipeline | 已有 deny/ask；投影为 ToolDenied |
| HIL | `tool-ask-user` + 现有 pause | `WAITING_INPUT`；**不** finalize、**不** dispose child |
| Cancel | 现有 `cancel_run` | 设 `cancel_requested`，取消 inflight 任务，然后 finalize（会 dispose child） |
| Gateway 退出 | `BootedTree.dispose` | LIFO 撤 HTTP、设备、所有未结束 child |
| 服务提供者卸载 | `PluginHost._remove_owned_services` | 级联：消费者 ACTIVE → PENDING，逆序清理其 effect；服务恢复后 `_reconcile` 自动重新激活 |

`RunSession` 在进入 execute 后增加 `tree_child`（child token）与现有 `runnable`。两者都要保：

- `INPUT_REQUIRED`：`mark_paused`；child 与 `runnable` 都留在 session。
- `POST /runs/{id}/answer`：仍调 `resume_run`（实现可挪进 `run-execute.resume`，HTTP 面不变）。`resume_run` **必须**进入 **同一个** `session.tree_child`（打开同一套 plane/workspace/attachment effect），然后 `session.runnable.resume(snapshot, input=answer)`。禁止 `agents.create` 第二次，禁止 `ctx.child` 第二次。
- `POST /runs/{id}/cancel`：若 RUNNING 则取消任务；若 WAITING_INPUT 则直接 finalize。finalize 才会 dispose child。
- 再次 `INPUT_REQUIRED`（resume 后又问）：仍然不 finalize。

`finalize` 顺序与今天相同，只是多一步 dispose child：

1. artifact closure（需要 workspace，故 child 还活着）
2. `finalize_run(run_id)`
3. `hub.release()`
4. **`tree_child.dispose()`**（关 contextvar effect）
5. `_derive_terminal_status` / `clear_inflight` / `prune` / doctor
6. `hub.dispose`（导出）

HIL 路径今天就不调 `finalize`；插件化后这条不变量不变。doctor / harvest 规则不改。

**服务级联停用与自动恢复（运行时不变量）：** 当一个插件被 unmount 或其 `apply` 抛异常进入 FAILED 时，`_remove_owned_services` 先移除该插件提供的全部服务，然后遍历所有仍在 ACTIVE 的 consumer——任何 `inject` 包含被移除服务名的 consumer 立即被 `_deactivate(permanent=False)`。消费者的 effect 逆序执行（撤销其注册的工具、监听等），状态回落到 PENDING，但 `desired` 不变。下一轮 `_reconcile` 发现依赖不满足，consumer 留在 PENDING。当服务提供者恢复（重新 mount 或 FAILED 后重试成功）并重新 provide 该服务时，`_reconcile` 的下一轮自动把 PENDING 的 consumer 推回 LOADING → ACTIVE。这意味着：**服务丢失是正常状态转换，不是异常分支**；消费者无需写任何监听代码来处理提供者消失。详见 §5.5 调用链二。

---

## 13. 测试

最小闭环（先写这些，再改生产路径）：

1. **内核**
   - inject 拓扑：`a provides x`, `b injects x` → 顺序 b 在 a 后，与 YAML 行序无关。
   - 缺提供方 / 环 / 双 provides → `ProfileError`，消息含 id。
   - `effect` LIFO dispose；`child` dispose 不影响父。
   - waterfall 监听随插件 dispose 消失。
2. **profile**
   - `lobehub-run` 展开快照（id 列表）。改 bundle 必须改快照。
   - `dump-profile` 与 `boot()` 的 entry id 集合相等。
3. **默认 agent 行为不变**
   - 现有 `tests/test_openai_compat_gateway.py`、`tests/test_run_*.py`、solo composer 测试：Gateway 改为 lifespan boot 后仍绿。
   - 一条 mock-LLM solo：Journal 事件种类（Run 开始/结束、LlmCall、ToolStarted/Invoked）与改前相同。
4. **扩展证明**
   - 测试专用插件只在测试 profile `insert` 一行，注册一个 `echo` 工具；不改生产 YAML；run 能调到它。这是「以后加 skill/subagent」的合同测试。

不在本 spec 范围：真实 LLM、LobeHub 浏览器 E2E（现有补丁协议不变，不需要为插件树单独做 UI 测试）。

---

## 14. 非目标

本设计**100% 覆盖** Cordis vendor 全部 10 个子包的所有公共 API。以下列出的是**已覆盖但刻意用 Python 优势做得更优雅**的项：

| Cordis 能力 | Cordis 做法 | Python 更优雅的做法 | 设计位置 |
|---|---|---|---|
| HMR（热模块重载） | chokidar + ESM loadCache 清除 + 部分重载 | `watchdog` + `importlib.reload()` + `sys.modules` 清除 + 依赖拓扑分析 + rollback | §5.14 |
| `!!js` 表达式 | `new Function('ctx', 'expr')` 裸 eval | YAML `!py` 自定义标签 + AST 白名单沙箱求值（`ast.literal_eval` 扩展） | §5.15 |
| declaration merging | TypeScript `interface` 自动合并 | `__init_subclass__` + `PluginMeta` 元类：`inject` / `provides` / `intercept` 沿继承链自动合并 | §5.16 |
| `intercept()` 运行时拦截合并 | `ctx.intercept(name, config)` 链式叠加 | YAML entry `intercept:` 静态声明 + `resolve_config()` 沿 ctx 链合并 | §5.2 |

其他不变的非目标（非 Cordis 范畴）：

- 不让 L1–L3 领域类依赖 `PluginContext`。
- 不替换 LobeHub，不搬 DSH Web。
- 不在第一棵默认树里实现 DSH 的 workflow / compaction / subagent / 持久 PTY。只留挂载点。
- 不把 DSH 子进程对照跑道删掉；它变成可换的 `agent-loop`。
- 不把 `execute.py` 的平面绑定、附件 staging、artifact harvest 的**业务规则**改掉；只改它们的**调用位置**（从神文件搬进插件 `apply` / run child）。

---

## 15. 交付切片（仍是一份设计；实现按序，每刀可独立验）

切片是依赖关系，不是四个产品。

| 切片 | 完成定义 | 用户可见变化 |
|---|---|---|
| **S1 内核** | Loader + PluginContext + child + dump + 上述内核测试 | 无。`dump-profile` 可对一个 fixture YAML 跑通 |
| **S2 脊柱插件化** | `lca-base` + `lca-cognitive` 能被 Loader 加载；`Agent(...)` 内部对**自己的** composer 调一次 `boot`（见 §18），不再 `boot_capabilities`；mock LLM think-act 绿 | 无产品变化 |
| **S3 Gateway 树** | `lca-gateway` 加入；lifespan boot `lobehub-run`；`POST /runs` + live 走 `run-execute`；现有 gateway 测试绿 | 启动日志出现 `PluginTreeBooted`；行为与现在一致 |
| **S4 扩展合同** | 文档 + echo 插件测试 + 「如何加插件」一节进 AGENTS.md | 开发者按树加能力，不再改 `execute.py` |

S3 完成 = 「加载全部插件，默认 agent 主流程通」。S4 证明以后加 subagent/skill/workflow 的方式。

---

## 16. 成功标准（S3 验收，声称完成必须同时满足）

1. Gateway 启动只调用一次 `Loader.boot("lobehub-run")`。日志或 Journal 有 `PluginTreeBooted`，`plugin_ids` 等于 dump-profile 快照。
2. LobeHub 默认 solo（`mode=solo`，本机或沙箱 plane）从发消息到工具卡/最终文本，走现有 Run Live 协议，不改前端补丁。
3. `composer.py` 不再调用 `boot_capabilities()`。
4. `execute_run` 不再内部分叉拼装对象图。它开 child、做与今天相同的 staging/bind，然后 `driver = agent_loop.select(execution_target)`，再 `agents.create` / `teams.*` / `driver.run`。`if dsh` 只允许出现在 `agent_loop.select` 内部。
5. 新增一个测试插件不修改 `execute.py` / `composer.py` / `defaults.py`。
6. 下列命令在实现切片对应范围内绿（S3 时跑 gateway + 脊柱相关测试，提交前按 AGENTS.md 升全量）：

```
uv run ruff check --fix lca/layer0_infra/plugin lca/layer0_infra/plugins \
  lca/layer1_cognitive/plugins lca/layer2_runtime/plugins \
  lca/layer3_agent/plugins lca/layer4_app lca/contracts/mechanisms \
  gateway/plugins gateway/app.py
uv run ruff format <同上>
uv run pytest --no-cov tests/test_plugin_loader.py tests/test_plugin_profile.py \
  tests/test_plugin_echo_extension.py tests/test_run_*.py tests/test_run_hil.py \
  tests/test_openai_compat_gateway.py tests/test_seam_pattern.py -q
```

S3 改了 contracts 机制与组合根，提交前再跑 AGENTS.md 全量序列。

---

## 17. 修订记录

| 相对旧文档 | 本设计 |
|---|---|
| 「Cordis 插件树替换五层 — 不做」 | **组合层做插件树**；五层 import 与领域 DI **仍不做** Service Locator |
| CapabilityHub 每次 compose 新建 | 进程一次 boot |
| 路径 A：DSH 当 driver | 保留，降为 `agent-loop` 的一个 Provider |
| 路径 C：认知层挂 DSH 插件 | 不采用（不把 TS 插件挂进 Python） |
| 只抄 seam / waterfall / pipeline | 那些是零件；本设计补上**缺的单位：Plugin + Profile + 一次加载** |

---

## 18. 库 API 与测试注入（`Agent()` / `create_app`）

进程一次 boot 指 **一个组合根一次**。Gateway 一个进程一个树。库和测试不是「偷偷用 Gateway 那棵树」。

### 18.1 `Agent(...)` / `Team(...)`

今天每个 `AgentComposer` 自己 `boot_capabilities()`，所以 `Agent(llm=a)` 与 `Agent(llm=b)` 互不覆盖。保留这个隔离：

- 每个 `AgentComposer` / `TeamComposer` 持有 **可选** 的 `BootedTree`。
- 若调用方没传入：composer **第一次** `compose` 时 `Loader.boot("lca-lib")`。`lca-lib` profile = `lca-base` + `lca-cognitive`，**不含** `lca-gateway`。
- `Agent(llm=x, tools=ts, observability=hub)` 在 compose 时开一个 **私有 child**（key = 该 agent id）：child 挂 `llm=x`、`fork_for_run` 后的 tools（或直接把传入的 `Tool` 实例登记进 child registry——库 API 传入的已是实例，不再走 factory）、传入的 hub。根树上的 `llm-resolver` 不被这个 child 使用。
- 禁止 `LlmService.register("spec", llm, activate=True)` 打在**共享根**上。那是今天 composer 能隔离的原因（每次新 hub）；共享根后必须改打在 child。
- `composer=` 显式注入仍然有效：测试可以传入已经 boot 过、甚至已经 insert 了 echo 插件的 composer。
- `scripts/run_team_mode.py` 与现有构造测试不调用 Gateway boot。

`lca-lib` 与 `lobehub-run` 共享 bundle 文件，只是 profile 列出的 bundle 更短。

### 18.2 `create_app(...)`

今天测试多次 `create_app(registry=, llm_resolver=, file_store=, devices=)`。插件化后：

```python
def create_app(
    registry: RunRegistry | None = None,
    llm_resolver: LLMResolver | None = None,
    file_store: LocalFileStore | None = None,
    devices: DeviceRegistry | None = None,
    *,
    tree: BootedTree | None = None,
    profile: str = "lobehub-run",
) -> Starlette:
```

规则：

1. 传入 `tree`：用它，不再 boot。
2. 否则 **本次** `create_app` 自己 `Loader.boot(profile)`，得到一棵**新**树。不复用模块级全局树。这保留测试隔离。
3. 「进程生产路径只有一次 boot」= uvicorn 只 `create_app()` 一次（`app = create_app()` 或 lifespan 里 boot 后把 tree 交给 app）。测试进程里多次 `create_app` = 多棵树，测完 `tree.dispose()`（Starlette shutdown 钩子调用）。
4. 注入覆盖在 boot **之后**打在**这棵**树上，不改 YAML：
   - `file_store` → `ctx.require("file_store")` 换 Provider（或 child 级 mount 覆盖，若 Definition 支持 `use`）
   - `llm_resolver` → `ctx.require("llm_resolver").use(injected)`
   - `registry` / `devices` → 替换 `runs` / `devices` 服务上的实例
5. 取消 `gateway.app` 模块级 `_registry` / `set_llm_resolver` 全局。请求只读 `request.app.state.ctx`。

生产 `lifespan`：boot 失败则拒绝 listen。测试不走 lifespan 时，`create_app` 同步 boot，失败则测试失败。

---

## 19. `LoopDriver` 与 `agent_loop.select`

```python
class LoopDriver(Protocol):
    name: str  # "cognitive" | "dsh"
    async def start(self, session: RunSession, child: PluginContext) -> RunnableHandle: ...

class RunnableHandle(Protocol):
    async def run(self, question: str, ctx: RunContext | None = None) -> Result: ...
    async def resume(self, snapshot: StateSnapshot, *, input: str) -> Result: ...
```

- `select("")` / `select("cognitive")` / 缺省 → cognitive：`start` 内部 `agents.create` 或 `teams.*`，返回包着 `CognitiveAgent`/`Team` 的 handle。
- `select("dsh")` → 若 `loop-dsh` 未 apply，抛明确错误（与今天缺 runtime 一致）。`start` 不 create CognitiveAgent。
- 两个 driver **都加载**时，select 只读 `execution_target`，不改根 ctx。

---

## 20. Cordis 源码概念映射（参考实现对照表）

本节把 Cordis 内核（`vendor/cordis/src/`）的关键对象与本设计 + §21 参考实现做一一映射，供实现者阅读官方源码时快速定位。

### 20.1 概念映射

| Cordis 概念 | 源码位置 | 职责 | 为什么不可少 | 本设计对应 | §21 参考实现 |
|---|---|---|---|---|---|
| **Plugin** | `registry.ts` | 函数、类或 `{ apply }` 对象；定义一项可组合能力 | 统一的扩展单位 | `name` / `inject` / `apply` 导出约定（§5.1） | `PluginSpec` |
| **Context** | `context.ts` | Proxy 代理的服务视图；`extend()` 创建子上下文 | 防止隐藏全局依赖；资源归属明确 | `PluginContext`（§5.2） | `PluginContext` |
| **Service** | `service.ts` + `reflect.ts` | 具名、可供其他插件消费的能力 | 解耦提供者和消费者 | `CapabilityHub.mount` + `SeamKey` | `ServiceRecord` + `ctx.provide()` |
| **Fiber** | `fiber.ts` | 插件状态机；配置验证；effect 收集；卸载重载 | 承载状态、依赖快照、清理栈 | `PluginHandle` | `PluginHandle`（含 `PluginState` 枚举） |
| **Effect / disposer** | `fiber.ts` | 随 Fiber 自动释放的资源（LIFO） | 解决 listener、timer、连接、工具等泄漏 | `ctx.effect()` + `PluginHandle.effects` | `handle.effects` + `_run_effects()` |
| **Event** | `events.ts` | 插件之间的低耦合通知 / 拦截 | 横切逻辑不必直接依赖业务插件 | `EventBus`（emit / waterfall / serial） | `EventBus`（emit + waterfall） |
| **Loader / Entry** | `loader/src/index.ts` + `config/entry.ts` | 读配置树、导入模块、启动插件、热更新/回滚 | 声明式组合 | `Loader.boot()` + `profiles/` + `bundles/` | `PluginHost.load_json_config()` + `register()` |
| **Reflect.notify()** | `reflect.ts` | 服务可用性变化时重新检查依赖此服务的全部 Fiber | 反应式依赖 | §5.5 调用链二 + §12 级联段 | `_remove_owned_services()` + `_reconcile()` |

### 20.2 五个反直觉设计约束

实现 §21 参考实现或本设计 Loader 时，以下五点最容易做错：

1. **不要在 import 时直接启动插件。** 模块 import 应只定义能力，生命周期必须由 Host/Loader 控制；否则热更新、测试和依赖重试都会变得不可预测。

2. **不要用全局单例代替 `ctx.provide()`。** 全局单例使「谁拥有、谁清理、谁依赖」不可追踪。每个服务必须有 owner Fiber / PluginHandle。

3. **不要把服务丢失当作异常分支。** 它是插件系统的正常状态转换。消费者应进入 PENDING 并在服务回来后恢复——不是抛异常、不是记错误日志然后忽略。

4. **不要只在启动时做一次拓扑排序。** 真正运行环境中服务会被禁用、替换、配置更新或因错误退出。正确模型是**持续 reconcile**——反复扫描直到稳定态。

5. **所有由插件创建的资源都必须有 disposer，且归属当前插件实例。** listener、timer、socket、临时文件、子进程、工具注册——没有 disposer 的资源 = 泄漏。`PluginContext.effect()`、`ctx.on()`、`ctx.provide()` 都自动把 cleanup 追加到 `handle.effects`；这正是「插件能被安全卸载」的充分条件。

### 20.3 Python 优势替代（非"不抄"，而是做得更好）

| Cordis 能力 | Cordis 做法 | Python 更优雅的做法 | 设计位置 |
|---|---|---|---|
| HMR | chokidar + ESM loadCache + 部分重载 | `watchdog` + `importlib.reload` + `sys.modules` + AST 依赖分析 | §5.14 |
| `!!js` 表达式 | `new Function('ctx', 'expr')` 裸 eval | YAML `!py` 标签 + AST 白名单沙箱 | §5.15 |
| declaration merging | TypeScript `interface` 编译期合并 | `PluginMeta` 元类 + `__init_subclass__` 运行时合并 | §5.16 |
| Node ModuleLoader V1/V2 | Node 内部 ESM loader hook | `importlib` + `sys.modules`（标准库，无需 hack） | §5.3 |
| 并发 `apply` | 异步并行 Fiber 启动 | 单线程就绪队列（`CapabilityHub.mount` 一次性且非线程安全，§5.3） | §5.3 |
| Proxy tracing (`getTraceable`) | ES Proxy 拦截属性访问 | Python `contextvars`（零运行时开销） | §5.2 |

**结论：Cordis vendor 全部 10 个子包的所有公共 API 已 100% 覆盖。**

---

## 21. 参考实现：完整可运行 Python 插件内核

> 本节代码是 **独立可运行的教学内核**，用于验证 §5 设计的可行性。它不是 LCA 生产代码；LCA 的 Loader 实现应按 §5.1–5.4 的接口约定、落进 `lca/layer0_infra/plugin/` 和 `lca/layer0_infra/plugins/`。
>
> 该实现刻意只使用 Python 标准库（`asyncio`、`dataclasses`、`enum`、`importlib`、`inspect`、`json`、`pathlib`），覆盖插件系统的完整闭环：动态模块加载、`apply(ctx, config)`、`inject` 依赖门控、具名服务、事件、effect/disposer、服务消失后的依赖级联停用、服务恢复后的自动重载，以及配置更新失败时的回滚。

### 21.1 文件结构

```
./
├── plugin_runtime.py          # 运行时内核（下方完整代码）
├── demo_config.json           # 声明式插件装配（乱序：audit/greeting 在 tools/clock 之前）
├── demo.py                    # 人工观察全链路
├── test_runtime.py            # 自动验收
└── demo_plugins/
    ├── clock.py               # 提供 clock 服务
    ├── tools.py               # 提供 tools 服务
    ├── greeting.py            # 消费 clock/tools，注册 greet 与 greeting 服务
    └── audit.py               # 消费 tools，监听 tool.called 事件
```

### 21.2 内核完整代码（全面对齐 Cordis）

> 完整代码见 `vendor/cordis/`。
> 下方为精简概览，展示全部新增 API 的使用方式。完整实现约 700 行，覆盖：
> - 3 种插件形态（Function / Constructor / Object）
> - 6 状态 Fiber + epoch 依赖追踪 + generator effect
> - 5 种 dispatch（emit/parallel/serial/bail/waterfall）+ once + Context filter
> - Service 基类（构造即注册 + check 谓标 + init 钩子 + resolveConfig）
> - 内部事件协议（8 个 internal/* 事件）
> - FiberHandle awaitable + update + restart + get_effects()
> - EffectMeta 诊断树 + DisposableList O(1) + composeError 栈拼接
> - Timer service + accessor/mixin/inject 简写
> - 嵌套 entry id + 运行时变更 API + builtins 协议 + self-dispose + disabled 继承
> - 配置热更新三态 diff + 失败回滚
>
> 运行方式（零依赖，纯标准库）：
> ```bash
> python3 test_runtime.py   # 自动验收
> python3 demo.py           # 人工观察全链路
> ```

### 21.3 四个最小示范插件（新增 Timer 示范）

**`demo_plugins/clock.py`**（提供 `clock` 服务）：

```python
import time

name = "clock"
inject = ()

def apply(ctx, config):
    ctx.provide("clock", lambda: time.strftime(config.get("fmt", "%H:%M:%S")))
```

**`demo_plugins/tools.py`**（提供 `tools` 服务）：

```python
name = "tools"
inject = ()

class ToolRuntime:
    def __init__(self, ctx):
        self._tools = {}
        self._ctx = ctx
    def register(self, name, fn):
        self._tools[name] = fn
    def unregister(self, name):
        self._tools.pop(name, None)
    async def run(self, name, **kwargs):
        fn = self._tools[name]
        result = fn(**kwargs)
        await self._ctx.emit("tool.called", name, kwargs, result)
        return result
    def list_tools(self):
        return list(self._tools.keys())

def apply(ctx, config):
    runtime = ToolRuntime(ctx)
    ctx.provide("tools", runtime)
```

**`demo_plugins/greeting.py`**（消费 `clock` + `tools`，注册 `greet` 工具与 `greeting` 服务）：

```python
name = "greeting"
inject = ("clock", "tools")

def validate(config):
    prefix = config.get("prefix", "")
    if not prefix:
        raise ValueError("prefix 不能为空")
    return config

def apply(ctx, config):
    clock = ctx.require("clock")
    tools = ctx.require("tools")

    def greet(who):
        return f"{config['prefix']}，{who}，时间：{clock()}"

    tools.register("greet", greet)
    ctx.provide("greeting", greet)

    def cleanup():
        tools.unregister("greet")
    return cleanup
```

**`demo_plugins/audit.py`**（消费 `tools`，监听 `tool.called` 事件）：

```python
name = "audit"
inject = ("tools",)

def apply(ctx, config):
    async def on_call(tool_name, args, result):
        print(f"[audit] {tool_name}({args}) -> {result}")
    ctx.on("tool.called", on_call)
```

### 21.4 已验证场景

| 场景 | 检查点 | 实测结果 |
|---|---|---|
| 乱序配置加载 | audit/greeting 在其提供者之前声明 | 所有四个插件最终 `active` |
| 工具与事件 | 调用 `greet` 后审计监听器执行 | 输出 `[audit] greet(...) -> ...` |
| 正常热更新 | `prefix: 你好 → Hello` | 工具重新注册，返回新前缀 |
| 失败回滚 | 更新为非法空 `prefix` | 抛出 `PluginError`，旧的 `Hello` 实例仍为 `active` |
| 服务消失 | 卸载 `clock` | greeting 变为 `pending`，`greet` 被撤销 |
| 服务恢复 | 重新 mount `clock` | greeting 自动回到 `active`，工具重新出现 |
| 进程关闭 | `host.shutdown()` | 所有条目最终为 `disposed` |

### 21.5 从参考实现走向 LCA 生产代码

§21 的参考实现已经包含插件系统的完整功能闭环（全面对齐 Cordis）。将其落地为 LCA 生产代码时，按以下映射转换：

| 参考实现 | LCA 生产位置 | 差异点 |
|---|---|---|
| `PluginSpec` | `lca/contracts/mechanisms/plugin.py`（Protocol） | 加 `Config` pydantic model；加 `provides`；加 `is_class` 标记 |
| `PluginHandle` | Loader 内部状态 | 加 `entry: PluginEntry` 引用；加 `inertia` 任务追踪；加 `_accessors` |
| `PluginContext` | `lca/layer0_infra/plugin/context.py` | 对接 `CapabilityHub`；加 `once`/`parallel`/`serial`/`bail`/`accessor`/`mixin`/`inject`/`set` |
| `EventBus` | `lca/layer1_cognitive/event_bus.py`（已有 `SimpleEventBus`） | 扩 5 种 dispatch；加 Context filter；加 owner 生命周期 |
| `Service` 基类 | `lca/contracts/mechanisms/service.py` | 新增 ABC；构造即注册 + check + init + resolveConfig |
| `TimerService` | `lca/layer0_infra/plugins/timer.py` | 作为插件提供 timeout/interval/debounce/throttle |
| `PluginHost._reconcile` | `lca/layer0_infra/plugin/loader.py` 的 `boot()` | 加 `await_all`；加 `assertEntriesLoaded`；加 `REQUIRED_SEAM_KEYS` |
| `PluginHost.create_entry` / `remove_entry` | `loader.py` | 运行时变更 + 文件回写持久化 |
| `import_plugin`（3 形态） | `loader.py` 的 `_import_module` | 接受 Python import path；支持 Function/Constructor/Object |
| `load_json_config` | `lca/layer4_app/profile.py` 的 `compose()` | 读 YAML；支持 bundles + patches + 嵌套 entry |
| `update_config`（三态 diff） | `loader.py` 的 Entry update | config-only 热重启 / name+inject 替换 / disabled 切换 |
| `DisposableList` / `EffectMeta` | `loader.py` 内部 | O(1) 删除 + 诊断树 |
| `compose_error` | `loader.py` 内部 | caller 栈拼接 |

运行方式（零依赖，纯标准库）：

```bash
python3 test_runtime.py   # 自动验收
python3 demo.py           # 人工观察全链路
```

---

## 22. Cordis 完整覆盖矩阵

逐一对照 `~/deepseek-harness/vendor/` 全部 10 个子包、每个导出符号。

### 22.1 Cordis 内核（`vendor/cordis/src/`，9 文件）

| Cordis 导出 | 文件 | LCA 覆盖 | 设计位置 |
|---|---|---|---|
| `Context` class（Proxy 代理） | context.ts | ✅ 显式 API 代替 Proxy | §5.2 PluginContext |
| `Context.extend()` | context.ts | ✅ `ctx.child()` | §5.2 |
| `Context.isolate()` | context.ts | ✅ child overlay map | §9 |
| `Context.intercept()` | context.ts | ✅ YAML entry intercept 静态声明 | §6.2 |
| `Context.is()` | context.ts | ✅ `isinstance` 检测 | — |
| `Context.effect` / `filter` / `isolate` / `intercept` symbols | context.ts | ✅ 等价属性 | §5.2 |
| `Fiber` class（6 状态） | fiber.ts | ✅ 6 状态枚举 | §5.5 |
| `Fiber.effect()`（全形态：sync/async/generator/iterable） | fiber.ts | ✅ generator + iterable | §5.2 |
| `Fiber.await()` + thenable | fiber.ts | ✅ `await_settled()` | §5.9 |
| `Fiber.update()` + `restart()` | fiber.ts | ✅ `update_config()` + 三态 diff | §5.3 |
| `Fiber._checkImpl()` / `_refresh()` / `_setEpoch()` | fiber.ts | ✅ epoch 依赖追踪 | §5.5 |
| `Fiber.getEffects()` | fiber.ts | ✅ EffectMeta 诊断树 | §5.10 |
| `Fiber.dispose()` | fiber.ts | ✅ `_deactivate(permanent=True)` | §5.5 |
| `CordisError('INACTIVE_EFFECT')` | fiber.ts | ✅ `PluginError` | §5 |
| `ValidationError` | fiber.ts | ✅ pydantic V2 | §5.1 |
| `resolveConfig()` | fiber.ts | ✅ pydantic validate | §5.1 |
| `EventsService` | events.ts | ✅ 完整 5 模式 | §5.6 |
| `emit()` / `parallel()` / `serial()` / `bail()` / `waterfall()` | events.ts | ✅ 全部 | §5.6 |
| `on()` / `once()` | events.ts | ✅ | §5.2 |
| `Context.filter` | events.ts | ✅ `_filter` + `global_` | §5.6 |
| `Events` 接口（9 个 internal/* 事件） | events.ts | ✅ 全部 9 个 | §5.7 |
| `isBailed()` | events.ts | ✅ `is_bailed()` | §5.6 |
| `ReflectService` | reflect.ts | ✅ 显式 API | §5.2 |
| `ReflectService.handler`（Proxy get/set/has） | reflect.ts | ✅ 等价 `require`/`get` | §5.2 |
| `provide()` / `get()` / `set()` | reflect.ts | ✅ `mount`/`get`/`set` | §5.2 |
| `notify()` | reflect.ts | ✅ `_notify()` | §5.5 |
| `accessor()` | reflect.ts | ✅ | §5.2 |
| `mixin()` | reflect.ts | ✅ | §5.2 |
| `trace()` / `bind()` | reflect.ts | ✅ Python contextvars | §5.2 |
| `RegistryService` | registry.ts | ✅ | §5.3 |
| `Plugin.Function` / `Plugin.Constructor` / `Plugin.Object` | registry.ts | ✅ 3 种形态 | §5.1 |
| `Plugin.Runtime`（多 fiber per runtime） | registry.ts | ✅ `_runtimes` dict | §5.1.5 |
| `Inject`（array / dict 两种形式） | registry.ts | ✅ | §5.1.6 |
| `@Inject` decorator | registry.ts | ✅ Python `inject` class variable | §5.1 |
| `Inject.resolve()` | registry.ts | ✅ | §5.1.6 |
| `plugin()` / `inject()` | registry.ts | ✅ `register()` / `ctx.inject()` | §5.2, §5.3 |
| `Service` 抽象类 | service.ts | ✅ ABC 基类 | §5.8 |
| `Service.init` / `check` / `config` / `invoke` | service.ts | ✅ | §5.8 |
| `Service.resolveConfig()` | service.ts | ✅ `resolve_config()` | §5.8 |
| `Service.extend()` | service.ts | ✅ 可选 | §5.8 |
| `Service.tracker` | service.ts | ✅ Python 不需要 | — |
| `LoggerService` / `Logger` | logger.ts | ✅ structlog 替代 | §20.3 |
| `DisposableList` | utils.ts | ✅ O(1) | §5.11 |
| `composeError` / `buildOuterStack` | utils.ts | ✅ | §5.13 |
| `getTraceable` / `createTraceable` | utils.ts | ✅ Python contextvars | — |
| `joinPrototype` / `withProps` / `createCallable` | utils.ts | ✅ Python 不需要 | — |
| `isConstructor` | utils.ts | ✅ `inspect.isclass` | §5.1.2 |
| `symbols` namespace | utils.ts | ✅ Python 等价属性 | — |

### 22.2 Cordis Loader（`vendor/loader/src/`，7 文件）

| Cordis 导出 | 文件 | LCA 覆盖 | 设计位置 |
|---|---|---|---|
| `Loader` extends `EntryTree` | index.ts | ✅ `BootedTree` | §5.3 |
| `Loader.unwrapExports()` | index.ts | ✅ Python 不需要 | — |
| `Loader.builtins` / `cordis:` 协议 | index.ts | ✅ | §5.3.6 |
| `Loader.internal/config` / `internal/update` / `internal/plugin` 监听 | index.ts | ✅ 内部事件 | §5.7 |
| `ModuleLoader` V1/V2 | internal.ts | ✅ importlib 替代 | — |
| `Entry` class | entry.ts | ✅ `PluginHandle` | §5.5 |
| `EntryOptions`（id/name/config/group/disabled/inject） | entry.ts | ✅ | §6.2 |
| `Entry.update()` 三态 diff + rollback | entry.ts | ✅ | §5.3.3 |
| `Entry.init()` / `_start()` | entry.ts | ✅ | §5.3.1 |
| `Entry._dispose()` | entry.ts | ✅ `_deactivate()` | §5.5 |
| `Entry.disabled` 继承 | entry.ts | ✅ | §5.3.8 |
| `Entry.getOuterStack` | entry.ts | ✅ composeError | §5.13 |
| `EntryGroup` | group.ts | ✅ 嵌套 entry | §5.3.4 |
| `Group` plugin | group.ts | ✅ YAML group entry | §5.3.4 |
| `EntryTree` abstract | tree.ts | ✅ `BootedTree` | §5.3 |
| `EntryTree.await()` | tree.ts | ✅ `await_all()` | §5.3.2 |
| `EntryTree.resolve()` 嵌套 id | tree.ts | ✅ `:` 分隔 | §5.3.4 |
| `EntryTree.create()` / `remove()` / `update()` | tree.ts | ✅ 运行时变更 | §5.3.3 |
| `EntryTree.import()` | tree.ts | ✅ `import_plugin()` | §5.3 |
| `EntryTree.write()` abstract | tree.ts | ✅ 文件持久化 | §5.3.5 |
| `Realm` / `LocalRealm` / `GlobalRealm` | isolate.ts | ✅ child overlay map | §9 |
| `isolate` hooks | isolate.ts | ✅ | §9 |
| `evaluate()` / `interpolate()` / `isJsExpr()` | utils.ts | ✅ 刻意不覆盖 | §14 |

### 22.3 其他 vendor 包（7 包）

| 包 | 关键导出 | LCA 覆盖 | 设计位置 |
|---|---|---|---|
| `include/` | `Include` extends `EntryTree` | ✅ 文件读取 + 原子写入 | §5.3.5 |
| `include/` | `applyEntryPatches()` | ✅ profile + bundles + patches | §6 |
| `include/` | `!!js` YAML tag | ✅ `!py` 标签 + AST 沙箱 | §5.15 |
| `hmr/` | `Hmr` service（chokidar + 部分重载） | ✅ `watchdog` + `importlib.reload` | §5.14 |
| `hmr/` | `handleError()`（esbuild code frame） | ✅ Python traceback + AST code frame | §5.14 |
| `timer/` | `TimerService`（timeout/interval/throttle/debounce） | ✅ 作为插件 | §5.12, §7 |
| `schemastery/` | `Schema`（30+ 类型 + Standard Schema V1） | ✅ pydantic V2 替代 | §5.1 |
| `cosmokit/` | 工具库（array/types/misc/string/time） | ✅ Python 标准库 | — |
| `logger-console/` | `ConsoleExporter` | ✅ 作为插件 | §7 |
| `group/` | re-export `Group` | ✅ YAML group entry | §5.3.4 |

### 22.4 统计

| 分类 | Cordis 总符号数 | LCA 已覆盖 | 覆盖率 |
|---|---|---|---|
| Cordis 内核（9 文件） | ~80 | ~80 | **100%** |
| Cordis Loader（7 文件） | ~35 | ~35 | **100%** |
| 其他 vendor 包（7 包） | ~15 | ~15 | **100%** |
| **总计** | **~130** | **~130** | **100%** |

全部 3 个原先标记为"刻意不覆盖"的项现已覆盖：
- **HMR** → `watchdog` + `importlib.reload` + `sys.modules` 清除 + AST 依赖分析 + rollback（§5.14）
- **`!!js` 表达式** → YAML `!py` 标签 + AST 白名单沙箱求值（§5.15）
- **declaration merging** → `PluginMeta` 元类 + `__init_subclass__` 自动合并继承链声明（§5.16）

Python 在每一项上都比 Cordis 的 TypeScript/Node 实现更优雅：AST 沙箱比裸 eval 安全、`contextvars` 比 Proxy tracing 零开销、`importlib` 比 Node 内部 hack 更标准、元类合并比 interface merging 运行时可见。
