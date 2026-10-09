# ADR-0294：沙箱路径单点映射机制（SandboxPaths）

> **Status: Accepted**（2026-10-08 起草；源于李超 14:40/14:55 两问立案的 todo-81 第一性原理设计——沙箱环境路径统一、agent 只感知自己的目录、skill 不写死路径；验收标准来自李超 15:00「环境可换性」问。**李超 15:17 side chat "实施吧" 批准实施**；(b) `SandboxPaths` 合入 main（merge `7ace29bdb`，15:32），(c) per-exec mount namespace 合入 main（merge `386a438aa`，15:57），四步迁移全部完成，见 §11 实施记录）

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

1. (b) 修复落地（todo-79 修法 (b)，staging 传 session id）——✅ 2026-10-08，merge `6d8ba982e`
2. 引入 `SandboxPaths` 并逐个调用点 rewiring（每步全绿）——✅ 2026-10-08 15:32，merge `7ace29bdb`（新模块 `lca/infrastructure/sandbox/paths/sandbox_paths.py`：`resolve`/`present`、path-token 感知的 `rewrite_command`/`present_text`、`for_local()`/`identity()` factory、fail-closed 错误；5 处调用点 rewiring；32 新测试全绿）
3. skill 审计 + 模板变量化 + lint 进 CI ——✅ 2026-10-08 15:32，随 `7ace29bdb` 落地（`tests/infrastructure/sandbox/test_skill_path_hygiene.py`：lca/ 内 `/mnt/data` 字面量仅允许命名清单、skill 正文与 prompt 模板禁硬编码 host 路径，pytest 套件内常跑）
4. 契约文档化（短 ADR 或契约节）——✅ 本 ADR 即契约文档；另追加 (c) per-exec mount namespace（Pattern A）：2026-10-08 15:57，merge `386a438aa`（`mount_namespace.py`：`mount_namespace_available()` cached 探针、`mount_namespace_enabled()`（`LCA_SANDBOX_MOUNT_NS` 显式 0/1 > 自动检测）、`wrap_in_mount_namespace()` 纯字符串构造器；`SandboxPaths` 加 `mounted` 模式：mounted 时 `rewrite_command`/`present_text` 恒等（内核做映射）、`resolve`/`present` 供 host 侧；13 新测试全绿；userns 不可用自动回退 (b)）

lane 归属：lca/** 归 quality lane，tests/** 归 tests lane。

## 8. 验收标准（环境可换性，李超 15:00 问）

新增执行环境只需两件事：

1. 实现 SandboxBackend 执行原语（spawn/stream/kill 等）
2. 写一个 `SandboxPaths` factory（guest 可见根→该环境的 host root）

agent 可见契约、skills、prompts、rewrite/projection/staging 逻辑**零改动**。mapper 内部 guest 侧恒为 POSIX 语义、host 侧按 OS 处理（pathlib 对象，不做字符串替换）——这是换到异构 host（如 Windows）时不翻车的关键。

今天做不到的原因：5 处散落代码各自 baked in 了"当前环境长什么样"，换环境 = 人肉猎杀 N 处假设。

## 9. 与已有工作的关系

- todo-79 修法 (b)（`_stage_files` 落 session root）：本机制的步骤 1，先行条件
- RA-040（逆向投影）+ `8094cc234`（emit 内投影）：本机制 `present()` 侧的现有实现，已被 `present()`/`present_text()` 收编（adapter 内已无调用者，仅留 virtual 路径 legacy 契约测试）
- `b6608bb58`（contract-absolute guest 输入映射到有效根）：本机制 `resolve()` 侧的现有实现，已被 `resolve()` 收编
- iter-quality 14:09 附带观察（正向裸 replace vs 逆向 boundary-aware 不对称）：已由 round-trip 不变量消除（`tests/infrastructure/sandbox/test_sandbox_paths.py` property 测试钉死）；旧 `command.replace(mount, root)` 的兄弟前缀暗坑（`/mnt/data2/x` → `<root>2/x`）在 (b) 落地时一并修复（双边边界检查）

## 10. 诚实边界

- P2（无行为变化，纯结构）；不改 guest 可见契约（agent 视角仍是 `/mnt/data`）
- 本 ADR 已由李超 15:17 "实施吧" 批准并全部落地（§7/§11）；命名决策（`/mnt/data` 沿用，见 §6）与设计均按本 ADR 执行，未变更

## 11. 实施记录（2026-10-08，全部落地）

- **(b) `SandboxPaths` 单缝隙**（15:32，merge `7ace29bdb`）：guest 可见契约未变（ADR-0046 的 `/mnt/data` 输入 + `/mnt/data/outputs` 产出仍准）；`SandboxPaths` 三不变量（round-trip / containment / totality）由 `test_sandbox_paths.py` 的 property 测试钉死，非期望。
- **(c) per-exec mount namespace**（15:57，merge `386a438aa`，Pattern A）：`unshare -Urm` per-exec 新建 namespace、`mount --make-rprivate /` 为必需步骤（`test_mount_namespace.py` 的 mountinfo 无泄漏回归测试钉死）；无 holder、无常驻进程、无残留（3 次 exec 实测）；guest 可见语义与 (b) 完全一致，只是实现从字符串重写换成内核真实挂载；`LCA_GUEST_ROOT` 在 mounted 模式取 guest_mount（host 路径对 guest 不可见，§2 公理 1 成立）；非 Linux / userns 被禁时自动回退 (b)。
- **验证**（backlog todo-81 记录）：(b) 32 新测试 + 129 宽面绿；(c) 13 新测试 + sandbox 目录 76 绿 + `tests/infrastructure/` 1324 passed（7 failed 在 pristine main 同样红，pre-existing）；ruff（CI pin 0.16.10）净；0 push。
- **RA-050：§1 行 1/2 收编**（22:32 `81339c085`，merge `d8ace6aa1`）：`LocalSandboxAdapter._rewrite_command` / `_project_host_to_guest` 已删除（38 行）。二者生产无调用者，且以 `for_local(root)` 构造时不带 `mounted` 标志，per-exec mount namespace 下会重写内核已翻译过的命令；路径映射的唯一缝隙是 `_exec_shell` 内联构建的 `SandboxPaths`（入口 `rewrite_command`、出口 `present_text`）。边界重写覆盖 1:1 迁到 seam 侧（`test_seam_present_text_leaves_sibling_prefix_paths_alone`，三不变量仍由 `test_sandbox_paths.py` property 测试钉死），两条经 `run_terminal` 钉 adapter 出口的异步集成测试保留。§1 表行 1/2 是起草时点的差距记录，代码中已无对应符号。
