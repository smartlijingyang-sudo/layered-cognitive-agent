# lca/plugins

> 状态：稳定
> 所有者：@lca-maintainers
> schema_version: 3.0.0

## 1. 职责

Harness runtime 的全部插件入口集合。每个插件以单文件形式存在，由 `@plugin` 装饰器声明完整的 manifest（id、provides、requires、layer、kind、effects、functional_group、contract、test_suite）。插件通过 `bundles/*.yaml` 条目以 id 形式激活，由 profile 装配后随 run 启动。

## 2. 不负责

PluginSpec 声明、Profile 解析、运行时调度（这些由 `lca/harness/profile/` 和 `lca/harness/declarative/` 负责）。插件只声明身份、能力、依赖、效果；装配与生命周期由 harness 推进。

## 3. 输入

- `bundles/*.yaml` 装配清单（profile 通过 `$module` 引用插件文件，runtime 通过 id 解析为 manifest）
- profile 树中声明的 capability 需求与 `requires` 闭包

## 4. 输出

- 经 `lca.harness.plugin_api` 暴露的 `@plugin` 装饰器与 Manifest 类型
- 经 `lca.harness.profile.resolve` 解析后注入运行的插件实例

## 5. 插件如何声明

每个插件 = 一个含 `@plugin` 的 `.py` 文件（或一个包内**只有一个**文件含该 id 的 `@plugin`）。装饰器位于 `lca/harness/plugin_api.py`：

```python
from lca.harness.plugin_api import plugin, PluginKind

@plugin(
    id="<domain>.<name>",
    provides=[...],
    requires=[...],
    layer="L0".."L4",
    kind=PluginKind.SEAM | PROVIDER | PRIMITIVE | BRIDGE,
    effects=(EffectClass.FILESYSTEM,),
    functional_group=FunctionalGroup.G5_COGNITION,
    contract=PluginContract(...),
    test_suite="tests/plugins/<dir>/<test>.py",
    description="一句话：做什么 + 不做什么",
)
async def setup_<name>(ctx: PluginContext, config: Config) -> None: ...
```

- `__init__.py` 永远不许出现 `@plugin`。
- id 在一个文件内唯一；同 id 多文件会被 `scripts/check_plugin_shape.py` 第⑤维拦下。
- 每个插件必须被至少一个出厂 bundle 的 `$module` 引用（否则报"孤儿插件"）。
- 完整范式见 [AGENTS.md §5](../../AGENTS.md)。

## 6. 插件如何装配

插件**不**通过 import 路径激活，而通过 id 在 bundle 里登记：

```yaml
# bundles/web-app.yaml（节选）
plugins:
  - id: lca-brain-modular
    $module: lca.plugins.brain.modular
  - id: lca.plugins.observability.journal.default
    $module: lca.plugins.observability.journal.default
```

`lca/harness/profile/resolve.py` 按 `provides→requires` DAG 展开，再由 `boot_resolved_profile()` 按顺序启动。每条 `$module` 必须可导入，且该模块 `@plugin(id=...)` 必须与条目 id 一致；不匹配由 `scripts/check_plugin_shape.py` 第③维拦下。

事件 yaml 与 Pipeline yaml 的 `publishers:` / `consumer_rules:` / `hooks:` / `sinks:` 在 PR-5 之后改为 id 引用；当前形态由 `lca_kernel/events/registry.py` 与 `lca/harness/profile/pipeline_loader.py` 解析。

## 7. 插件如何发现

**不要**用文件枚举列举本目录的插件（路径会随 PR-10 迁移而失效）。改用以下入口：

| 想知道的 | 命令 |
|---|---|
| 某 profile 实际激活了哪些插件 | `./scripts/lca-ops inspect-tree <profile>` |
| 某 id 是哪个插件、装在哪里 | `./scripts/lca-ops why-plugin <id>` |
| 某 capability 由谁提供 | `./scripts/lca-ops why <capability>` |
| 当前 shape 门禁（effects 缺失、双形态残留、同 id 镜像、孤儿插件、死 bundle 引用、`@plugin` in `__init__.py`） | `./scripts/lca-ops audit-plugin-shape` |
| metadata 完整性（contract= / functional_group= / logic_address=） | `uv run python scripts/check_plugin_metadata.py` |

实时清单：`find lca/plugins -name '*.py' | wc -l` 与 `uv run python scripts/check_plugin_metadata.py 2>&1 | head -1`。

## 8. 子目录角色（静态表）

本表只列**目录角色**，不列具体文件路径——具体路径以 `inspect-tree` 输出为准。

| 子目录 | 角色 |
|---|---|
| `brain/` `think/` `perceive/` `memory/` `critic/` `reasoner/` `synthesizer/` `gates/` `control_contributions/` `skill/` `roles/` `insight/` `learning/` `creator/` `strategies/` `loop_drivers/` `phase_graph/` `runtime/` `sensors/` `body/` `profile/` `tools/` `tools/diagnostics/` `tools/cordis_control/` `prompts/` `factories/` `collaboration/` | 按认知闭集或功能群归类的插件（perceive → think → gate → act → reflect → remember → stop） |
| `seams/` `seams/<area>/` | seam 插件树：声明 Protocol 接口（SEAM kind），与 `providers/<area>/` 同 area 的 provider 配对 |
| `providers/` `providers/<area>/` | provider 插件树：填充 seam（PROVIDER kind），命名约定 `<name>_provider.py` |
| `observability/` | spine 派生器、可写矩阵、journal 默认实现等观测五缝插件 |
| `events/` `events/publishers/` `events/sinks/` `events/subscribers/` | 事件总线 publisher/sink/subscriber 组件（在 PR-4 之后全部以 `@plugin` 声明） |
| `transport/` `transport/webserver/` `transport/device_hub/` | 网络传输层（webserver routes、device hub 等） |
| `composer/` `composer/{act,think,perceive,collaboration,runtime,composition}/` | 组合根（plan → agent graph 绑定；fixtures）；在 PR-8 中迁至 `lca/application/composer/` |
| `bundles/` | 插件化 bundle 入口的 Python 形态（多数 bundle 已为 yaml） |
| `events/` 内无 `@plugin` 的子包 | 私有辅助，被同目录的插件文件调用 |

## 9. 副作用

`log:emit`（插件通过 `PluginContext` 发送结构化日志）。

## 10. 失败语义

- 模块导入失败 → `ImportError`；`@plugin` manifest 字段缺失 → `check_plugin_metadata.py` 在 CI 报 critical。
- bundle `$module` 与 `@plugin(id=)` 不一致 → `check_plugin_shape.py` 在 CI 报"死 bundle 引用"。
- 插件启动期抛错 → `lca.harness.profile.resolve` 抛出并终止装配；运行时错误由 plugin 自主抛出。
- `legacy_blacklist.txt` 中登记的插件在 `check_plugin_metadata.py` 报 critical 时豁免（当前为空）。

## 11. 公共入口

- `lca/plugins/` 下插件通过 `lca.harness.plugin_api.plugin` 声明；通过 `lca/harness/profile/resolve.py` 装配。
- `lca/plugins/__init__.py` 仅承载模块级文档串；不导出符号。
- 本目录内除 `composer/` 外的代码不通过 import 路径被外部直接调用；装配以 bundle 为唯一激活真值。
