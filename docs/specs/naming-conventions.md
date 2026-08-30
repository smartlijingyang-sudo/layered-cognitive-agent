# Layered 架构命名规范

## 目标

Layered 的命名应优先表达**架构职责、边界和生命周期**，而不是实现方式或历史来源。公共名称需要让读者能够从名称判断对象属于契约、适配、编排还是领域模型，并避免同一语义在不同层使用多个近义词。

## 核心规则

| 场景 | 规范 | 反例 | 推荐 |
|---|---|---|---|
| 数据契约 | 使用领域对象 + 语义后缀；避免 `Info`、`Data` 等无信息后缀 | `FilesInfoDocument` | `AttachmentManifest` |
| 单文件元数据 | 使用领域对象 + `Metadata` | `FilesInfoFile` | `AttachmentFileMetadata` |
| 协议实现 | 使用协议名 + `Adapter`，仅在确有适配边界时使用 | `RunDiffToolImpl` | `RunDiffToolAdapter` |
| 生命周期编排 | 使用领域对象 + `Coordinator`，表示协调多个参与者并持有流程状态 | `ActivationManager` | `SubagentActivationCoordinator` |
| 纯服务 | 使用 `Service`；不得把所有业务对象泛化为 Service | `AttachmentService` 仅当其确实提供用例编排 | 以职责判断 |
| 工厂 | 使用 `Factory`；只负责创建，不负责注册、执行或治理 | `ProviderFactoryManager` | 拆分为 `ProviderFactory` 与注册协调器 |
| 注册表 | 使用 `Registry`；只表达发现、索引和查找职责 | `PluginManager` | `PluginRegistry` |
| 运行边界 | 使用 `Run` 表示一次执行，使用 `Session` 表示可持续会话；二者不得混用 | `run_session` 随意互换 | 按生命周期语义选择 |

## 后缀语义

`Protocol` 表示可替换的契约，`Adapter` 表示跨边界转换或把具体基础设施接入契约，`Coordinator` 表示跨组件协调生命周期或流程，`Registry` 表示索引与发现，`Manifest` 表示可审计的声明性清单，`Plan` 表示经过解析或编译、可供执行的不可变计划。

## 迁移原则

重命名必须同步源码、测试、文档和导出列表，并优先通过包级导出维持清晰的公共入口。对于已经发布或被外部消费的 API，不应保留模糊别名作为长期兼容层；若确需过渡，应在迁移说明中记录退役版本和删除条件。新名称确定后，旧名称不得重新进入术语表或新代码。

## 当前规范化术语

本轮将以下名称规范化：

| 原名称 | 新名称 | 理由 |
|---|---|---|
| `FilesInfoFile` | `AttachmentFileMetadata` | 去除重复且无边界的 `FilesInfo`，明确对象属于 attachment，并说明其为元数据模型 |
| `FilesInfoDocument` | `AttachmentManifest` | `Manifest` 更准确表达由附件记录生成、用于注入和审计的声明性清单 |
| `RunDiffToolImpl` | `RunDiffToolAdapter` | `Impl` 只说明“怎么实现”，`Adapter` 明确其是基础设施到工具契约的接入层 |
| `TraceInspectorToolImpl` | `TraceInspectorToolAdapter` | 与同类只读工具保持一致的适配器命名 |
| `ActivationManager` | `SubagentActivationCoordinator` | 消除泛化的 `Manager`，明确协调对象、作用域与生命周期职责 |

> 命名规范本身不改变分层方向：`contracts → infrastructure → cognition → runtime → agent`，而 `application` 仍作为组合根存在。
