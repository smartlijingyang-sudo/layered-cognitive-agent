# Agent Note: create-assistant 对话创建流 —— 角色模板、工具执行面、前端投影与 run 绑定接缝

Status: implemented

> 配套 ADR：[ADR-0187](../../../adr/0187-assistant-agent.md) §3 D11/D12（PR-7 对话创建）。
> 本 Note 钉「对话创建助理」这条链路的 seam 边界：谁拥有真值、谁做投影、
> run 绑定从哪个字段进、人设从哪个通道进 prompt。Home 布局与三类真值分层的
> 边界见 [assistant-home-scope](./2026-09-04-assistant-home-scope.md)。

## Problem

ADR-0187 D12 要求「与现有 agent 对话『创建一个助理』自动走设置」，但 PR-3…PR-5
落地后链路上有四个缺口：创建只能写 `assistant.default` 一种模板；
`POST /v1/assistants` 是 501 stub 且路由未进任何 bundle；创建的助理在前端
不可见（LobeHub agents 行与 LCA Home 之间无桥）；`POST /runs` 不解析
`assistant_id`，助理人设进不了对话。

## Decision

### 角色模板 = 数据扩展，不动 Protocol

`_home_layout.TEMPLATE_REGISTRY` 登记 6 个 `template_id`（`assistant.default`
+ research / writing / coding / translation / daily），`templates/` 下每个角色
一个与 `assistant_default/` 同构的目录（profile.json 带 emoji、SOUL 角色人设、
goals 具体目标）。`catalog.create` 仅接受注册表内 id（未知 ⇒ 400，不回落
default）。`CreateAssistantRequest` 形状不变。

### 执行面 = `create_assistant` 工具（G7 窄门）

对话创建不走 shell / HTTP 脚本，走进程内工具：`lca.plugins.assistant.tools`
注册 `assistant` 工具工厂 → `AssistantCreateTool`（require `assistant.catalog`，
soft `assistant.frontend_bridge`）。理由：执行面 plane（sandbox / machine）的
网络与仓库可达性不确定；工具经 Body/审批闸受治理，副作用声明在 Plugin
manifest。`skills/create-assistant/SKILL.md` 只做对话引导（`askUserQuestion`
选项卡收敛输入），禁止 skill 指导绕开工具写盘。

### BOOTSTRAP 完成流

`seed_user_md` 非空 = 引导式创建：写 USER.md 后删除 BOOTSTRAP.md 并发
`assistant.bootstrap.completed` EP（EP 在 PR-2 已登记的 12 项闭集内）。
BOOTSTRAP.md 不在配置面 digest 清单，删除不触发 `revision_seq`。
无 `seed_user_md` 的裸创建保留 BOOTSTRAP.md（原语义）。

### 前端投影 = TRPC agents 行，映射真值在 `agencyConfig.lcaAssistantId`

`assistant.frontend_bridge` capability（`webserver_bridge` 插件，effects=NETWORK）
调 LobeHub `POST /trpc/lambda/agent.createAgent`（superjson body
`{"json":{"config":{...}}}`），config 携带 `title/description/avatar/model:"solo"`
+ `agencyConfig.lcaAssistantId = asst_xxx`。映射真值 = LobeHub agents 行本身，
不落第二份映射文件。注册失败 fail-soft（返回 None，不阻断创建）。
同一插件把 `assistant.catalog` 装进 `app.state.assistant_catalog` 供
`/v1/assistants` 路由（web-standard 无此插件 ⇒ 501 兜底不变）。

### run 绑定链（前端聊天 = legacy `/runs` 路径）

```
LcaRunDriver.ts planeFieldsFromAgent 读 agencyConfig.lcaAssistantId
  → POST /runs body assistant_id
  → decode_create_run 解析（非字符串 ⇒ 400）+ create_run fail-closed 校验
    （无 catalog ⇒ 400；未知 ⇒ 404；digest 不匹配 ⇒ 409，D7 不静默回落）
  → RunRequest → create_run_session → RunSession.assistant_id
  → RunAmbit.assistant_id（ADR-0122 环境量唯一载体）
  → Spine source / actor_role = assistant_id（I-A2 载体）+ structlog 上下文
```

### 人设注入 = RoleProfile 覆盖（既有 prompt 通道）

`CognitiveRunDriver` solo 装配时 `current_run_ambit().assistant_id` 非空 ⇒
`persona.persona_from_home(spec.home_path)` 收敛 `(role, goal, backstory)`
（SOUL + IDENTITY + USER 拼接，backstory 上限 3000 字符）覆盖默认角色。
不加 prompt section、不改模板、不动闭集；无绑定 ⇒ 逐字原路径（I-A1）。

## Alternatives considered

### Why not skill 指导 run_command 调 `POST /v1/assistants`？

执行面 plane 可能是沙箱容器，到宿主 `:8765/:3010` 的网络与仓库脚本可达性
都不保证；进程内工具不依赖执行面环境，且副作用经 G7 闸受治理。代价是工具
装配进 profile 才可用——这正是 opt-in 语义本身。

### Why not 在内核维护 `agt_* ↔ asst_*` 映射文件？

把 LobeHub 的 `agt_*` 命名空间引入内核是反向依赖；映射写进 LobeHub agents
行（`agencyConfig`）后，前端读取与聊天绑定都用同一份真值，内核只见自己的
`asst_*`。代价是前端行被删则绑定丢失——可接受，重新创建即恢复。

### Why not 新增 prompt section 渲染助理人设？

17-section 闭集与模板是核心面，改它需要 ADR 且影响所有 run；RoleProfile
三元组本就是模板首三行，覆盖它零闭集改动。代价是人设不走 ContextManifest
投影——PR-4 bootstrap 插件保留独立可用，后续需要时再接。

### Why not 什么都不做（只给 REST）？

D12 的产品意图是对话内完成创建；只有 REST 等于把设置流程推回给操作者手敲
JSON，违背「减少输入复杂度」的原始需求。

## Consequences

- 部署启用助理 = `lca-ops.yaml` `kernel_serve.profile: profiles/web-assistant.yaml`
  （`heal`/`kernel-restart` 读取；换回 `web-standard` 即关闭）。
- `/v1/assistants` create/list/get 为真实装；revise/install/retire/jobs 仍按
  各自 PR 的 501/503 兜底（PR-6 install 已接线，属并行工作）。
- workspace cwd 绑定（I-A5 运行期）、session spine 路径的 assistant 消费、
  evolve/jobs 不在本流内（PR-8 与后续任务）。
- 测试面：`tests/plugins/assistant/test_templates.py` / `test_create_tool.py` /
  `test_webserver_bridge.py` / `test_persona.py` / `test_run_binding.py` /
  `test_tools_plugin.py` + routes catalog-present 用例。

## Related

- [ADR-0187](../../../adr/0187-assistant-agent.md) —— AssistantAgent 产品面
- [assistant-home-scope](./2026-09-04-assistant-home-scope.md) —— Home seam 边界与三类真值分层
- `lca/plugins/assistant/{catalog,_home_layout,persona,tools,webserver_bridge}.py`
- `skills/create-assistant/SKILL.md` —— 对话引导协议
- `deploy/lobehub/patches/runtime/LcaRunDriver.ts` —— `planeFieldsFromAgent` 绑定
