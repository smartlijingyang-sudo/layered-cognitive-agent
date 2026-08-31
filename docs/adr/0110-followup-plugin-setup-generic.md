# ADR-0110 follow-up: PluginSetupFn 协变与 PluginDefinition 泛型化

## 状态

**Accepted — 2026-08-31**

承接 ADR-0110 PR-A / PR-E 等落地的 PluginManifest 不可变载体。
本次 follow-up 不改变 PluginDefinition 的字段集合，只修改其类型签名，
以便 88 个 `@plugin` 装饰的 setup 函数（其中 86 个用具体 `Config`
子类形参）能继续通过 mypy 静态校验，而无需在每个 setup 函数上手动
标注形参。

## 背景

`lca/harness/plugin_manifest.py` 既有契约：

```python
PluginSetupFn = Callable[["PluginContext", BaseModel], Awaitable[None]]
```

与 AGENTS.md 第 5 节、`scripts/check_plugin_typing.py:88` 的要求形成
内部矛盾：setup 函数应当形参标注为具体 `MyConfig(BaseModel)` 子类，
但 `Callable[[..., BaseModel], ...]` 在参数位置是**逆变**的，
`MyConfig` 子类签名无法赋给期望 `BaseModel` 的位 —— mypy 会一致报错
"Argument 1 has incompatible type
`Callable[[PluginContext, MyConfig], Coroutine[Any, Any, None]]`;
expected `Callable[[PluginContext, BaseModel], Awaitable[None]]`"。

实际影响面（修改前 baseline）：

| 类别 | 文件数 | 备注 |
|---|---|---|
| `@plugin` 装饰的具体 `Config` 子类 setup | 86 | `lca/plugins/` 几乎全部子目录 + `lca/cognition/team/modes/` + `lca/application/` |
| `dict[str, Any]` 形参的 setup（实际无 pydantic Config） | 2 | `cognitive_loop.py` / `loop_drivers/registry.py`，属于隐性 bug |
| **合计 mypy 报错** | **88** | 修改后归零 |

## 决策

1. **`PluginSetupFn` 改为 `TypeVar` 协变形式**：

   ```python
   from typing import TypeVar
   C = TypeVar("C", bound=BaseModel)
   PluginSetupFn = Callable[["PluginContext", C], Awaitable[None]]
   ```

   `C` 是绑定到 `BaseModel` 子类的 TypeVar；具体 `MyConfig` 子类的 setup
   函数现在自然满足 `PluginSetupFn[MyConfig]`。

2. **`PluginDefinition` 泛型化为 `Generic[C]`，使 `Config: type[C]` 与
   `setup: PluginSetupFn[C]` 共享同一个 TypeVar**。这样：

   - `definition.setup` 在静态层面知道自己期望什么 config；
   - `definition.with_config(config: type[C]) -> PluginDefinition[C]`
     能精确化返回类型；
   - 没有具体 Config 的兜底 stub（譬如 `_disabled_stub`）可用
     `PluginDefinition[Any](...)` 显式实例化。

3. **`plugin(...)` 装饰器签名与 `_wrap` 形参统一为
   `PluginSetupFn[Any] | None`** —— 装饰器入口接受任何具体 Config
   的 setup；具体 Config 在 `_wrap` 内部由 `Config=config_cls` 与
   `setup=fn` 通过泛型推断完成配对。

4. **修复两个 `dict[str, Any]` 形参的 setup**：
   - `lca/cognition/team/modes/cognitive_loop.py::setup`
   - `lca/plugins/loop_drivers/registry.py::setup`

   两处都新增内部 `Config(BaseModel)`（含 `extra="forbid"`），
   `@plugin(..., Config=Config)` 显式声明，setup 形参改为 `Config`
   而非 `dict[str, Any]`，函数体内改用属性访问
   （`config.target` / `config.default`）。bundle YAML
   `bundles/runtime-core.yaml` 中既有的 `config: { target: cognitive }`
   与 `config: { default: cognitive }` 继续工作（pydantic 自动 coercing）。

## 与既有 ADR 的关系

- **ADR-0061 / 0062**（PluginManifest 不变模型）：本次仅修改
  `PluginDefinition` 的类型签名，不新增字段，不改变运行时语义。
- **ADR-0074 PR-2**（PluginDefinition.control 可选段）：新泛型参数
  `C` 与 `contract: PluginContract | None` 正交，不影响任何 contract 字段。
- **ADR-0110 PR-A**（3-key 归一）：`compose_plugin_contract` /
  `_resolve_plugin_contract` 路径不变；本次改动在它们的更底层（Manifest
  形态本身）。
- **AGENTS.md 第 5 节**（公共接口完整类型标注）：本 follow-up 与其一致
  —— 现在 setup 形参的具体 `Config` 标注**真的**能被 mypy 校验了，
  之前的状态是装饰器强制 + mypy 报错的双重矛盾。

## 不变量保持

- `PluginDefinition` 仍是 `@dataclass(frozen=True, slots=True)`，泛型化
  不引入可变性、不破坏 `replace()`。
- `with_config` / `with_module` 仍返回同种不可变实例；返回类型从
  `PluginDefinition` 收紧到 `PluginDefinition[C]`，但所有 `definition: PluginDefinition`
  形参隐式等价于 `definition: PluginDefinition[Any]`，向后兼容。
- `PluginCarrier` Protocol 的 `setup: PluginSetupFn` 改为
  `setup: PluginSetupFn[Any]`，与 Cordis 载体接缝保持同样形状。
- ADR-0110 的 back-compat shim（`logic_address` 合成）路径不变。

## 验证

- `uv run mypy lca tests` 中 `Callable[[PluginContext, ...]` 一类错误
  从 88 → **0**；
- 整体 mypy 错误从 326 → **144**（剩余均为 baseline 中与本次契约无关的
  webserver handler / runtime loop / observability 错误，按约定本次不动）；
- 全量 pytest、ruff check/format、lint-imports、vulture、importlinter
  `kernel-domain-isolation` + `transport-isolation`、
  `scripts/check_kernel_boundary.py` 均按 AGENTS.md 第 6 节"修改
  contracts/Protocol/公共签名"档位跑过。

## 改动文件

| 文件 | 改动 |
|---|---|
| `lca/harness/plugin_manifest.py` | `PluginSetupFn` 改 TypeVar；`PluginDefinition(Generic[C])`；`Config: type[C] \| None`；`setup: PluginSetupFn[C]`；`with_config` / `with_module` 返回 `PluginDefinition[C]` |
| `lca/harness/plugin_declaration.py` | `plugin` 装饰器形参 `PluginSetupFn[Any] \| None`；`_wrap(fn: PluginSetupFn[Any])`；`_lca_definition` 与 `definition_from_plugin` 内的构造改为 `PluginDefinition[Any](...)`，cast 升级到 `PluginSetupFn[Any]` |
| `lca/harness/profile/resolve.py` | `_disabled_stub` 内 `cast("PluginSetupFn[Any]", ...)` 与 `PluginDefinition[Any](...)` |
| `lca/harness/plugin_context.py` | `AuditedPluginContext._definition: PluginDefinition[Any]` |
| `lca/cognition/team/modes/cognitive_loop.py` | 新增内部 `Config(BaseModel)`，`@plugin(Config=Config)`，setup 形参改为 `Config` |
| `lca/plugins/loop_drivers/registry.py` | 同上 |
| `tests/harness/test_plugin_contract_unification.py` | `_resolve` 形参 `PluginDefinition[Any]`，`# type: ignore` 加 `no-any-return` |
