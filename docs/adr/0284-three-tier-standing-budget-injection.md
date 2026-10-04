# ADR-0284：Standing 三层预算注入契约

## 状态

**Proposed — 2026-10-04**

> **一句话**：standing 组装从字符级截断（`_cap`/`_fit` + 末尾 `[:budget_chars]` 兜底切片）升级为三层注入架构——Tier-1 platform 整段注入、预算外、零截断；Tier-2 protected 整节装包、自有预算、丢节告警；Tier-3 projection 剩余预算内整节装包。本 ADR 是已实现（`5098195a0`，李超 2026-10-04）的事后契约化，四个待拍板项收敛给李超。

## 0. 接任务前 7 问

1. 谁受益？需要跨 assistant 生效的平台规则（URL 铁律）——再也不怕被预算截掉；身份文件（CONSTITUTION/SOUL/IDENTITY/USER）——宁可整节丢也不被拦腰斩；审计方——截断行为从字符级黑箱变成节级可观测（丢哪一节有名有姓）。
2. 真实问题？是。旧实现 `assemble_standing` 用 `_cap`/`_fit` 字符级截断：`_cap` 把剩余预算减半封顶（`min(remaining, max(remaining // 2, min(240, remaining)))`），`_fit` 从字符串中间拦腰斩断，末尾再补一刀 `[:budget_chars]`——todo-40 实测：URL 铁律 4 行在模板偏移 13651/23838，3000 预算下模型实际看不到。
3. 删掉会坏什么？回到字符级截断：平台级重要规则可能再次静默消失（todo-40 的截断实锤会重演）。
4. 更简单方案？只给 platform 免截断、其余保持旧截断。否决：`_cap` 的"减半封顶"本身就是不可解释的启发式；整节原子性同时修了 protected 文件被拦腰斩的诚实问题（斩断的半句话比整节丢失更危险——模型会按残句脑补）。
5. 契约先行？反向：实现已先落地（见 §1 证据链），本 ADR 是事后契约化 + 待拍板收敛。诚实声明，不伪装成"先设计后实现"。
6. 与现有 ADR 冲突？无。ADR-0258 C1（standing 永不进压缩流）：`preserve_standing_sections` 改为连 platform 块一起从磁盘刷新（"prompt 复用不丢 platform 块"），是对 0258 的实现补强而非冲突。ADR-0266 写权限矩阵：本 ADR 只定读注入规则，不动写路径。
7. 状态诚实？Proposed。实现已合 main，但待拍板①②③④需李超裁决后才能转 Accepted/Implemented。

## 1. 实证（main@a9fa65e0f）

- `lca/infrastructure/memory/contextfiles/domain/standing.py`：`split_sections`（`^#{2,3}\s` 为界，preamble 归 heading=None；heading 行归属其节）；`pack_sections`（整节 whole-in/whole-drop，`on_drop_section(name, heading)` 回调）；`assemble_standing(..., platform_files, protected_files, protected_budget_chars)` 三层分流；`_cap`/`_fit` 已删；`StandingTruncationError`（`LCA_STRICT_STANDING=1` 才抛，生产只打 `logger.warning`）。
- `lca/infrastructure/memory/contextfiles/layout.toml`：`platform_files=["PLATFORM.md"]`（注释明示"Resolved against get_lca_home() (~/.lca), NOT the assistant home. A missing file is skipped silently (fail-soft)"）、`platform_heading="## 平台共享规则（{name}，对所有助手生效）"`、`protected_files=["CONSTITUTION.md","SOUL.md","IDENTITY.md","USER.md"]`（注释"Must be a subset of standing_files"）、`protected_budget_chars=32000`（注释实测：protected 四文件共 ~30705 chars，32000 留 headroom）、`backstory_budget_chars=36000`（注释：tier2+tier3 共用；tier3 剩 4000，实测投影文件 ~4185 chars——projection 本身就会触发整节丢弃，见待拍板②的现实意义）。
- `lca/infrastructure/memory/contextfiles/service/assembly.py`：`read_platform_documents`（OSError 静默跳过、空文件跳过、注入时戳 `platform_heading` 留 provenance）；`read_standing_documents`（tier1 先读）；`refresh_standing_backstory` 新增 `platform_root` 参数（测试注入点，生产默认 `get_lca_home()`）。
- `lca/infrastructure/memory/contextfiles/service/compaction.py`：`preserve_standing_sections` 新增 `platform_root` 参数；platform documents 拼在 standing files 之前一并 `refresh_injected`（docstring："a prompt reuse never drops the platform blocks"）。
- `lca/plugins/assistant/persona/persona.py`：`persona_from_home(home_path, *, platform_root=None)`；旧 `_read_text` 删，统一走 `read_standing_documents`。
- `lca/plugins/assistant/templates/CONSTITUTION.md`：URL 铁律 4 行移出模板（`-4` 行）；铁律现由 252 部署落盘的 `~/.lca/PLATFORM.md` 承载——**repo 内无 PLATFORM.md 模板**（`git ls-files | grep -i PLATFORM` 零命中），todo-41 P1 仍 open。
- 测试证据：`0decbc2e8`（`tests/infrastructure/memory/test_context_layout.py`、`test_shared_standing.py`、`test_standing_preservation.py`、`test_standing_refresh.py`、`tests/plugins/assistant/test_persona.py` 三层行为测试）；`1629e5728`（铁律契约改钉：`test_url_iron_rule_reaches_model_via_platform_tier`——PLATFORM.md 经 `platform_root` 整段注入、零截断；旧 strict-xfail 的 `test_url_iron_rule_survives_standing_assembly` 前提死亡已删；todo-40 关闭）；`030b990cf`（3 个 stale assertion retarget 到三层行为）。

## 2. 契约

- **C1（Tier-1 platform）**：`layout.platform_files` 从 `get_lca_home()`（`~/.lca`）解析，**不是** assistant home；整段注入、预算外、零截断；缺失文件静默跳过（fail-soft）、空文件跳过；注入时戳 `platform_heading`（模型可见的平台 provenance）。run 首轮组装（`persona_from_home`）与 turn 间刷新（`refresh_standing_backstory`）、compaction 刷新（`preserve_standing_sections`）三个入口行为一致。
- **C2（Tier-2 protected）**：`layout.protected_files`（packaged 布局下须为 `standing_files` 子集；home override 的 merge 走 sanitize，见 C6）；按 markdown section（`##`/`###`，preamble 归 None）整节装包，**绝不拦腰斩**；在自有预算 `protected_budget_chars` 内；整节丢弃→`logger.warning(name, heading)` 留痕；`LCA_STRICT_STANDING=1` 时改为抛 `StandingTruncationError`（仅开发用，生产只 log）。
- **C3（Tier-3 projection）**：剩余预算 `backstory_budget_chars - protected_budget_chars` 内同样整节装包；丢弃**静默**（无 `on_drop_section` 回调——与 tier-2 不对称，见待拍板②）。
- **C4（字符级截断禁令）**：`_cap`/`_fit` 退役后，任何 tier 不得出现字符级拦腰截断；`assemble_standing` 末尾不再有 `[:budget_chars]` 兜底切片。预算超限的唯一合法动作是整节丢弃。
- **C5（输出顺序）**：输出按 documents 顺序（platform 块在前 + standing 原顺序），tier 只决定装包规则、不决定排序（`assemble_standing` docstring 原话）。
- **C6（merge sanitize）**：home override（`memory/contextfiles.toml`）的 tier 不变量走 sanitize 不拒绝——protected∩standing 保留、其余丢弃；platform 与 standing 重叠部分剔除；`protected_budget_chars` 钳制 `≤ backstory_budget_chars`；packaged 布局的 `read_layout` 保持 strict 抛错。设计意图：自定义 home 不因改文件清单/缩预算而整体回退到 packaged 布局（fail-soft 优先于 fail-fast，沿 ADR-0256 Task 3 修订先例）。

## 3. 待拍板（交李超）

1. **Tier-1 fail-soft vs 启动存在性检查**：缺失 PLATFORM.md 时静默跳过——铁律"静默消失"是最危险的失效模式（todo-41：repo 无模板 + fail-soft 跳过 = 新机器上铁律缺席且无告警）。接受现状，还是 kernel boot 时做存在性检查（缺文件发 warning 事件，todo-41 提案③）？
2. **Tier-3 丢弃静默 vs 同 tier-2 打 warning**：不对称是故意（projection 本来就是投影、可丢）还是疏漏？现实意义：projection 文件实测 ~4185 chars > 4000 预算，整节丢弃**正在发生**且无声。
3. **状态迁移**：本 ADR Proposed→Accepted 由李超拍板；实现已合 main，Accepted 后是否标 Implemented（按 0280 先例需 Implementation Notes 证据链——本 ADR §1 即证据链，裁决时确认即可）。
4. **`platform_heading` 语言**：中文措辞"平台共享规则（{name}，对所有助手生效）"，而 identity-disclosure 行刚被改写为英文——是否统一语言？边缘项，可顺手定。

## 4. 交叉引用

- ADR-0258（compaction 豁免）：platform 块随 `preserve_standing_sections` 从磁盘刷新、不进压缩流——0258 C1 的 tier-1 落点。
- todo-40（URL 铁律截断）：被 tier-1 架构解决——`1629e5728` 改钉后机制测试全绿，本项关闭。
- todo-41（PLATFORM.md 部署漂移）：repo 内无模板 + fail-soft 静默跳过，P1 仍 open；本 ADR 待拍板①是其决策入口。
- ADR-0266（写权限矩阵）：本 ADR 只定读注入，不动写路径，无交集。
- todo-31（constitution design doc）：该设计文档对三层预算架构零提及——作者侧是否补记，交作者（arch 不动李超正文）。

## 5. 决策记录

（待李超裁决后填写）
