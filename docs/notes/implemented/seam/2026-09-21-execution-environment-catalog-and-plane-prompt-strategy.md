# Agent Note: 执行环境目录与平面提示词策略

Status: implemented

## Problem

agent 只能感知当前绑定的执行平面。沙箱 run 里系统提示注入 `lobe-cloud-sandbox`，agent 不知道自己可以操作哪些已配对的电脑。绑定设备时提示词切换到 `lobe-local-system`，但 agent 没有途径列出全部可用设备。用户要求同时看到云端沙箱与所有配对成功的电脑（可能多台），并预留 SSH 等远程执行环境。

执行平面提示词装配同时存在坏味道。`sandbox_prompt.py` 位于认知层却处理 Machine 逻辑。`surface.py` 的 `_sandbox_note` 硬编码沙箱说明，`plane_system_role` 对 Machine 走模板、对 Sandbox 走字符串分支。同一概念在多个文件里有不同渲染路径，违背单一通道原则。

## Decision

引入统一的执行环境领域模型与目录，并把提示词装配重构为策略模式。代码已落地。

**领域模型**。`EnvironmentKind` 是封闭枚举（`sandbox` / `machine` / `ssh`）。`ExecutionEnvironment` 是不可变值对象，字段包含 kind、id、label、platform、online、is_current、root、outputs_dir、home、workspace、capabilities、metadata。它是模型可见环境事实的投影，由 `PlaneRef` 和设备注册表派生，不是第二事实源。`environment_from_plane()` 提供投影转换。

**端口**。`EnvironmentProvider` 是环境来源端口，`EnvironmentCatalog` 是目录读模型端口（`list_all()` / `current()`），`DeviceProvider` 是设备注册表的最小面。

**目录实现**。`CompositeEnvironmentCatalog` 聚合 providers、按 `(kind, id)` 去重、标记当前环境。`SandboxEnvironmentProvider` 投影当前沙箱。`DeviceEnvironmentProvider` 把每台配对设备映射为机器环境。`DeviceMachineResolver` 增加 `list_devices()` 实现 `DeviceProvider`。`build_environment_catalog()` 从 run 的平面绑定、沙箱、机器解析器组装目录。

**提示词策略**。`PlanePromptStrategy` 是渲染契约（kind + tool_name + `render(plane)`）。`SandboxPlaneStrategy` 渲染 `cloud_sandbox_system_role` 模板。`MachinePlaneStrategy` 渲染 `machine_system_role` 模板，注入 `{{preinstalled}}` 与 home 说明。`render_plane_prompt()` 是统一组装入口，`render_plane_role()` 提供无 `<tool>` 包装的内嵌渲染。`default_machine_ref()` 作为默认值对象，提示词渲染不再有 Python 字符串 fallback。

**环境感知工具**。`lca-environment-awareness` 工具提供 `listEnvironments` API，读取环境目录返回 `{current, environments}`。它在 `build_default_tools` 中无条件注入，沙箱 run 与机器 run 都能查询全部可用环境。

**配置化**。未来 SSH 等环境通过 `ConfigEnvironmentProvider` 从 YAML 声明加载，不改代码。环境声明格式为 `{kind, id, label, platform, host, root, online}`。

## Alternatives considered

### Why not 只做设备感知工具，不动提示词装配？

设备工具能满足"列出电脑"，但提示词装配的多处硬编码和认知层职责泄露仍然存在。未来加 SSH 时还要在多个文件里加分支。工具与提示词共享同一领域模型才符合 SSOT。

### Why not 只做提示词注入，不做环境目录工具？

Codex 与 DeepSeek-Harness 都不提供模型可查的环境目录，环境事实通过提示词与 schema 投影注入。但用户要求 agent 能列出多台配对设备并感知在线状态。LobeHub `RemoteDeviceManifest` 的 `listOnlineDevices` 是同类先例。双通道同时满足两者。

### Why not 把全部设备列表注入系统提示？

设备增多后上下文膨胀，且每次提示词构建都要查询注册表。提示词只注入当前平面，设备列表通过工具按需查询，符合最小化原则。

### Why not 做全局 PlanePromptRegistry 微内核注册表？

可插拔性最强但过度设计。当前稳定平面只有沙箱与机器，策略字典加开闭原则已经足够，注册表只会增加间接层与认知负担。

## Consequences

沙箱 run 里 agent 可以调用 `listEnvironments` 感知到 lipcmain 等配对设备及其在线状态。绑定设备时系统提示仍注入当前机器平面。新增执行环境类型只需实现一个 `EnvironmentProvider`、一个 `PlanePromptStrategy`、一个模板，不需要改动目录、工具或组装器。

## Verification

`tests/contracts/models/environment/test_execution_environment.py`：值对象冻结、`to_dict` 稳定、`environment_from_plane` 正确投影。

`tests/infrastructure/environment/test_environment_catalog.py`：providers 映射、目录去重、当前环境标记、工厂装配。

`tests/infrastructure/runtime_plane/test_plane_prompt.py`：无绑定渲染沙箱，绑定机器渲染本地系统角色，包含 preinstalled 与 home。

`tests/infrastructure/tools/test_environment_awareness.py`：`listEnvironments` 返回当前环境与列表，空目录安全。

`tests/scenario/computer/test_computer_tools.py`：`build_default_tools` 包含 `listEnvironments`。

## Testing

`pytest tests/contracts/models/environment test tests/infrastructure/environment tests/infrastructure/runtime_plane/test_plane_prompt.py tests/infrastructure/tools/test_environment_awareness.py tests/scenario/plane/test_plane_bindings.py tests/cognition/test_prompt_surface.py tests/cognition/test_cloud_sandbox_cjk_policy.py tests/lca/cognition/brain/test_reasoner_cloud_branch_renders_uploaded_files.py tests/scenario/computer/test_computer_tools.py` 共 53 个测试通过。`lint-imports` 与 `check_package_contracts.py` 门禁见对应 PR 验证。