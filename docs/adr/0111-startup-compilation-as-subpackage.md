# ADR-0111: 启动链路编译化为 `lca-kernel/` 顶层包

> **状态：** Accepted (Superseded by [ADR-0115](./0115-kernel-transport-boundary.md))
> **修订日期：** 2026-08-31
> **落地：** `lca-kernel/` 顶层包 14 文件,`lca/harness/profile/compilation/` 子包方向被 ADR-0115 修订为顶层包;6 个月兼容期到 2027-02-28。
> **配套 ADR：** [ADR-0083](./0083-deepseek-harness-plugin-implementation-plan.md) W1 主链收紧 · [ADR-0085](./0085-plugin-everything-explained.md) 插件哲学 · [ADR-0103](./0103-locked-surface-and-port-policy.md) Gateway/Adapter 锁定面 · [ADR-0105](./0105-package-organization-discipline.md) 包组织纪律 · [ADR-0106](./0106-naming-constitution.md) 命名宪法 · **优先 ADR:**[ADR-0115](./0115-kernel-transport-boundary.md) Kernel/Transport 边界
>
> ⚠️ **本文初版(2026-08-31 上午)规划 `lca/harness/profile/compilation/` 子包 + boot→compile 改名 + 6 文件拆分;被 [ADR-0115](./0115-kernel-transport-boundary.md) 修订方向:kernel 应为 `lca-kernel/` 顶层包,12 文件,保留 `boot_profile` 公共 API(不强制改名)。本 ADR 是新架构方向的执行细则,顶层设计见 [ADR-0115](./0115-kernel-transport-boundary.md)。**

## 修订记录(2026-08-31 被 ADR-0115 锁定)

| 旧内容(初版) | 新内容(ADR-0115 修订) |
|---|---|
| `lca/harness/profile/compilation/` 子包 | `lca-kernel/` 顶层包(独立,跟 `lca/` 平级,不在 `lca/` 树下) |
| 6 文件拆分 | **12 文件**:8 大职责(source/resolve/plan/boot/closure/observability/lifecycle/env/hmr) + stages + trace + errors |
| `boot→compile` 改名 | **删除改名决定**(评审一致反对,保留 `boot_profile / boot_resolved_profile / boot_entries` 公共 API) |
| `_install_observability` 双源 | → `lca-kernel/observability.py` 唯一装配点 + `lca-kernel/trace.py` 独立 trace 数据 |
| `invariant.py` | **删除**(评审 YAGNI,后续 ADR 合并进 `@plugin` 装饰器 `invariants` 字段) |
| 4 个 Public API(`compile_*`) | 公共 API 改名 `compile_profile` 为保留 `boot_profile` 沿用,但**新增 `lca-kernel/__init__.py` 单一公共面**:`compile_profile / run_kernel / stop_kernel / run_kernel_lifespan` |

## 背景

`lca/harness/profile/boot.py`(240 行)同时承担五类职责:

1. **公共 API 门面**:`boot_profile / boot_resolved_profile / boot_entries`
2. **输入适配壳**:把 `ResolvedProfile` 转交给 cordis
3. **生命周期**:`_boot_plugin` 调 `ctx.registry.plugin(...)` 注册 Fiber
4. **观测装配**:`_install_observability` 是观测边界唯一挂点(违反 ADR-0083 §2 "可观测是横切观察" 收敛)
5. **错误处理**:`_dispose_context` 在失败时回收 Fiber

文件名遵循 ADR-0106 §3.2 角色后缀表,应当表达"群归属 + 角色 + 对象":`boot.py` 既不是群、也不是对象,只是个动词,违反宪法强制规则 2。`cordis` 已经提供 `Context` + `Fiber` 生命周期,我们重复实现了 ADR-0062 §4 已经否决的"维护 started[]/disposer 列表"心智模型。

`gateway/app.py` 还残留早期同步 boot 路径 `_load_harness_profile`(注释自陈"lifespan 已接管")和 module-level 副作用 `_configure_structlog()`,违反 C7 控制/观察分离。

参考实现 [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 把 boot 拆为 `packages/boot/app-boot/`,严格按 `src/{index, invariant}.ts` + `tests/*.spec.ts` 形态组织,职责单一、文件名自解释。

## 决定

### 决定 1:把 `boot.py` 拆为 `profile/compilation/` 子包

新建 `lca/harness/profile/compilation/`,把现有 `boot.py` 的内容按职责切分:

| 新文件 | 职责 | 对应 deepseek 借鉴点 |
|---|---|---|
| `compilation/__init__.py` | 公共 API:`compile_profile / compile_resolved / compile_entries`;保留 `boot_profile / boot_resolved_profile / boot_entries` 作为 deprecated alias(转发到新名) | deepseek `app-boot/src/index.ts` 的"门面 + 兼容转发"形态 |
| `compilation/stages.py` | `Stage` 枚举(`SOURCE/RESOLVE/TOPO/PREFLIGHT/FIBER_SPAWN/OBSERVABILITY`)+ `StageTimer` 不可变数据类 | deepseek `Stage` 模式 + `scoped-events.generated.ts` |
| `compilation/fiber.py` | `spawn_fiber(ctx, definition, config) -> AuditedPluginContext`;唯一注册 Fiber 的地方 | deepseek `webserver/src/index.ts` 的 Service-注册-disposer 范式 |
| `compilation/observability.py` | `install_observability(ctx) -> BoundObservability`;**唯一观测装配点**(从 `boot.py` 迁出) | deepseek 观测为独立 seam |
| `compilation/dispose.py` | `dispose_safely(ctx)`;容错 dispose,保留原始异常 | deepseek 清理路径 |
| `compilation/errors.py` | 编译期异常:`StageError / FiberBootError / ObservabilityAssemblyError` | deepseek `invariant.ts` 自描述 |

每个文件 ≤ 150 行,顶部 docstring 严格遵循 PEP 257 + ADR-0085 "Plugin 文档即 Manifest" 形态(开头三段:Pipeline / Public API / Why-dedicated-module)。

### 决定 2:公共 API 改名 `boot_*` → `compile_*`,旧名保留 6 个月 deprecated

```python
# lca/harness/profile/compilation/__init__.py
from lca.harness.profile.compilation.core import compile_resolved
from lca.harness.profile.resolve import resolve_profile

def compile_profile(path: Path | str, *, bootstrap_file_store=None) -> Context:
    """Compile a profile YAML into a booted Cordis Context."""
    resolved = resolve_profile(path)
    return compile_resolved(resolved, bootstrap_file_store=bootstrap_file_store)


# === Deprecated (2026-08-31, retire 2027-02-28) ===
import warnings
def boot_profile(path, *, bootstrap_file_store=None):
    warnings.warn("boot_profile is deprecated, use compile_profile", DeprecationWarning, stacklevel=2)
    return compile_profile(path, bootstrap_file_store=bootstrap_file_store)
```

**理由**:compile 比 boot 精确表达"从声明文本到运行时对象"的转换,与 SQLAlchemy `compile()` / Python `compile()` / LLVM 术语一致。`boot_profile` 作为 deprecated alias 不破坏现有 import 路径(lifespan 内部、tests、scripts/、examples/)。

### 决定 3:`gateway/app.py` 删除死代码,启动只走 lifespan

删除:
- `_load_harness_profile()`(L138–204):注释自陈"lifespan 已接管",实际不会在 uvicorn 路径触发。
- `_configure_structlog()`(L109–117):module-level 副作用,迁给 `lca-logging-config` plugin(由 ADR-0115 单独处理)。
- `_download_file / _get_file_meta`(L96–104):handler 包装,迁给 `gateway/routes/files.py`。

`_registry / _file_store / _devices / _device_hub` 等 module-level 单例改为 `application.state` 上的属性(已经是这样),消除 module-level 副作用。

### 决定 4:每个 plugin 包加 `invariant.py`

仿 deepseek `invariant.ts` 的"包对外契约"形态,在每个 plugin 包添加 `invariant.py`,**只放契约,不放实现**。该文件由 ADR-0112 强制,本 ADR 提供 CLI 工具:

```sh
$ lca-ops diagnose plugin-invariants --all
$ lca-ops diagnose plugin-invariants --plugin lca-observability-assembly
```

### 决定 5:trace 事件从 ADR-0113 注入,本 ADR 不预设事件词表

`compilation/stages.py` 的 `Stage` 枚举是**内部实现细节**,不发 Journal event。启动事件的 Journal 词表由 [ADR-0113](./0113-boot-event-catalog.md) 单独定义,本 ADR 不耦合。

## 与既有 ADR 的衔接

| 既有 | 衔接 |
|---|---|
| ADR-0061 / 0062 插件 Manifest + Fiber boot | 本 ADR 不重写,只把 `boot.py` 迁到 `compilation/`,保持 Manifest 解析 + Fiber 注册语义 |
| ADR-0083 W1 主链收紧 | 本 ADR 是 W1 的"启动链路"具体落地子任务;不与 ADR-0083 的 W0~W8 冲突 |
| ADR-0085 插件哲学 | 本 ADR 把"启动过程也是插件化"的哲学落到文件结构上(每文件一职责,文件名自解释) |
| ADR-0103 locked surface | Gateway 改动只删死代码,不修改 ADR-0103 列出的 wire-shape 路由 |
| ADR-0105 包组织纪律 | `compilation/` 子包 ≤ 7 文件(实际 6),符合"子包规模"上限 |
| ADR-0106 命名宪法 | `compilation/` 是 group 名(隐含 profile group),`stages.py / fiber.py / observability.py / dispose.py / errors.py` 是 subject 名,`spawn_fiber` / `install_observability` / `dispose_safely` 用宪法 §8.1 函数前缀表(`spawn/install/dispose`) |

## CI 门禁

新增 / 复用:

- `scripts/check_plugin_paths.py`(新建):扫所有 profile/bundle,每个 `$module` 路径必须能 `importlib.import_module`;`provides / requires / layer / kind` 必须与 `@plugin` 装饰器声明一致;在 PR pipeline 阻断。
- `scripts/check_package_size.py`(ADR-0105):校验 `compilation/` 子包 ≤ 7 文件、单文件 ≤ 200 行。
- `scripts/check_no_utility_modules.py`(ADR-0106):拦截 `utils.py / helpers.py / manager.py` 等无信息后缀。
- `scripts/check_function_verb_prefix.py`(ADR-0106 §8.1):`compilation/` 内函数必须以 `spawn / install / dispose / compile / resolve / load / register` 等前缀开头。
- `tests/harness/profile/compilation/test_fiber.py`:F iber 启动幂等性 + setup 异常时 dispose 路径。
- `tests/harness/profile/compilation/test_deprecated_alias.py`:验证 `boot_profile` 仍能调用但发 DeprecationWarning。
- `tests/architecture/test_declarative_production_closure.py`(已有,扩展):覆盖 `compilation/` 子包导出。

## 放弃的方案

- **保持 `boot.py` 单文件,只内部拆分函数**:违反 ADR-0106 §3 强制规则 2(文件名必须表达对象),保留"动词文件"的反模式。
- **把 boot 拆成完全独立的 `lca/harness/compilation/` 包**:虽然借鉴 deepseek `boot/app-boot` 是独立的,但 LCA 的 boot 是 profile 解析后的编译阶段,**不是独立问题域**;`profile/compilation/` 更准确表达"它是 profile 的一部分"且改动面更小。已经在 ADR 评审会确认。
- **彻底删 `boot_profile` 旧名不做 alias**:违反 ADR-0083 §10 风险表的"目录迁移破坏导入"行,需要保持 6 个月过渡期。
- **用 deepseek `cordis-plugin-loader` 替代 `$module` 字段**:LCA 是 vendored + Python monorepo,不需要 npm-name resolution;`$module` + 门禁校验(`check_plugin_paths.py`)等价。

## 后果

正面:
- 启动链路每一步文件可独立读懂;新人 0 上下文能拼出"compile = source → resolve → topo → preflight → fiber → observability" 流水线。
- `_install_observability` 从 boot 中迁出,真正变成 ADR-0083 §2 要求的"横切观察 seam"。
- 旧的 `boot_profile` 调用方有 6 个月迁移窗口,scripts/、tests/、examples/ 不需要同步改。
- `gateway/app.py` 减少约 90 行死代码 + module-level 副作用。

负面:
- `boot_profile` 的 deprecated alias 期间,所有调用点会出现 DeprecationWarning,需要批量替换;CI 会先以 warning 形式提示,半年后切 error。
- `compilation/` 子包规模控制在 6 个文件,新增"启动相关"文件需先写 ADR(沿用 ADR-0105 的"先新增,再迁移"路径)。

## 索引

| 主题 | 文档 |
|---|---|
| DeepSeek Harness boot 借鉴 | `~/deepseek-harness/packages/boot/app-boot/src/index.ts` |
| LCA 既有 Profile/Boot | `lca/harness/profile/resolve.py` · `lca/harness/profile/boot.py` · `lca/harness/profile/lifespan.py` |
| 命名宪法 | [`docs/design/naming-constitution.md`](../design/naming-constitution.md) |
| 命名规范附录 | [`docs/specs/naming-conventions.md`](../specs/naming-conventions.md) |
| 包组织纪律 | [`docs/specs/package-organization-discipline.md`](../specs/package-organization-discipline.md) |
| 锁定面与端口策略 | [ADR-0103](./0103-locked-surface-and-port-policy.md) |
| 插件哲学 | [ADR-0085](./0085-plugin-everything-explained.md) |
| DeepSeek Harness 实施计划 | [ADR-0083](./0083-deepseek-harness-plugin-implementation-plan.md) |