# ADR-0294：沙箱路径单点映射机制（SandboxPaths）

> **Status: Proposed**（2026-10-08 起草；源于李超 14:40/14:55 两问立案的 todo-81 第一性原理设计——沙箱环境路径统一、agent 只感知自己的目录、skill 不写死路径；验收标准来自李超 15:00「环境可换性」问。待李超拍板后实施）

## 1. Context（差距）

guest 可见 `/mnt/data` ↔ host 实际目录的映射**不是 SSOT**，今天散在 5 处，每处自带常量与假设——这正是 todo-79（改了 rewrite 目标没改 staging）与 RA-040（逆向投影另起一套机制）两起事故的共同根因：

| # | 调用点 | 方向 | 机制 |
|---|---|---|---|
| 1 | `LocalSandboxAdapter._rewrite_command` | inbound（guest→host） | 裸 `command.replace(mount, root)` 字符串替换 |
| 2 | `_project_host_to_guest`（RA-040） | outbound（host→guest） | stdout/stderr 逆向投影，正则 boundary-aware |
| 3 | `SandboxRuntime._stage_files` | 写侧 | staging 落点（修法 (b) 后：session root） |
| 4 | guest preamble `LCA_GUEST_ROOT` / `BG_DIR` | guest 脚本视角 | guest 可见 ROOT |
| 5 | `activate_skill` prompt 文本 | skill 面 | 告诉 model `/mnt/data/<name>` |

`/mnt/data` 字面量散落各处，session-work 目录多处各自计算。"改映射要同时改 N 处"目前靠人肉保证，零机制约束。更深层的问题：**inbound 与 outbound 不对称**——正向重写是朴素 `str.replace`（非 boundary-aware），逆向投影是正则（boundary-aware）；命令含兄弟前缀路径（如 `/mnt/data2/x`）会被重写为 `<work>2/x` 而投影不掩回，host 路径泄漏（iter-quality 14:09 轮附带观察）。

李超 14:55 纠正：不要补丁思维，要第一性原理的一套稳定机制。

## 2. 公理（机制从这三条推出，不再拼凑）

1. **Agent 恰好有一个文件系统命名空间：自己的目录。** 它不命名、不看见、不推理 host 路径。
2. **Skill 只对 agent 命名空间写作。** Skill 里出现字面 host/infra 路径是 defect。
3. **Host 布局（session 目录、平面、挂载）是运行时私有的**，可自由变更；除映射缝隙外任何地方不得引用。

## 3. 机制：单个 `SandboxPaths`

每 session 构建一次，唯一构造点：

- `resolve(agent_path) -> host_path` —— 执行侧：命令重写、文件写、staging、harvest 扫描
- `present(host_path) -> agent_path` —— 观测侧：stdout/stderr 投影、tool 结果、文件列表
- **所有边界穿越走它**；factory 编码平面策略（Local→虚拟化，Onlyboxes→恒等）；调用点不再做平面判断、不再自带常量

不变量（测试钉死，非期望）：

- **round-trip**：`present(resolve(p)) == p`（杀死 inbound/outbound 不对称边角）
- **containment**：`resolve(p)` 永不逃出 session host root，否则报错（fail-closed）
- **totality**：不可解析的 agent 路径显式报错，不静默透传

二阶：裸 `str.replace(mount, root)` 换 path-token 感知重写（子串碰撞：`/mnt/data` 作为更长名字的子串、或出现在非路径上下文）。

## 4. Skill 不写死路径

- Skill 只用相对路径（相对 agent root 解析）或声明式模板变量（如 `{agent_root}`、`{attachments_dir}`），运行时加载时填充
- 执行：lint/test 扫 skill 正文与 prompt 模板，硬编码绝对路径字面量（`/mnt/data`、`/tmp/`、`/home/`…）进 CI 失败；allowlist 仅命名空间定义本身

## 5. 稳定性的来源

agent 可见命名空间是**版本化契约**（如 "agent path contract v1"：固定名、固定布局 `<root>/`、`<root>/outputs/`…）。host 侧可任意重排而不触契约；改 agent 可见命名空间 = breaking change = 走迁移。变化方向被约束——这才是"稳定机制"与"补丁"的区别。

## 6. 命名决策（记录，不代决）

agent 可见根沿用 `/mnt/data` 作虚拟名（ADR-0046、`activate_skill`、RA-040 投影已是既成契约，改名是纯迁移成本、零功能收益）；语义重定义为"每 session 私有的 agent 命名空间"，不再是共享挂载。若李超要连字面 `/mnt/data` 都从 agent 世界拿掉，另立迁移项。

## 7. 迁移（零行为变化）

1. (b) 修复落地（todo-79 修法 (b)，staging 传 session id）→
2. 引入 `SandboxPaths` 并逐个调用点 rewiring（每步全绿）→
3. skill 审计 + 模板变量化 + lint 进 CI →
4. 契约文档化（短 ADR 或契约节）

lane 归属：lca/** 归 quality lane，tests/** 归 tests lane。

## 8. 验收标准（环境可换性，李超 15:00 问）

新增执行环境只需两件事：

1. 实现 SandboxBackend 执行原语（spawn/stream/kill 等）
2. 写一个 `SandboxPaths` factory（guest 可见根→该环境的 host root）

agent 可见契约、skills、prompts、rewrite/projection/staging 逻辑**零改动**。mapper 内部 guest 侧恒为 POSIX 语义、host 侧按 OS 处理（pathlib 对象，不做字符串替换）——这是换到异构 host（如 Windows）时不翻车的关键。

今天做不到的原因：5 处散落代码各自 baked in 了"当前环境长什么样"，换环境 = 人肉猎杀 N 处假设。

## 9. 与已有工作的关系

- todo-79 修法 (b)（`_stage_files` 落 session root）：本机制的步骤 1，先行条件
- RA-040（逆向投影）+ `8094cc234`（emit 内投影）：本机制 `present()` 侧的现有实现，将被收编
- `b6608bb58`（contract-absolute guest 输入映射到有效根）：本机制 `resolve()` 侧的现有实现，将被收编
- iter-quality 14:09 附带观察（正向裸 replace vs 逆向 boundary-aware 不对称）：本机制 round-trip 不变量消除

## 10. 诚实边界

- P2（无行为变化，纯结构）；不改 guest 可见契约（agent 视角仍是 `/mnt/data`）
- 本 ADR 仅为提案：设计来自李超指令的 backlog todo-81，实施细节与命名归属待李超拍板
