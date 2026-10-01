# 硬编码全量系统性治理架构设计方案 (Hardcoding Remediation Design)

- **日期**：2026-10-01
- **状态**：Approved
- **设计人**：LCA 架构组
- **爆炸半径等级**：`DRAFT` (AP-05，受控演进与分步测试确认)

---

## 1. 背景与问题诊断

在 2026-10-01 批次的提交与深度代码审查中，排查出 7 大类严重的硬编码（Hardcoding）与架构反模式缺陷：

1. **宿主机网络与私有资产侵入 (P0)**：
   - [`lca/plugins/assistant/templates/TOOLS.md`](lca/plugins/assistant/templates/TOOLS.md) 中直接硬编码了开发者特定宿主机的私网 IP（`10.36.6.252`）、内核网关（`8765`）、前端（`3010`）、个人智库（`1889`）和本地代理（`127.0.0.1:7890`）；
   - 6 大预设助理的 `AGENTS.md` 模板硬编码了宿主机私有智库路径 `~/everything-library` 和端口 `1889`；
   - 违背了 LCA 独立认知智能体框架的定位，触犯 [`AGENTS.md`](AGENTS.md) 范围铁律与 AP-01 负向边界。
2. **Prompt 伪造运行时与时间戳假象 (P0)**：
   - [`lca/plugins/prompts/sections/runtime_env.py`](lca/plugins/prompts/sections/runtime_env.py) 中，`RuntimeEnvSection.render()` 与 `DeveloperTimestampSection.render()` 采取无参调用；
   - 导致注入给模型的状态行中模型永远是伪造的 `"Muse Spark"`（而真实生产模型是 **Qwen** 等实际模型），操作系统永远伪造为 `"linux"`，Shell 永远伪造为 `"bash"`；
   - 时间戳永远写死东八区（`CST / UTC+8`）与客户端来源 `web`，使模型在跨平台、跨时区与非 Web 渠道中产生严重的认知偏差。
3. **用户偏好模板写死时区 (P0)**：
   - 6 大预设助理的 `USER.md` 模板写死 `Timezone / 时区：Asia/Shanghai (UTC+8)`，剥夺了用户按需配置的自由度。
4. **路径安全拦截使用魔数与字符串片段匹配 (P1)**：
   - [`lca/infrastructure/memory/contextfiles/domain/standing_path.py`](lca/infrastructure/memory/contextfiles/domain/standing_path.py) 仅通过检查路径分割片段是否包含 `".lca"` 来识别 standing 文件；
   - 产生双向漏洞：自定义 `LCA_HOME` 时保护失效，工作区内部有 `.lca` 目录时工作区文件被误杀；未接入权威的 [`lca.infrastructure.path.locator`](lca/infrastructure/path/locator.py)。
5. **协议解析工具名硬编码与参数截断粗暴误杀 (P1/P2)**：
   - [`lca/cognition/brain/prompt/leaked_tool_call.py`](lca/cognition/brain/prompt/leaked_tool_call.py) 将 `<fsWrite>` 标签硬编码解析为 `"write_file"`，而 Wire 实际上是 `writeFile`；
   - `_TRUNCATED_VALUE = re.compile(r"\.{4,}|…")` 对参数任意位置进行全局正则扫描，导致合法包含多个点号的正则表达式、命令输出或脚本被系统作为垃圾调用暴力误杀。
6. **Prompt 组装依赖硬编码文本标记反向刨雷 (P1)**：
   - [`lca/nodes/think/history/assemble.py`](lca/nodes/think/history/assemble.py) 先硬编码拼接 Defer Catalog，再在下次循环中用正则全文匹配剔除，脆弱且易失控。

---

## 2. 负向边界声明 (Does NOT own 铁律，AP-01)

为防止架构蔓延与越权破坏，明确本设计的严格边界：

* **严格禁止修改（Does NOT own）**：
  * **非 LCA 外部资产**：严禁触碰宿主机 `~/everything-library` 智库目录及外部服务（整台机器的外部资产专属于外部仓库，绝不提交至 LCA）；
  * **前置框架与前端代码**：严禁修改 `vendor/`、`lobehub-ui/` 源码（由补丁系统 `deploy/lobehub/patches/` 单独守护）；
  * **无关核心流与业务数据**：严禁修改 `lca/domain/session/` 的持久化格式（Journal/Spine schema），严禁改动已有会话存储；
  * **ADR-0256 正在演进的业务工具实现**：严禁越权回滚或横向改动正在进行中的工具命名空间业务实现，保持职责解耦。
* **所有权（Owns）**：
  * **模板与预设文件**：`lca/plugins/assistant/templates/`（`TOOLS.md`、`AGENTS.md`、`USER.md` 等）；
  * **Prompt 状态行与时间戳**：`lca/plugins/prompts/sections/runtime_env.py`、`runtime_env` 相关 Section 构造与装配契约；
  * **路径安全拦截**：`lca/infrastructure/memory/contextfiles/domain/standing_path.py`；
  * **模型输出解析与风控**：`lca/cognition/brain/prompt/leaked_tool_call.py` 中的 `<fsWrite>` 映射及 `_TRUNCATED_VALUE` 正则；
  * **历史组装解耦**：`lca/nodes/think/history/assemble.py`；
  * **相关回归测试套件**：`tests/plugins/assistant/`、`tests/plugins/prompts/`、`tests/infrastructure/memory/`、`tests/scenario/leaked/` 等。

---

## 3. 核心架构与详细设计

### 3.1 模板净化与框架可移植性治理

1. **`lca/plugins/assistant/templates/TOOLS.md`**：
   - 彻底删除 `10.36.6.252`、`7890` 等私有网段与特定端口；
   - 规范为通用说明：
     ```markdown
     # TOOLS.md - Local Notes

     简短、持久的本地环境备忘，使外部工具在当前这台机器与特定配置中稳定运行：
     设备别名、主机别名/主机映射、偏好配置、特定环境踩过的 quirk。
     Skills 描述工具通用的工作方式；本文件仅记录在此处特有的差异与注意事项。

     ## 本机基准与端口参考
     - 本地认知内核服务与网关端口由当前启动配置确定（默认 `http://127.0.0.1:8765`）
     - 如需配置本地智库、外部工具或代理，请在本文件中按需记录当前环境的特有配置与踩坑事项
     ```
2. **`lca/plugins/assistant/templates/assistant_*/AGENTS.md`**：
   - 移除 6 个助理模板中硬编码的 `~/everything-library` 和端口 `1889`，改为通用的本地/团队智库规范声明。
3. **`lca/plugins/assistant/templates/assistant_*/USER.md`**：
   - 将 `Timezone / 时区：Asia/Shanghai (UTC+8)` 恢复为纯净占位符 `Timezone / 时区：`。

### 3.2 Prompt 真实环境感知动态化 (消除伪造假象)

1. **`render_runtime_row` 与 `RuntimeEnvSection`**：
   - `os_name` 自动探测：调用 `platform.system().lower()`（支持 `linux` / `darwin` / `windows`）；
   - `shell` 自动探测：Windows 下探测 `COMSPEC` / PowerShell，Unix 下读取 `SHELL` 环境变量（默认 `bash`）；
   - `model` 动态提取：允许从 `ContextManifest` / `role_profile` / 活跃模型配置传入，缺省时标注真实当前生效的模型标识（如 `qwen` / `default`），**严禁硬编码伪造为 `Muse Spark`**；
   - `session` / `chat` / `depth` 支持运行时参数真实透传。
2. **`render_developer_timestamp` 与 `DeveloperTimestampSection`**：
   - 时间与时区：若未传入显式 `dt`，使用 `datetime.now().astimezone()` 读取系统真实时间与时区；
   - 时区名称 `tz_name`：由本地时区动态解析（如 `datetime.now().astimezone().tzname()`），不再硬编码 `Asia/Shanghai` 与写死东八区；
   - 客户端来源 `sent_from`：支持运行时根据调用渠道传入真实来源（如 `web` / `cli` / `wechat`）。

### 3.3 路径安全守卫重构 (收敛至权威 Locator)

1. **`standing_path.py` 改造**：
   - 废除 `_AGENT_HOME_SEGMENTS = (".lca",)` 字符串包含检查；
   - 调用 `expand_user_path(path).resolve()`，并获取 `get_lca_home().resolve()`；
   - 使用 `Path.resolve().relative_to(lca_home)` 精确判定目标路径是否位于助理自治家目录内：
     - 若不在 `lca_home` 内部，说明为外部工作区文件，直接放行，**彻底解决工作区内包含 `.lca` 目录时的误杀缺陷**；
     - 若在 `lca_home` 内部且命中 `layout.standing_files` 或 `semantic.json`，则严格拒收并返回安全提示，**彻底解决自定义 LCA_HOME 时保护失效的漏洞**。

### 3.4 协议解析解耦与参数风控优化

1. **`<fsWrite>` 与工具别名对齐**：
   - 将 `<fsWrite>` 解析逻辑统一对齐当前运行时注册的真实文件工具名（Wire 契约优先使用 `writeFile`，同时保留兼容别名映射）。
2. **消解参数截断的暴力误杀**：
   - 将 `_TRUNCATED_VALUE` 从全局匹配任意位置的 `r"\.{4,}|…"`，收紧为**末尾未闭合/省略号截断特征**（如 `r"(\.{3,}|…)\s*$"`），并结合残缺 JSON 状态机判定；
   - 确保用户在 Shell 脚本、代码片段、正则表达式中包含多个点号（如 `echo "1....2"` 或 `grep -E "a....b"`）时，**绝不被系统当成垃圾调用误杀**。
3. **历史组装解耦**：
   - 优化 `assemble.py` 中 `_strip_defer_catalog`，消除循环中的脆弱全文正则替换。

---

## 4. 自动化测试不变量断言矩阵 (Invariants to test, AP-02)

| 不变量编号 | 目标模块 | 必须验证的确定性断言（assert） |
|---|---|---|
| **INV-01 (零私有泄露)** | `lca/plugins/assistant/templates/` | 自动化扫描所有模板文件，断言**不存在**任何私网 IP（`10.36.6.252`）、代理端口（`7890`）和宿主机特定路径（`~/everything-library`）。 |
| **INV-02 (真实模型感知)** | `lca/plugins/prompts/sections/runtime_env.py` | `RuntimeEnvSection.render()` 与 `render_runtime_row()` 绝不再输出硬编码的 `"Muse Spark"`；实际渲染与活跃配置（如 `qwen`）及系统实际 `platform.system().lower()` 严格一致。 |
| **INV-03 (真实时区感知)** | `lca/plugins/prompts/sections/runtime_env.py` | `DeveloperTimestampSection.render()` 生成的时间戳必须基于本地实际时区（通过 `datetime.now().astimezone()` 读取），不再盲目硬编码东八区 `+0800 / CST`。 |
| **INV-04 (路径真值隔离)** | `lca/infrastructure/memory/contextfiles/domain/standing_path.py` | ① 对工作区内的 `.lca/foo.txt`（非 LCA 根目录）断言放行（不误杀）；<br>② 对 `get_lca_home() / "SOUL.md"` 严格断言拦截；<br>③ 对通过环境变量 `LCA_HOME=/custom/path` 指定的自定义目录严格断言保护有效。 |
| **INV-05 (防误杀截断)** | `lca/cognition/brain/prompt/leaked_tool_call.py` | ① 传入包含 `....` 的合法正则或字符串参数，断言**正常解码**为有效 ToolCall（不误杀）；<br>② 传入真正以 `....` 或 `…` 截断收尾的残缺参数，断言**拦截拒收**。 |
| **INV-06 (门禁与合规)** | 全局代码库 | `ruff check` 0 报错；`ruff format --check` 通过；`git diff --check` 0 告警；严格遵守 AP-01 负向边界。 |
