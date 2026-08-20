# `~/deepseek-harness` 插件系统与主流程深度分析

> 写于 2026-08-20，读盘式探索（无编辑）。
> 覆盖：核心抽象、加载链路、扩展点机制、Agent 主循环如何消费插件、LCA `lca/packages/` ↔ deepseek-harness `packages/` 1:1 镜像对照。

---

## 1. 插件架构概览

`deepseek-harness`（下文简称 DSH）的插件系统完全建立在 vendored **Cordis** 之上（Cordis 是 Koishi.js 的依赖注入核心，由 DSH 团队用 TypeScript 1:1 移植到 `vendor/cordis/`，再在仓库内做了小规模扩展）。整张图分为四层：

1. **核心容器（cordis）**：`Context` + `Service` + `Fiber` + 事件总线 + 反射层（reflect）。所有"插件"都是 Cordis 插件（`Plugin.Function | Plugin.Constructor | Plugin.Object`）。
2. **加载层（cordis-plugin-loader / cordis-plugin-include / cordis-plugin-group / cordis-plugin-timer / cordis-plugin-hmr）**：负责从 YAML 配置 / profile / bundle / `--patch` 列表构建一棵插件树。
3. **应用包（packages/*）**：每个目录是一个 npm 包（`@deepseek-ai/dsh-*`），内含一个或一组 cordis 插件 + Schemastery 配置 schema。
4. **Bundle / Profile / Patch 编排（packages/bundle + boot/app-boot/profile.ts）**：把若干 `cordis.patch.yml` 拼成一份 entry list，喂给 Loader。

关键文件树（截取）：

```
~/deepseek-harness/
├── vendor/cordis/src/                # 核心容器（context/fiber/registry/events/reflect/service/utils）
├── packages/                         # 73 个应用包，1:1 镜像到 LCA
│   ├── core/                         # 核心服务（agent / agent-loop / scope / session / system-prompt / tools / agent-default-model）
│   ├── llm/                          # LLM 服务 + 适配器（deepseek / pi-ai / retry / token-meter）
│   ├── sandbox/                      # 沙箱 + 策略
│   ├── tools/                        # 工具族
│   ├── hooks/                        # Claude Code / Codex hook 桥接
│   ├── extensions/                   # 动态 Cordis 插件（cordis-host-runner / cordis-client-runner / tool-cordis / ui-cordis）
│   ├── bundle/                       # base / headless / web-app 三个 bundle
│   ├── boot/                         # app-boot / cmdline（启动装配）
│   ├── cli/                          # CLI 启动 profile
│   └── ...
├── apps/                             # 入口二进制（cli / web）
├── vendor/{cordis,cosmokit,schemastery}/
└── python/sdk/                       # Python 镜像 SDK（与 LCA 无关）
```

---

## 2. 核心抽象

### 2.1 `Context` —— 插件的根容器

**定位**：`vendor/cordis/src/context.ts`

**核心设计**：`Context` 是一个 Proxy，所有 `ctx.foo` 读取都会穿过 `ReflectService.handler`；内置 4 个核心 service（`events`/`logger`/`reflect`/`registry`），外加一个 root fiber。

```ts
// vendor/cordis/src/context.ts:67-87
export class Context {
  // ...
  constructor() {
    this[symbols.isolate] = Object.create(null)
    this[symbols.intercept] = Object.create(null)
    const self = new Proxy<this>(this, ReflectService.handler)
    this.root = self
    this.baseUrl = undefined
    this.fiber = new Fiber(self, {}, Object.create(null), null, () => [])
    this.reflect = new ReflectService(self)
    this.registry = new RegistryService(self)
    this.events = new EventsService(self)
    this.logger = new LoggerService(self)
    // ...
    return self
  }
```

三个关键派生工具：

- `ctx.extend(meta)` —— 创建子上下文，浅继承（不污染父）
- `ctx.isolate(name, label?)` —— 给某个服务名创建独立作用域（"provider 与其消费者绑在同一 realm"）
- `ctx.intercept(name, config)` —— 在子上下文里覆盖某 service 的 per-plugin config

```ts
// vendor/cordis/src/context.ts:115-142
isolate(name: string, label?: symbol) {
  const shadow = Object.create(this[symbols.isolate])
  shadow[name] = label ?? Symbol(name)
  return this.extend({ [symbols.isolate]: shadow })
}
intercept<K extends InjectKey>(name: K, config: ...): this
intercept(name: string, config: any) {
  const intercept = Object.create(this[symbols.intercept])
  intercept[name] = config
  return this.extend({ [symbols.intercept]: intercept })
}
```

### 2.2 `Plugin` —— 插件入口形状

**定位**：`vendor/cordis/src/registry.ts:99-145`

```ts
// vendor/cordis/src/registry.ts:99-145
export type Plugin<T = any> =
  | Plugin.Function<T>
  | Plugin.Constructor<T>
  | Plugin.Object<T>

export namespace Plugin {
  export interface Base<T = any> {
    name?: string                           // 调试名
    Config?: StandardSchemaV1<any, T>       // Schemastery schema
    inject?: Inject                         // 服务依赖声明
    provide?: string | string[]             // 本插件提供的服务名
    intercept?: Dict<boolean>
  }
  export interface Function<T = any> extends Base<T> {
    (ctx: Context, config: T): any
  }
  export interface Constructor<T = any> extends Base<T> {
    new (ctx: Context, config: T): any
  }
  export interface Object<T = any> extends Base<T> {
    apply(ctx: Context, config: T): any
  }
}
```

注入依赖通过 `@Inject()` 装饰器或静态 `inject` 字段表达：

```ts
// vendor/cordis/src/registry.ts:30-67
export function Inject<K extends InjectKey>(name: K, config?: ...) {
  return function (value: any, decorator: ...) {
    if (decorator.kind === 'class') {
      // 把 name 写进 static inject[name]
      value.inject[name] = config
    } else if (decorator.kind === 'method') {
      // 方法级延迟注入
      const inject = (value[symbols.metadata] ??= {}).inject ??= Object.create(null)
      inject[name] = config
      decorator.addInitializer(function () {
        const property = this[symbols.tracker]?.property
        ;(this[symbols.initHooks] ??= []).push(() => {
          (this.ctx as Context).inject(inject, (ctx) => {
            return value.call(property ? withProps(this, { [property]: ctx }) : this)
          })
        })
      })
    }
  }
}
```

### 2.3 `RegistryService` —— 插件注册中心

**定位**：`vendor/cordis/src/registry.ts:195-326`

负责：归一化插件形状、维护 `Plugin.Runtime`（callback → fibers 列表）、创建 `Fiber`。

```ts
// vendor/cordis/src/registry.ts:307-326
plugin(plugin: Plugin, config?: any, getOuterStack = buildOuterStack()) {
  const callback = this.resolve(plugin)
  if (!callback) throw new Error('invalid plugin...')
  this.ctx.fiber.assertActive()

  let runtime = this._internal.get(callback)
  if (!runtime) {
    let name = plugin.name
    if (name === 'apply') name = undefined
    runtime = { name, callback, fibers: new DisposableList(), Config: plugin.Config }
    this._internal.set(callback, runtime)
  }

  const fiber = new Fiber(this.ctx, config, Inject.resolve(plugin.inject), runtime, getOuterStack)
  // 返回 PromiseLike<Fiber> —— 启动失败可被 await 抛出
  return wrappedFiber
}
```

### 2.4 `Fiber` —— 插件运行时实例

**定位**：`vendor/cordis/src/fiber.ts:182-330`

每个 `ctx.plugin()` 调用产生一个 Fiber；Fiber 跟踪依赖、运行生命周期 effects、收集 disposers。状态机：

```ts
// vendor/cordis/src/fiber.ts:145-155
export const enum FiberState {
  PENDING,    // 等待依赖服务
  LOADING,    // 启动中
  ACTIVE,     // 提供服务中
  FAILED,     // 启动抛错
  DISPOSED,   // 已卸载
  UNLOADING,  // 卸载中
}
```

关键 effect 注册：

```ts
// vendor/cordis/src/fiber.ts:417-549  摘录
effect(execute: () => Effect, label = 'anonymous'): any {
  // 1. 同步执行 execute() 收集 disposer
  // 2. 卸载时反向执行（reverse order）
  // 3. 双层 effect（composite）：用 generator yield 嵌套 disposer，固定顺序
}
```

每个 Fiber 在构造时把自己的 inject 配置塞进 `ctx[Context.intercept]`，从而影响所有子 plugin：

```ts
// vendor/cordis/src/fiber.ts:237-244
if (runtime) {
  this.uid = parent.registry.counter
  this.ctx = this.context = parent.extend({ fiber: this })
  const injectEntries = Object.entries(this.inject)
  if (injectEntries.length) {
    this.ctx[Context.intercept] = Object.create(parent[Context.intercept])
    for (const [name, config] of injectEntries) {
      if (isNullable(config)) continue
      this.ctx[Context.intercept][name] = config
    }
  }
}
```

### 2.5 `Service` —— 类型化服务基类

**定位**：`vendor/cordis/src/service.ts:14-65`

```ts
// vendor/cordis/src/service.ts:30-65
export abstract class Service<out T = never> {
  declare [symbols.config]: T
  public name!: string

  constructor(protected ctx: Context, name: string) {
    name ??= this.constructor['provide'] as string
    // ...
    self.ctx = ctx
    self.name = name
    // 注册到 reflect store；卸载时随 fiber 自动取消
    self.ctx.reflect.provide(name, self, this[symbols.check])
    return self
  }
}
```

具体应用：`@deepseek-ai/dsh-agent` 的 `AgentRegistry extends Service`：

```ts
// packages/core/agent/src/index.ts:258-272
export class AgentRegistry extends Service {
  // ...
  constructor(ctx: Context) {
    super(ctx, 'agents')
    ctx.inject(['typert'], (typeCtx) => { /* 注册远端查找 */ })
    ctx.accessor('agent', { get: () => undefined })
    // ...
  }
}
```

### 2.6 事件总线 —— `EventsService`

**定位**：`vendor/cordis/src/events.ts:134-318`

5 种 dispatch 模式：`emit` / `parallel` / `serial` / `bail` / `waterfall`。内置 8 个 `internal/*` 事件 + 完全类型化的 `Events` interface（每个插件包通过 `declare module '@deepseek-ai/cordis' { interface Events { ... } }` 扩展）。

```ts
// vendor/cordis/src/events.ts:140-160
constructor(private ctx: Context) {
  defineProperty(this, symbols.tracker, { property: 'ctx', noShadow: true })
  // internal/listener + internal/update 拦截
  this.on('internal/listener', function (this: Context, name, listener, options) {
    if (name === 'internal/update' && !options.global) {
      const hooks = this.fiber._hooks['internal/update'] ??= new DisposableList()
      const method = options.prepend ? 'unshift' : 'push'
      return hooks[method](listener)
    }
  })
  this.on('internal/update', function (config, noSave, next) {
    // 触发 update 链
  }, { global: true, prepend: true })
}
```

典型事件（类型扩展）：

```ts
// vendor/cordis/src/events.ts:328-352
export interface Events {
  'internal/plugin'(fiber: Fiber): void
  'internal/status'(fiber: Fiber, oldValue: FiberState): void
  'internal/config'(this: Fiber, config: any, next: () => any): any
  'internal/service'(this: Context, name: string, value: any): void
  'internal/update'(this: Fiber, config: any, noSave: boolean, next: () => void | Promise<void>): void | Promise<void>
  'internal/get'(ctx: Context, name: string, error: Error, next: () => any): any
  'internal/set'(ctx: Context, name: string, value: any, error: Error, next: () => boolean): boolean
  'internal/listener'(this: Context, name: string, listener: any, prepend: boolean): void
  'internal/dispatch'(mode: DispatchMode, name: string, args: any[], thisArg: any): void
}
```

应用包用声明合并扩展事件类型，例如 `@deepseek-ai/dsh-agent`：

```ts
// packages/core/agent/src/runtime-types.ts:148-203
declare module '@deepseek-ai/cordis' {
  interface Events {
    'agent/created'(this: Scoped<Agent>, payload: { agent: Agent }): void     // emit
    'agent/disposed'(this: Scoped<Agent>, payload: { agent: Agent }): void   // emit
    'agent/status'(this: Scoped<Agent>, payload: { agent: Agent; status: AgentStatus }): void
    'agent/inbox/inserted'(this: Scoped<Agent>, payload: { agent: Agent; message: UserMessage }): void
    'agent/pre-step'(this: Scoped<Agent>, payload: { agent: Agent; messages: UserMessage[]; ... }, next: () => Promise<PreStepDecision>): Promise<PreStepDecision>  // waterfall
    // ...
  }
}
```

### 2.7 `Scope` —— 跨层隔离原语

**定位**：`packages/core/scope/src/index.ts:140-160`

`createScope(ctx, key, options?)` —— 在 cordis fiber 上挂一个 `dsh.scope` Symbol，作为 routing-only event carrier 的身份键。

```ts
// packages/core/scope/src/index.ts:139-148
export function createScope(ctx: Context, key: ScopeKey, options?: CreateScopeOptions): Scope {
  if (options?.parent !== undefined) bindScopeParent(key, options.parent)
  const fiber = ctx.plugin(scope)
  const scoped: Context = fiber.ctx.extend({ [kScope]: key })
  // ...
}
```

```ts
// packages/core/scope/src/index.ts:171-200
export function scopeTarget<T extends object>(base: T, key: ScopeKey | undefined): Scoped<T> {
  const baseFilter = (base as { [Context.filter]?: ... })[Context.filter]
  const carrier = {
    [Context.filter](ctx: Context): boolean {
      if (baseFilter !== undefined && !baseFilter.call(base, ctx)) return false
      const tag = scopeOf(ctx)
      if (tag === undefined) return true
      for (let cursor = key; cursor !== undefined; cursor = scopeParents.get(cursor)) {
        if (cursor === tag) return true
      }
      return false
    },
  }
  // ...
}
```

Scope 是 DSH agent 隔离的核心机制 —— Agent 的 inbox / tools / prompt sections 都是 scope-scoped 注册。

---

## 3. 注册与加载流程

### 3.1 从 YAML 到运行

完整链路：

```
CLI (dsh) 
  → profile-boot.ts:composeProfile()
  → composeEntries() 把 N 个 bundle + 用户 patch 拼成 entry list
  → boot()  (packages/boot/app-boot/src/index.ts:759)
       ├─ ctx.plugin(Loader)          // 安装 loader 服务
       ├─ mountRootInclude(ctx, configPath, patches)
       │     └─ ctx.loader.create({ id:'include', name:'cordis:include', config: { path, patches }})
       └─ ctx.get('loader').await() + assertEntriesActivated()
```

### 3.2 配置 schema / patch 格式

**定位**：`packages/bundle/base/cordis.patch.yml`

```yaml
# packages/bundle/base/cordis.patch.yml:18-58  节选
- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'

    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      config:
        root: ['.']

    - id: llm
      name: '@deepseek-ai/dsh-llm'

    - id: agent
      name: '@deepseek-ai/dsh-agent'

    - id: agent-default-model
      name: '@deepseek-ai/dsh-agent-default-model'
      config:
        provider: deepseek-official
        model: deepseek-v4-flash

    # User-settings document ($DSH_HOME/settings.yaml, hot-reloaded):
    - id: settings
      name: '@deepseek-ai/dsh-settings-file'
```

`!!js` 是 include 提供的 YAML 表达式节点：

```yaml
# packages/bundle/base/cordis.patch.yml:169-186
- id: sandbox-policy
  name: '@deepseek-ai/dsh-sandbox-policy'
  config:
    mode: !!js process.env.DSH_PERMISSION_MODE ?? 'workspace-write'
    workspaceRoot: !!js process.cwd()
```

### 3.3 Profile + Bundle 解析

**定位**：`packages/boot/app-boot/src/profile.ts`

Profile 是一个目录（`$DSH_HOME/profiles/<name>`），里面有 `package.json`（声明 `dsh.profile.bundles`）+ `cordis.patch.yml`（用户层）。每个 bundle 包是 npm 包，`package.json` 的 `dsh.bundle.patch` 字段指向 bundle 自己的 `cordis.patch.yml`。

```ts
// packages/boot/app-boot/src/profile.ts:115-122
export const PROFILE_TEMPLATES: Record<string, readonly string[]> = {
  web: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'],
  headless: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'],
}
```

`composeEntries()` 是单一调用，与 `boot()` 完全一致：

```ts
// packages/boot/app-boot/src/profile.ts:412-420
export function composeEntries(
  layers: readonly PatchOptions[][], warn: ...,
): EntryOptions[] {
  return applyEntryPatches([], structuredClone(layers.flat()), (message, ...args) => {
    warn(message.replace(/%C/g, () => JSON.stringify(args[index++])))
  })
}
```

### 3.4 `boot()` —— 真正落地

**定位**：`packages/boot/app-boot/src/index.ts:759-808`

```ts
// packages/boot/app-boot/src/index.ts:759-810
export async function boot(
  binName: string,
  absoluteConfigPath: string,
  patches?: PatchOptions[],
  prepare?: (ctx: Context) => Promise<void> | void,
  bareModuleBaseUrl?: string,
): Promise<Context> {
  const ctx = new Context()
  let stage = 'host preparation failed'
  try {
    ctx.baseUrl = pathToFileURL(dirname(absoluteConfigPath)).href + '/'
    ctx.provide('dshHomePath', dshHomePath)
    await ctx.plugin(Loader)                              // 安装 Loader 服务
    await prepare?.(ctx)                                  // 可选 host 准备
    stage = 'plugin tree failed to load'
    await mountRootInclude(ctx, absoluteConfigPath, patches, bareModuleBaseUrl)
    await ctx.get('loader')?.await()                     // 等所有条目 settle
    if (ctx.get('loader') === undefined) return ctx
    await assertEntriesActivated(ctx, binName)            // 状态断言
    return ctx
  } catch (cause) {
    await ctx.fiber.dispose()
    // ...
  }
}
```

`assertEntriesActivated`（仅启用 + 非 PENDING + 非 FAILED）：

```ts
// packages/boot/app-boot/src/index.ts:689-720
export async function assertEntriesActivated(ctx, binName): Promise<void> {
  assertEntriesLoaded(ctx, binName)
  const failures: string[] = []
  const rejectionReasons: unknown[] = []
  for (const entry of ctx.loader.entries()) {
    const fiber = entry.fiber
    if (fiber === undefined || entry.disabled) continue
    const state = fiber.state
    if (state === FIBER_ACTIVE) continue
    if (state === FIBER_FAILED) {
      try { await fiber.await() } catch (error) { rejectionReasons.push(error); failures.push(...) }
      continue
    }
    if (state === FIBER_PENDING) {
      const missing = Object.keys(fiber.inject).filter(service => fiber.ctx.get(service) === undefined)
      failures.push(`${entry.options.name}: pending (waiting for: ${missing.join(', ')})`)
    }
  }
  if (failures.length > 0) throw new Error(`${binName}: ${failures.length} entries did not activate\n${failures.join('\n')}`)
}
```

### 3.5 `appBoot.mountRootInclude()` —— 实际挂载 root include

```ts
// packages/boot/app-boot/src/index.ts:485-529
export async function mountRootInclude(ctx, absoluteConfigPath, patches, bareModuleBaseUrl): Promise<Entry | undefined> {
  ctx.loader.builtins.include = bareModuleBaseUrl === undefined ? Include : class HostResolvedRootInclude extends Include { ... }
  ctx.loader.builtins.group = Group
  const includeConfig: Include.Config = {
    path: pathToFileURL(absoluteConfigPath).href,
    ...patches.length > 0 ? { patches: [...patches] } : {},
  }
  const rootInclude: EntryOptions = { id: 'include', name: 'cordis:include', config: includeConfig }
  const includeId = await ctx.loader.create(rootInclude)
  const loader = ctx.get('loader')
  if (loader === undefined) return undefined
  const entry = loader.resolve(includeId)
  bootstrapIncludes.set(ctx, entry)
  return entry
}
```

### 3.6 实际 CLI 入口

**定位**：`apps/cli/src/bin.ts` + `apps/cli/src/profile-boot.ts`

```ts
// apps/cli/src/bin.ts:29-49
switch (invocation.mode) {
  case 'profile': {
    const { runProfile } = await import('./profile-boot.ts')
    await runProfile({
      environment: loadLayeredEnv('dsh'),
      profile: invocation.profile,
      patchFiles: invocation.patches,
      args: invocation.args,
    })
    break
  }
  // ...
}
```

`runProfile` 把 patch 栈堆成 `allPatches`，然后：

```ts
// apps/cli/src/profile-boot.ts  摘录
function composeProfile(name, patchFiles) {
  const profile = prepareProfile(name)
  const homePatches = loadOptionalPatches(NAME, homePatchPath()) ?? []
  const overlays = patchFiles.flatMap(file => loadOverlayPatches(NAME, resolve(file)))
  const bundlePatches = profile.layers.flatMap(layer => layer.patches)
  const rows = new Map<string, EntryOptions>()
  for (const row of composeEntries([bundlePatches, profile.patches, homePatches, overlays])) {
    if (typeof row.id === 'string') rows.set(row.id, row)
  }
  // ...
}
```

---

## 4. 插件交互模式

### 4.1 依赖注入

#### (a) 硬依赖（`inject` 静态字段）

插件声明自己需要的 service，**Loader 会等所有 inject 都 ACTIVE 后才激活**：

```ts
// packages/core/agent-loop/src/index.ts:299-301
export class AgentLoop extends Service implements AgentFactory {
  static inject = ['agents', 'sessions', 'llm', 'tools', 'systemPrompt']
  static Config = z.object({...})
```

#### (b) 软依赖（`ctx.get()`）

运行时按需读取，没有 inject 时不阻止启动：

```ts
// packages/llm/llm-deepseek/src/index.ts:228-243
const credentials = ctx.get('credentials')
if (credentials !== undefined) {
  const hit = await credentials.resolve(ref)
  if (hit !== undefined) return assertUsableApiKey(hit.value, 'llm-deepseek', ref)
} else {
  // Without the seam there is no managed store to rank against, so the
  // environment is the whole credential plane.
  const ambient = launchEnvironmentOf(ctx).get(ref)
  if (ambient !== undefined && ambient.value.length > 0) return assertUsableApiKey(ambient.value, 'llm-deepseek', ref)
}
```

#### (c) Service-base 注入（按 fiber 调用上下文）

```ts
// packages/core/agent/src/index.ts:269-271 摘录
ctx.inject(['typert'], (typeCtx) => {
  typeCtx.typert.lookups.register('agent', { ... })
  typeCtx.typert.contexts.registerHost('agent', { ... })
})
```

### 4.2 事件 / 钩子

应用包通过 `declare module '@deepseek-ai/cordis' { interface Events { ... } }` 扩展事件类型，再用 `ctx.on()` / `ctx.parallel()` / `ctx.waterfall()` 注册监听器。

典型 waterfall（agent/pre-step，Hook 桥接）：

```ts
// packages/hooks/hooks-claude-code/src/index.ts:200-260
ctx.on('agent/pre-step', async ({ agent, messages, turn, signal }, next): Promise<PreStepDecision> => {
  // ... 调用 hooks, 合并输出
  const merged = await runPoint('UserPromptSubmit', '', payload, { agent, turn, signal })
  if (merged.stop) return { kind: 'reject' }
  // ... 把 merged.additionalContext 塞进 messages
  return next()  // waterfall 默认值
})

ctx.on('tools/pre-execute', async (exec, next): Promise<PreToolDecision> => {
  // ... 决策 allow/block/ask
})
```

### 4.3 扩展点（Extension Points）

DSH 没有用 `ExtensionPoint<T>` 这种类型化槽，而是靠 **service 注册 + 配置 schema 注入** 表达扩展点。13 个核心 seam 在 `packages/llm/`、`packages/tools/`、`packages/sandbox/` 等"服务定义包"中以 `extends Service` 形式声明；具体实现包（如 `llm-deepseek`、`bash-sandbox`）通过 `ctx.<service>.registerAdapter(...)` / `ctx.tools.register(...)` 等方法提供。

#### (a) LLM 适配器

```ts
// packages/llm/llm/src/index.ts:281-365 摘录
export class LlmRuntime extends Service {
  private adapters = new Map<string, AdapterRegistration>()
  // ...

  registerAdapter(providers: string[], adapter: LlmAdapter): AdapterRegistrationHandle {
    // ... 全部 entry 装入 owned / this.adapters；emit 'llm/adapters-updated'
  }
}
```

适配器实现：

```ts
// packages/llm/llm-deepseek/src/adapter.ts:54-78
export class DeepSeekAdapter implements LlmAdapter {
  // stream(options: GenerateOptions): AsyncIterable<StreamChunk>  ← 唯一必需
  // providerInfo / listModels / resolveModel
}
```

plugin 端注册：

```ts
// packages/llm/llm-deepseek/src/index.ts:271-281
ctx.llm.registerConfigurableProviders([
  { provider: PROVIDER, displayName: 'DeepSeek', settingsNs: NS, settingsPath: [] },
])
const registration = ctx.llm.registerAdapter([PROVIDER], adapter)
```

#### (b) 工具注册

```ts
// packages/core/tools/src/index.ts:787-868 摘录
export class ToolRuntime extends Service {
  static inject = ['systemPrompt']
  static Config: z<Config> = z.object({
    mode: z.union(['native', 'code', 'both'] as const).default('native'),
    maxParallelSubCalls: z.natural().min(1).default(10),
  })
  // ...
}
```

每个 tool 包调 `ctx.tools.register(defineTool({ name, description, parameters, output, execute }))`。Tool 通过 cordis hooks 扩展管线：

```ts
// packages/core/tools/src/index.ts:142-200
declare module '@deepseek-ai/cordis' {
  interface Events {
    'tools/pre-execute'(this: Scoped<ToolRuntime>, exec: ToolExecution, next: () => Promise<PreToolDecision>): Promise<PreToolDecision>  // waterfall: allow/deny/ask
    'tools/execute'(this: Scoped<ToolRuntime>, exec: ToolDispatchExecution, next: () => Promise<ToolExecutionResult>): Promise<ToolExecutionResult>  // waterfall: timeout/retry/metrics
    'tools/post-execute'(this: Scoped<ToolRuntime>, exec: ToolExecution, result: ..., next: () => Promise<PostToolDecision>): Promise<PostToolDecision>  // waterfall: accept/replace/enrich/block
    'tools/code-dispatch-log'(this: Scoped<ToolRuntime>, dispatch: CodeDispatchLog, next: () => Promise<ContentBlock[]>): Promise<ContentBlock[]>  // waterfall: durable 改写
    'tools/result'(this: Scoped<ToolRuntime>, exec: Readonly<ToolExecution>, result: Readonly<ToolExecutionResult>): undefined  // emit
    'tools/change'(): void  // emit: registry 变化
  }
}
```

#### (c) 沙箱策略

```ts
// packages/sandbox/sandbox-policy/src/index.ts:89-145
export class SandboxPolicyService extends Service {
  static Config: z<Config> = z.object({
    mode: z.union(['read-only', 'workspace-write', 'danger-full-access'] as const).default('read-only'),
    workspaceRoot: z.string(),
  })
  // resolve({ session, mode? }) → SandboxExecutionPolicy
}
```

#### (d) 动态 Cordis 插件（in-runtime plugin 定义 + VM 沙箱）

**定位**：`packages/extensions/cordis-host-runner/src/`

完整插件系统之上的"动态插件"机制 —— 运行时通过 `cordis_define` 工具新增/升级/移除包：

```ts
// packages/extensions/cordis-host-runner/src/registry.ts:39-72
export interface DynamicCordisDefinition {
  packageId: CordisDynamicPackageId
  name: string
  purpose: string
  hostCode?: string       // Host 端源码
  clientCode?: string     // Client 端源码
}

export interface DynamicCordisPlugin {
  pluginId: CordisDynamicPluginId
  sessionId: SessionId
  packages: Map<CordisDynamicPackageId, DynamicCordisDefinition>
  approvedClientPackages: Set<CordisDynamicPackageId>
  clientVersionUpdatesApproved: boolean
  currentPackageId?: CordisDynamicPackageId
  nextPackageId?: CordisDynamicPackageId
  run?: DynamicCordisRun
}
```

Host 端代码在 `node:vm` 沙箱里 eval，沙箱中只有白名单：

```ts
// packages/extensions/cordis-host-runner/src/sandbox.ts:19-45 摘录
export const HOST_BUILTIN_INSPECTION = [
  { name: 'ctx', description: 'Restricted Cordis Context...', signatures: [...] },
  { name: 'harness', description: 'Host helpers for Package-private Client RPC...', signatures: [...] },
  { name: 'console', description: 'Package-tagged Host logging...', signatures: [...] },
  { name: 'btoa', ... }, { name: 'atob', ... }, { name: 'TextEncoder', ... }, { name: 'TextDecoder', ... },
] as const
```

`require`、`setTimeout` 等被截到错误信息，告诉用户改用 `ctx.fs` / `ctx.web` / `ctx.bash` / cordis timer service。

模型面对的工具：`cordis_define` / `cordis_run` / `cordis_stop` / `cordis_undefine` / `cordis_inspect_list` / `cordis_inspect_query` / `cordis_inspect_self`：

```ts
// packages/extensions/tool-cordis/src/index.ts:30-50 摘录
export const name = 'tool-cordis'
export const inject = ['tools', 'systemPrompt', 'dynamicCordisRunner', 'cordisInspect']

export function apply(ctx: Context): void {
  ctx.systemPrompt.section({ name: 'tool:cordis', order: 115, text: CORDIS_SYSTEM_PROMPT })
  for (const provider of hostInspectProviders(ctx)) {
    ctx.effect(() => ctx.cordisInspect.register(provider), ...)
  }
  ctx.tools.register(defineTool({ name: 'cordis_inspect_list', ..., execute() { return { providers: ctx.cordisInspect.list() } } }))
  ctx.tools.register(defineTool({ name: 'cordis_inspect_query', ... }))
  ctx.tools.register(defineTool({ name: 'cordis_inspect_self', ... }))
  ctx.tools.register(defineTool({ name: 'cordis_define', ... }))
  // ...
}
```

### 4.4 钩子桥接（hooks-*）

Claude Code / Codex 的 `hooks.json` 通过两个桥接插件接入 cordis 事件总线：

```ts
// packages/hooks/hooks-claude-code/src/index.ts:39-46
export const name = 'hooks-claude-code'
export const inject = ['shell']   // 'bash' is required to run hooks

export const Config: z<Config> = z.object({
  configPath: z.string().required(),
  pluginRoot: z.string(),
  projectDir: z.string(),
  defaultTimeoutMs: z.number().default(DEFAULT_HOOK_TIMEOUT_MS),
  stderrSummaryMaxChars: z.number().default(DEFAULT_STDERR_SUMMARY_MAX_CHARS),
})
```

执行模型：每个 hook 点通过 `ctx.on('agent/pre-step', ..., next) / ctx.on('tools/pre-execute', ...) / ctx.on('agent/session-start', ...)` 接出，由 `runHook()` 调到 shell，**用 ctx.shell 的 credential scrub + 超时 + 进程组取消**。

### 4.5 配置 / 设置（hot reload）

`@deepseek-ai/dsh-settings-file` 监听 `$DSH_HOME/settings.yaml`，通过 `internal/update` waterfall 把新配置塞进对应 plugin：

```ts
// packages/llm/llm-deepseek/src/index.ts:281-286
installSettingsSection(ctx, NS, Config, config, {
  setSource: (source) => { current = source },
  onChange: ensureRegistrationFacts,
})
```

---

## 5. 主流程如何使用插件

### 5.1 Agent 生命周期

**核心包**：`@deepseek-ai/dsh-agent` + `@deepseek-ai/dsh-agent-loop`

`dsh-agent` 提供：
- `Agent` interface
- `AgentRegistry`（`ctx.agents`）—— live agent 索引 + AsyncLocalStorage initiator
- `AgentFactory` 协议
- `agentEvents()` —— 带 scope carrier 的事件分发

```ts
// packages/core/agent/src/index.ts:255-290
export class AgentRegistry extends Service {
  private store = new Map<SessionId, AgentEntry>()
  private factory: FactorySlot | undefined
  private readonly initiators = new AsyncLocalStorage<Agent | undefined>()
  // ...

  constructor(ctx: Context) {
    super(ctx, 'agents')
    ctx.inject(['typert'], (typeCtx) => { /* ... */ })
    ctx.accessor('agent', { get: () => undefined })
    ctx.on('internal/status', (fiber) => {
      if (fiber.state === FiberState.UNLOADING && this.hasLifecycleAncestor(fiber)) {
        this.closeInitiators()
      }
    })
  }

  setFactory(factory: AgentFactory): () => void {
    // 唯一 register factory 的入口
  }

  async create(options: CreateAgentOptions): Promise<AgentHandle> {
    // 通过 factory.createAgent(ownerCtx, options)
  }
}
```

`dsh-agent-loop` 注册 AgentFactory 实现（`AgentLoop` 类）：

```ts
// packages/core/agent-loop/src/index.ts:299-303
export class AgentLoop extends Service implements AgentFactory {
  static inject = ['agents', 'sessions', 'llm', 'tools', 'systemPrompt']
  static Config = z.object({ ... }) as z<Config>
  // ...
  constructor(ctx, config) {
    super(ctx, 'agentLoop')
    // ...
    ctx.effect(() => ctx.agents.setFactory(this), 'agentLoop.setFactory()')
    ctx.systemPrompt.variable('provider', context => context.agent?.options.provider)
    ctx.systemPrompt.variable('model', context => context.agent?.options.model)
    ctx.systemPrompt.variable('cwd', context => context.agent?.session.header.cwd)
    // 声明式 agent 启动
    for (const { id, sessionId, cwd, resumeSessionId, ...options } of this.config.agents) {
      // ... create / resume 启动
    }
  }
}
```

### 5.2 主循环（ReactLoopAgent）

**定位**：`packages/core/agent-loop/src/agent.ts`

```ts
// packages/core/agent-loop/src/agent.ts:70-90 摘录
export class ReactLoopAgent implements Agent {
  readonly inbox: Inbox
  private phase: Phase  // { idle | maintenance | running }
  private activityDone: Promise<void> = Promise.resolve()
  readonly scope: Scope
  readonly ctx: Context
  private readonly dispatch: AgentEventDispatch
  private requestHeaderLogged = false
  private readonly runtimeContext: RuntimeContextProjection

  constructor(private loopCtx, public readonly id, public readonly options, public readonly session) {
    this.dispatch = agentEvents(loopCtx, this)
    this.inbox = new Inbox(session, {
      inserted: (m) => this.dispatch.emit('agent/inbox/inserted', { message: m }),
      discarded: (m) => this.dispatch.emit('agent/inbox/discarded', { message: m }),
      claimed: (m, turn) => this.dispatch.emit('agent/inbox/claimed', { message: m, turn }),
    })
    const lastTurn = session.events.findLast(event => event.type === 'turn/start')?.data.turn ?? 0
    this.phase = { kind: 'idle', lastTurn }
    this.scope = createScope(loopCtx, this)
    this.ctx = this.scope.ctx.extend({ agent: this })
    // ...
  }
```

主循环伪代码（`kick()` → `turn()` → `step()` → `executeToolCalls()`）：

```text
wakeDriver():
    if phase.kind != 'idle': latch or abort; return
    phase = running (abort, turn, step=0)
    loopCtx.agents.withInitiator(this, () => this.kick())

kick():
    while await this.turn(): pass
    // finally: emit idle, replay wakeRequested

turn():
    phase.turn += 1
    session.append('turn/start', { turn })
    target = 'next-turn'
    while true:
        decision = await preStep(target, { turn, step: phase.step+1 })
        if decision.kind == 'reject': return false (turn blocked)
        session.append('step/start', { turn, step })
        for msg in decision.messages: session.append('user/message', msg)
        stepEnd = await step(decision.assembly)
        session.append('step/end', { turn, step })
        if turnEnds && inbox.nextStep empty: break
        target = 'next-step'
    if inbox.hasPending: return true (next turn)
    return false

preStep(target, position):
    claimed = inbox.claim(target, position.turn)
    assembly = await loopCtx.systemPrompt.assemble(assembleContextFor(this, signal))
    decision = await dispatch.waterfall('agent/pre-step',
        { messages: claimed, ...position, signal },
        () => ({ kind: 'enter', messages: [...claimed, context] }))
    return { ...decision, assembly }

step(assembly):
    request = buildRequest(turn, step, tools, system, session.deriveMessages(), signal)
    stream = preparedCall?.stream(request) ?? loopCtx.llm.stream(request)
    chunks → assembler → finish
    if finish.kind in {error, aborted}: dispatch.waterfall('agent/request-error', ...) → retry or throw
    session.append('assistant/message', { turn, step, message, usage })
    toolCalls = message.content.filter(b => b.type === 'tool-call')
    if toolCalls.length == 0: return { kind: 'completed' }
    { concluded } = await executeToolCalls(loopCtx, turn, step, toolCalls, signal, acceptContext)
    return concluded ? { kind: 'completed' } : null

executeToolCalls(ctx, turn, step, toolCalls, signal, acceptContext):
    agent = ctx.agents.requireInitiator()
    while next < planned.length:
        first = planned[next]
        mode = ctx.tools.executionMode(first.exec).kind  // 'parallel' | 'exclusive'
        group = mode == 'parallel' ? planned.slice(next) : [first]
        outcome = await runGroup(ctx, turn, step, group, mode, signal, acceptContext)
        next += outcome.consumed
        if outcome.aborted:
            for each unstarted: appendSkippedToolCall(session)
            return { concluded }
    return { concluded }

runGroup(...):
    // parallel 模式：bounded rolling pool；exclusive 模式：单调用 barrier
    // 关键 hooks：
    //   ctx.tools[TOOL_RUNTIME_SCHEDULER].prepare(exec)   ← pre-execute + guards
    //   ctx.tools[TOOL_RUNTIME_SCHEDULER].dispatch(exec)   ← tools/execute waterfall + body
    //   ctx.tools[TOOL_RUNTIME_SCHEDULER].finalize(exec,result)   ← post-execute
    //   ctx.tools[TOOL_RUNTIME_SCHEDULER].finish(exec,result)     ← finalize without post
```

源码摘录：

```ts
// packages/core/agent-loop/src/agent.ts:228-243
private async preStep(target: InboxTarget, position: { turn: number; step: number }): Promise<PreparedStep> {
  const signal = this.phase.abort.signal
  const claimed = this.inbox.claim(target, position.turn)
  const assembly = await this.loopCtx.systemPrompt.assemble(assembleContextFor(this, signal))
  signal.throwIfAborted()
  const sections = renderContextSections(assembly)
  const context = this.runtimeContext.project(joinContextSections(sections), sections)
  const decision = await this.dispatch.waterfall(
    'agent/pre-step', { messages: claimed, ...position, signal },
    (): Promise<PreStepDecision> => Promise.resolve<PreStepDecision>({
      kind: 'enter',
      messages: context === undefined ? claimed : [...claimed, context],
    }),
  )
  // ...
  return decision.kind === 'reject' ? decision : { ...decision, assembly }
}
```

```ts
// packages/core/agent-loop/src/agent.ts:336-405  摘录
private async step(assembly: PromptAssembly): Promise<StepEndReason | null> {
  // ...
  while (true) {
    const { request, preparedCall } = await this.buildRequest(turn, step, ...)
    const assembler = new BlockAssembler()
    const stream = preparedCall?.stream(request) ?? this.loopCtx.llm.stream(request)
    for await (const chunk of stream) {
      chunkSeqs.push(this.session.append('assistant/chunk', { turn, step, chunk }).seq)
      assembler.push(chunk)
    }
    const finish = assembler.finish
    if (finish.kind === 'error' || finish.kind === 'aborted') {
      const action = await this.dispatch.waterfall('agent/request-error', {...}, () => Promise.resolve<RequestErrorAction>(undefined))
      if (action?.kind !== 'retry') throw new LlmError(...)
      continue
    }
    // ... session.append('assistant/message'), 调度 tool calls
    const { concluded } = await executeToolCalls(this.loopCtx, turn, step, toolCalls, signal, ...)
    return concluded ? { kind: 'completed' } : null
  }
}
```

### 5.3 工具调用调度器

**定位**：`packages/core/agent-loop/src/tool-calls.ts`

```ts
// packages/core/agent-loop/src/tool-calls.ts:59-100  摘录
export async function executeToolCalls(ctx, turn, step, toolCalls, signal, acceptContext) {
  const agent = ctx.agents.requireInitiator()
  const { session } = agent
  const planned = toolCalls.map(block => ({ block, exec: { callId, name, arguments, agent, signal } }))
  let next = 0
  let concluded = false
  while (next < planned.length) {
    const first = planned[next]
    const mode = ctx.tools.executionMode(first.exec).kind  // parallel / exclusive
    const group = mode === 'parallel' ? planned.slice(next) : [first]
    const outcome = await runGroup(ctx, turn, step, group, mode, signal, acceptContext)
    next += outcome.consumed
    concluded ||= outcome.concluded
    if (outcome.aborted) {
      for (const call of planned.slice(next)) appendSkippedToolCall(session, ...)
      return { concluded }
    }
  }
  return { concluded }
}
```

```ts
// packages/core/agent-loop/src/tool-calls.ts:163-200  摘录
const startCall = async (index: number): Promise<void> => {
  const call = group[index]
  callSeqs[index] = appendToolCall(session, turn, step, call.block)
  started++
  const prepared = await ctx.tools[TOOL_RUNTIME_SCHEDULER].prepare(call.exec)  // pre-execute + guards
  throwSchedulerFailure()
  switch (prepared.kind) {
    case 'dispatch': {
      const promise = ctx.tools[TOOL_RUNTIME_SCHEDULER].dispatch(prepared.exec).then(...)
      inFlight.set(index, promise)
      break
    }
    case 'post-result': slots[index] = { exec, result, needsPost: true }; break
    case 'final-result': slots[index] = { exec, result, needsPost: false }; break
    // ...
  }
}
```

### 5.4 工具管线（pre/guard/around/post/result）

**定位**：`packages/core/tools/src/index.ts`

```ts
// packages/core/tools/src/index.ts:787-868  摘录
export class ToolRuntime extends Service {
  static inject = ['systemPrompt']
  static Config: z<Config> = z.object({
    mode: z.union(['native', 'code', 'both'] as const).default('native'),
    maxParallelSubCalls: z.natural().min(1).default(10),
  })

  readonly [TOOL_RUNTIME_SCHEDULER]: ToolRuntimeScheduler = {
    prepare: exec => this.prepareScheduledExecution(exec),
    dispatch: exec => this.dispatchScheduledExecution(exec),
    finalize: (exec, result) => this.finalizeScheduledExecution(exec, result),
    finish: (exec, result) => this.finishScheduledExecution(exec, result),
  }

  private readonly layers = new ScopedLayers(
    scope => new ToolLayer(scope),
    () => { this.ctx.emit('tools/change') },
  )
  // ...
}
```

Scope-aware 注册层（Agent scope / preset scope / global）：

```ts
// packages/core/tools/src/index.ts:712-765  摘录
return this.tools.isEmpty() && this.restrictions.isEmpty() && this.guards.isEmpty()
// ↑ 一个 ToolLayer 持有的三张表：tools / restrictions / guards

guard(guard: ToolGuard): () => void {
  // 注册一个 monotonic guard；返回 exact disposer
  return this.ctx.effect(() => /* register into layers */, { label: 'tools.guard()', notify: false })
}
```

Tool 定义：

```ts
// packages/core/tools/src/index.ts:222-289 摘录
export interface ToolDefinition extends ToolSchema {
  readonly output: ToolOutputDefinition  // 强制声明 schema + 渲染函数
  execute(args, exec): Promise<unknown>
  finalizeContent?(exec, result): ContentBlock[] | undefined
  timeoutMs?: number
  isConcurrencySafe?(args): boolean
  presentCall?(args): ToolCallView | undefined
  presentResult?(args, result): ToolResultView | undefined
}
```

### 5.5 LLM 适配器选择

主循环调用 `loopCtx.llm.stream(request)`：

```ts
// packages/llm/llm/src/index.ts:281-365  摘录
export class LlmRuntime extends Service {
  // ...
  registerAdapter(providers: string[], adapter: LlmAdapter): AdapterRegistrationHandle { /* ... */ }
}

// packages/core/agent-loop/src/agent.ts:344 摘录
const stream = preparedCall?.stream(request) ?? this.loopCtx.llm.stream(request)
```

`llm/stream` 是 waterfall，可被 retry / 重放 / 路由拦截：

```ts
// packages/llm/llm/src/index.ts:52-68 摘录
declare module '@deepseek-ai/cordis' {
  interface Context { llm: LlmRuntime }
  interface Events {
    /** Waterfall around every streaming model call (retry, replay, routing). */
    'llm/stream'(this: LlmRuntime, options: GenerateOptions, next: () => AsyncIterable<StreamChunk>): AsyncIterable<StreamChunk>
  }
}
```

DSH 没有"主流程挑 driver"的概念 —— Agent 主循环的入口固定是 `ReactLoopAgent.step()`，它消费的就是 cordis 树中所有相关服务（llm / tools / systemPrompt / session / agents）的当前实现。换 provider / 换 tool 实现 = 换 entry 的 `id` 即可（base bundle 的 `llm-pi-ai` 就是 dormant 双胞胎）。

---

## 6. 与 LCA `lca/packages/` 的对应关系表

LCA 通过 `scripts/check_port_surface.py` 校验 deepseek-harness `packages/` ↔ `lca/packages/` 的 public surface 1:1 镜像（目录名 hyphen ↔ underscore；`src/*.ts` ↔ `src/*.py`；当前 LCA 端是 auto-generated surface skeleton，运行时抛 `NotImplementedError`）。

按 deepseek-harness 子目录映射：

| deepseek-harness (`~/deepseek-harness/packages/`) | LCA (`/home/lichao/layered-cognitive-agent/lca/packages/`) | 角色 |
|---|---|---|
| `core/agent/` | `core/agent/` | Agent 接口 + AgentRegistry service |
| `core/agent-loop/` | `core/agent_loop/` | ReactLoopAgent + AgentLoop factory |
| `core/agent-default-model/` | `core/agent_default_model/` | 默认 provider/model |
| `core/agent-tool-presentation/` | `core/agent_tool_presentation/` | 工具呈现中间件 |
| `core/scope/` | `core/scope/` | Scope 隔离原语 |
| `core/session/` | `core/session/` | Session 事件流 + 投影 |
| `core/system-prompt/` | `core/system_prompt/` | SystemPrompt 服务 |
| `core/tools/` | `core/tools/` | ToolRuntime + 工具 schema |
| `llm/llm/` | `llm/llm/` | LlmRuntime + Adapter 抽象 |
| `llm/llm-deepseek/` | `llm/llm_deepseek/` | DeepSeek adapter |
| `llm/llm-pi-ai/` | `llm/llm_pi_ai/` | 多 provider 适配器 |
| `llm/llm-retry/` | `llm/llm_retry/` | Retry policy |
| `llm/token-meter/` | `llm/token_meter/` | 用量计量 |
| `sandbox/sandbox/` | `sandbox/sandbox/` | 沙箱接口 |
| `sandbox/sandbox-local/` | `sandbox/sandbox_local/` | 本地沙箱实现 |
| `sandbox/sandbox-policy/` | `sandbox/sandbox_policy/` | 沙箱策略 |
| `sandbox/sandbox-windows-acl/` | `sandbox/sandbox_windows_acl/` | Windows ACL 后端 |
| `e2b/e2b/` | `e2b/e2b/` | E2B 接口 |
| `e2b/fs-e2b/` | `e2b/fs_e2b/` | E2B 文件系统 |
| `e2b/subprocess-e2b/` | `e2b/subprocess_e2b/` | E2B 子进程 |
| `mcp/mcp-client/` | `mcp/mcp_client/` | MCP 客户端 |
| `lsp/lsp/` | `lsp/lsp/` | LSP 接口 |
| `lsp/lsp-stdio/` | `lsp/lsp_stdio/` | LSP stdio 后端 |
| `lsp/tool-lsp/` | `lsp/tool_lsp/` | LSP 工具 |
| `shell/` | `shell/` | shell 执行 |
| `subprocess/` | `subprocess/` | 子进程 |
| `terminal/` | `terminal/` | 终端 |
| `code-runtime/` | `code-runtime/` | CodeRuntime 接口 |
| `code-runtime/code-runtime-worker-thread/` | `code-runtime/code_runtime_worker_thread/` | Worker Thread 后端 |
| `compaction/` | `compaction/` | 压缩接口 |
| `compaction/compaction-basic/` | `compaction/compaction_basic/` | 基础压缩 |
| `compaction/compaction-tool-result-pruner/` | `compaction/compaction_tool_result_pruner/` | tool result 修剪 |
| `compaction/command-compact/` | `compaction/command_compact/` | `/compact` 命令 |
| `fs/fs/` | `fs/fs/` | FS 接口 |
| `fs/fs-local/` | `fs/fs_local/` | 本地 FS |
| `fs/fs-observation-policy/` | `fs/fs_observation_policy/` | FS 观察策略 |
| `fs/fs-sandbox/` | `fs/fs_sandbox/` | 沙箱 FS |
| `fs/tool-fs/` | `fs/tool_fs/` | FS 工具 |
| `fs/tool-fs-search/` | `fs/tool_fs_search/` | FS 搜索工具 |
| `fs/tool-str-replace-editor/` | `fs/tool_str_replace_editor/` | 编辑器工具 |
| `goal/goal/` | `goal/goal/` | Goal 服务 |
| `goal/goal-round-driver/` | `goal/goal_round_driver/` | Goal 回合驱动 |
| `goal/tool-goal/` | `goal/tool_goal/` | Goal 工具 |
| `goal/command-goal/` | `goal/command_goal/` | Goal 命令 |
| `todo/tool-todo/` | `todo/tool_todo/` | Todo 工具 |
| `workflow/` | `workflow/` | 工作流 |
| `subagent/` | `subagent/` | 子 agent |
| `jobs/jobs/` | `jobs/jobs/` | Job 接口 |
| `jobs/jobs-local/` | `jobs/jobs_local/` | 本地 Job |
| `jobs/tool-jobs/` | `jobs/tool_jobs/` | Job 工具 |
| `schedule/` | `schedule/` | 调度 |
| `session-query/session-query/` | `session-query/session_query/` | Session 查询 |
| `session-query/session-query-sqlite/` | `session-query/session_query_sqlite/` | SQLite 后端 |
| `session-query/session-log-export/` | `session-query/session_log_export/` | 日志导出 |
| `session-query/tool-session-query/` | `session-query/tool_session_query/` | Session 查询工具 |
| `skill/skill/` | `skill/skill/` | Skill 接口 |
| `skill/skill-badge/` | `skill/skill_badge/` | Skill badge |
| `skill/skill-filesystem/` | `skill/skill_filesystem/` | 文件系统 Skill |
| `skill/tool-skill/` | `skill/tool_skill/` | Skill 工具 |
| `spill/` | `spill/` | 溢出处理 |
| `storage/` | `storage/` | 存储 |
| `interaction/commands/` | `interaction/commands/` | 命令 |
| `interaction/permission-presets/` | `interaction/permission_presets/` | 权限预设 |
| `interaction/tool-ask-user/` | `interaction/tool_ask_user/` | 询问用户工具 |
| `interaction/user-approval/` | `interaction/user_approval/` | 用户审批 |
| `interaction/user-questions/` | `interaction/user_questions/` | 用户问题 |
| `feedback/command-feedback/` | `feedback/command_feedback/` | 反馈命令 |
| `feedback/message-feedback/` | `feedback/message_feedback/` | 消息反馈 |
| `compaction/compaction-tool-result-pruner/` | `compaction/compaction_tool_result_pruner/` | 工具结果修剪（亦出现于 compaction） |
| `context/agent-instructions/` | `context/agent_instructions/` | Agent 指令上下文 |
| `context/session-reference/` | `context/session_reference/` | Session 引用 |
| `context/time-context/` | `context/time_context/` | 时间上下文 |
| `context/tmux-context/` | `context/tmux_context/` | tmux 上下文 |
| `extensions/cordis-host-runner/` | `extensions/cordis_host_runner/` | 动态 Cordis host |
| `extensions/cordis-client-runner/` | `extensions/cordis_client_runner/` | 动态 Cordis client |
| `extensions/tool-cordis/` | `extensions/tool_cordis/` | 模型面对的动态插件工具 |
| `extensions/ui-cordis/` | `extensions/ui_cordis/` | 动态插件 UI |
| `host/apiproxy/` | `host/apiproxy/` | Host API 代理 |
| `host/directory-picker/` | `host/directory_picker/` | 目录选择器接口 |
| `host/directory-picker-auto/` | `host/directory_picker_auto/` | 自动目录选择 |
| `host/directory-picker-browse/` | `host/directory_picker_browse/` | 浏览目录选择 |
| `host/directory-picker-native/` | `host/directory_picker_native/` | 原生目录选择 |
| `host/frontend-static/` | `host/frontend_static/` | 静态前端 |
| `host/plugin-inventory/` | `host/plugin_inventory/` | 插件清单 |
| `host/webserver/` | `host/webserver/` | Web 服务器 |
| `api/gateway/` | `api/gateway/` | API 网关 |
| `api/remotes/` | `api/remotes/` | 远端 |
| `sdk/client/` | `sdk/client/` | SDK 客户端 |
| `sdk/protocol/` | `sdk/protocol/` | SDK 协议 |
| `sdk/server/` | `sdk/server/` | SDK 服务端 |
| `acp/acp/` | `acp/acp/` | ACP 桥接 |
| `plan/plan-mode/` | `plan/plan_mode/` | Plan 模式 |
| `preset/agent-presets/` | `preset/agent_presets/` | Agent 预设 |
| `preset/persona/` | `preset/persona/` | Persona |
| `settings/settings/` | `settings/settings/` | 设置接口 |
| `settings/settings-file/` | `settings/settings_file/` | 文件设置 |
| `credentials/credentials/` | `credentials/credentials/` | 凭证接口 |
| `credentials/credentials-local/` | `credentials/credentials_local/` | 本地凭证 |
| `identity/anonymous-user-id/` | `identity/anonymous_user_id/` | 匿名用户 ID |
| `attachment/attachment/` | `attachment/attachment/` | 附件接口 |
| `attachment/attachment-local/` | `attachment/attachment_local/` | 本地附件 |
| `runtime-diagnostics/invariants/` | `runtime-diagnostics/invariants/` | 不变式 |
| `test-support/` | `test-support/` | 测试支持 |
| `typert/` | `typert/` | 类型桥 |
| `util/` | `util/` | 工具 |
| `web/` | `web/` | Web |
| `workspace/` | `workspace/` | 工作区 |
| `hooks/hook-protocol/` | `hooks/hook_protocol/` | Hook 协议 |
| `hooks/hooks-claude-code/` | `hooks/hooks_claude_code/` | CC 桥 |
| `hooks/hooks-codex/` | `hooks/hooks_codex/` | Codex 桥 |
| `guard/repeat-tool-reminder/` | `guard/repeat_tool_reminder/` | 重复工具提醒 |
| `guard/timeout-policy/` | `guard/timeout_policy/` | 超时策略 |
| `boot/app-boot/` | `boot/app_boot/` | 启动装配 |
| `boot/cmdline/` | `boot/cmdline/` | 命令行 |
| `bundle/base/` | `bundle/base/` | base bundle |
| `bundle/headless/` | `bundle/headless/` | headless bundle |
| `bundle/web-app/` | `bundle/web_app/` | web-app bundle |
| `examples/agent-spine-demo/` | `examples/agent_spine_demo/` | Agent 骨架 demo |
| `examples/acp-demo/` | `examples/acp_demo/` | ACP demo |
| `examples/jsonrpc-demo/` | `examples/jsonrpc_demo/` | JSON-RPC demo |
| `client/**`（多个 ui-* / runtime / connection / locale / web / web-react / hmr / modules / schema_form / runtime / ui_tool 等） | `client/**`（ui_* / runtime / connection / locale / web / web_react / hmr / modules / schema_form / ui_tool 等） | 客户端 UI 模块（与 web 资产对应） |

**LCA 不存在的子包**：

- `examples/`：DSH 有 `acp-demo` / `jsonrpc-demo` / `agent-spine-demo`；LCA 已在 `lca/packages/examples/` 下建立同名目录（见 LCA `lca/packages/examples/`）。
- `dist-exe/`、`native/landlock-run/`、`python/sdk-runtime/`：DSH 专用二进制分发。

**对应规则的强约束**：

```python
# scripts/check_port_surface.py:328-348
def _ts_to_py_relpath(ts_rel: str) -> str:
    parts = ts_rel.split("/")
    if len(parts) < 4: return ts_rel
    top, sub, src_dir, *rest = parts
    sub_py = sub.replace("-", "_")  # hyphen → underscore
    if not rest: return ts_rel
    last = rest[-1]
    stem, _ext = last.rsplit(".", 1) if "." in last else (last, "")
    if len(rest) > 1:
        nested = "/".join(rest[:-1])
        new_rel = f"{top}/{sub_py}/{src_dir}/{nested}/{stem}.py"
    else:
        new_rel = f"{top}/{sub_py}/{src_dir}/{stem}.py"
    return new_rel
```

即 `packages/<top>/<sub>/src/<file>.ts` ↔ `lca/packages/<top>/<sub_py>/src/<file>.py`（嵌套 src/ 子目录保留），跳过的目录：`node_modules / lib / dist / .git / __pycache__ / tests / fixtures`（`.d.ts` 也跳过）。

LCA 端当前以 auto-generated surface skeleton 形式存在，每个文件首注释明确标注：

```python
# lca/packages/core/agent_loop/src/agent.py:1-20 摘录
"""Auto-generated surface skeleton for upstream ``core/agent-loop/src/agent.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``core/agent-loop/src/agent.ts``
"""
__all__: list[str] = [
    "ReactLoopAgent",
]
```

```python
# lca/packages/hooks/hook_protocol/src/index.py:5-23
"""Auto-generated surface skeleton for upstream ``hooks/hook-protocol/src/index.ts``.
...
"""
__all__: list[str] = [
    "DEFAULT_HOOK_TIMEOUT_MS", "DEFAULT_STDERR_SUMMARY_MAX_CHARS",
    "CommandHook", "DetachedRuns", "HookDialect", "HookInvocation",
    "HookOutput", "HookResultRecord", "MatcherGroup", "MatcherMode",
    "MergedDecision", "MergedHookOutcome", "RunHookOptions", "RunHookResult",
    "appendHookInvoked", "appendHookResult", "createDetachedRuns",
    "matcherDiagnostic", "matchesMatcher", "mergeHookOutputs",
    "parseHookOutput", "runHook", "summarizeStderr",
]
```

这种对应关系意味着 LCA 的最终目标是：把 cordis vendored 到 Python（LCA 已通过 `vendor/cordis/` 拿到 Python 移植 `taiyi-cordis`，并在 `pyproject.toml` 通过 `[tool.uv.sources]` 加载），再把这些 surface stub 替换为真正运行起来的 Python 实现，最终在 LCA 自己的 cognition/runtime/agent 层之上复用同一棵插件树。

---

## 附录：DSH 关键 vendored 库

| 库 | 路径 | 作用 |
|---|---|---|
| `cordis` | `vendor/cordis/src/` | 依赖注入 / 插件运行时（Context + Service + Fiber + EventBus） |
| `cosmokit` | `vendor/cosmokit/src/` | 通用工具（Dict / Awaitable / defineProperty 等） |
| `schemastery` | `vendor/schemastery/src/` | Standard-schema v1 验证（DSH 全用 `z<Config>` 风格 schema） |
| `cordis-plugin-loader` | `vendor/loader/` | YAML entry list → 插件树加载器 |
| `cordis-plugin-include` | `vendor/include/` | 嵌套 include + `!!js` 表达式 + patch 合并 |
| `cordis-plugin-group` | `vendor/group/` | 给一组 row 一个 `isolate` realm |
| `cordis-plugin-timer` | `vendor/timer/` | cordis-aware `ctx.timeout` / `ctx.interval` |
| `cordis-plugin-hmr` | `vendor/hmr/` | 文件 watcher + `update` 链触发 |

LCA 已经把这些 vendored 库复制为自己的 Python 包（见 LCA `vendor/cordis/`、`vendor/cosmokit/`、`vendor/schemastery/`），并通过 `pyproject.toml` 的 `[tool.uv.sources]` 把它们接到 `taiyi-cordis` / `taiyi-cosmokit` / `taiyi-schemastery` 这套 Python 别名上。这就是为什么 LCA 能用 Python cordis API + 1:1 Python 镜像 `packages/`。