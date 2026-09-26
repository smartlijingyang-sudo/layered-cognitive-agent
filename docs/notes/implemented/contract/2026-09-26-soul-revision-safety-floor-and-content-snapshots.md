# Agent Note: SOUL 修订安全底线与内容级修订快照

Status: implemented

## Problem

助理可以在对话中通过 `update_assistant_soul` 重写自己的 SOUL.md。实测 run（run_084f8dab8576）暴露三个事实。

第一，`revise_profile` 只校验四个核心段（🧠身份/🎭性格/🛠能力/🗣语气），安全边界/记忆规则/错误处理/红线四个模板段可以被整体删除且校验放行。该 run 中模型重写语气后，成文的安全段全部丢失。红线可被一次 prompt 注入或一次失误重写静默移除。

第二，缺段校验的报错只列段名，模型第一次重写常因丢段被拒，多消耗一轮 LLM 调用。

第三，`revisions/N.json` 只存 manifest digest 不存文件内容，且 `create()` 不写基线快照。`write_revision_snapshot` docstring 承诺「供回滚与审计」，实际无法回滚到任何历史版本。

业界对 agent 自修改人格文件的共识是：自修改系统提示词/persona 需要外部闸门、版本化可回滚存储、冻结/受保护段落，以及高风险变更的人工审批（自演化 agent 安全研究，如 Self-Healing Harness、AgentSelfEdit 的确定性门）。

## Decision

- `revise_profile` 的 soul 分支在 `_validate_soul` 通过后复用 `_merge_soul_defaults`：缺失的安全段先从当前磁盘 SOUL.md 补（保留用户已定制文案），仍缺再从该助理模板渲染结果补。未登记模板（如 LobeHub 导入遗留）降级到内置默认模板，保底不丢安全段。提交文本显式给出的安全段以提交为准。安全段是平台保底，revise 不能整体删除。
- `_validate_soul` 缺段报错附可照抄的四核心段骨架（`_SOUL_CORE_SKELETON`），模型重试少走一轮。
- `write_revision_snapshot` 在快照 JSON 追加 `files` 键（CONFIG_FACE_FILES 中存在文件的全文）；`create()` 写 `revisions/0.json` 出生基线，使回滚可以恢复内容而不只是校验 digest。读回 UI 仍按 ADR-0242 开放问题暂缓。
- 安全段标记词表提升为 `_home_layout.SOUL_SAFETY_SECTIONS` 公开常量，catalog 与 self_manage_tools 共用，消灭双份词表。
- `UpdateAssistantSoulTool` 增加可选 `confirmed` 参数：提交的安全段文案与当前文件不同时必须为 true，模型须先经 `askUserQuestion` 获得用户同意。对齐 ADR-0242 D6 敏感修改审批语义。读不到当前文件按不敏感处理，revise 内部的 digest 校验仍 fail-closed。

## Alternatives considered

- **校验要求全八段（strict validation）**：强迫模型每次复读安全段文本，复读引入漂移风险，且与 ADR-0242 附录 C「安全段模板预置、无需手写」的既定契约冲突。
- **内容快照走独立 digest 寻址存储（CAS）**：快照无读方，属过度设计；`files` 键增量进入现有快照即可，无迁移负担。
- **确认门放在 `catalog.revise_profile`**：REST PATCH 路径是用户亲自发起，无需二次确认；门放 agent 工具边界符合信任分级（agent 低信任、用户高信任）。
- **do nothing**：安全段已在真实运行中丢失，红线可被静默删除，不可接受。

## Consequences

- 已丢安全段的存量助理在下一次 revise 时自动补回（自愈），补回来源优先当前文件、其次模板默认文案。实测的 asst_5166b058964f 属于此类。
- 快照体积从 ~1KB（digest）增至配置面全文（几十 KB 级），随 revision 数线性增长；个人助理量级可接受。
- `dream.py` 直写 USER.md 的 `user-md-preimage-*.md` 前置镜像与 `files` 快照并存，存在统一到单一快照入口的机会，留给后续决策。
- 验证：`tests/plugins/assistant/test_self_manage.py` 新增 `TestSoulRevisionSafety` 六组用例，覆盖合并保留定制文案、坏档自愈、错误消息骨架、创建基线快照、篡改检测+reimport 恢复链；`TestSelfManageTools` 新增安全段修改确认门三态。实时 run 复测改语气后安全段完整保留。