# ADR-0271：Avatar 头像系统对齐与补遗

## 状态

**Proposed — 2026-10-03**

> **一句话**：agy 的 ADR-0269《助理头像生成系统》（2026-10-02 落盘）+ `lca/contracts/models/avatar/`
> （commit `d43ec9c04`）已把头像系统契约大部落地；本 ADR 不是第二套契约——只记录与 0269 的
> **重叠清单**、三处**实质冲突**（待拍板）、0269 **未覆盖的新契约条目**。0269 仍是头像系统主契约，
> 本 ADR 不 supersede 0269。

## 0. 背景与编号说明

- arch 轮曾备 0271 草稿《Avatar 头像系统契约：生成管线后端契约》（C1–C11，
  2026-10-02 23:09 只读轮 `hidden_files/adr-0271-draft.md`），原计划落盘 0271。
- 2026-10-03 开工发现：agy 已于 2026-10-02 落盘 ADR-0269《助理头像生成系统》
  （85 行：接任务前 7 问 / 独立插件边界 / 数据模型与存储 / 生成管线与身份特征 /
  三态候选池 / 定时换装 / WS 推送通道 / 安全红线 / 验证），并提交
  `lca/contracts/models/avatar/__init__.py`（80 行）+ `tests/plugins/avatar/test_contracts.py`
  （70 行，commit `d43ec9c04`）。
- 处理原则（质量铁律：提交诚实 + ADR 深审四问）：**不制造双契约**。
  原草稿 C1–C7/C10 的落盘点多被 0269 更具体地覆盖 → 原草稿撤回，改为本对齐+补遗 ADR。
  原草稿文件保留在 `hidden_files/adr-0271-draft.md` 备查，不删除。

## 1. 重叠清单（原草稿 C 点 → 0269 对应，不重复立案）

| 原草稿 | 0269 对应 | 结论 |
|---|---|---|
| C1 两轮分离（create 只进池不激活） | §4 铁律"第一轮绝不自动激活" | ✅ 覆盖 |
| C2 候选池 24h TTL | `AvatarCandidate` TTL=created_at+24h | ✅ 覆盖；上限 20+FIFO 未覆盖 → 见 N2 |
| C3 user_request 原文传递 | §3 prompt=`{user_request_verbatim}` + traits | ✅ 覆盖 |
| C4 edit 必须以当前激活图为 reference（禁从零重绘） | §7 `reference_image` provenance=user 或当前 active | ✅ 覆盖 |
| C5 variants 多尺寸 + 视频异步 | `AvatarVariant` 四尺寸 + `avatar_video_ready` | ✅ 覆盖 |
| C6 clear 恢复默认 | `active==null` 回退 `profile.json` emoji / SVG 萌宠 | ✅ 覆盖 |
| C7 定时换装 opt-in 后 auto-activate | §5 `avatar_edit(auto_activate=True)`，CronJob 载体 | ✅ 覆盖；opt-in 粒度未提 → 待拍板⑤ |
| C10 落盘 SSOT（JSON+图片） | `avatar/state.json`（原子写 + revision） | ✅ 覆盖；IDENTITY.md 追认部分 → 冲突 X1 |

## 2. 实质冲突（待拍板，只提案不擅自决定）

### X1 IDENTITY.md 写入路径

- **草稿 C10**：`set` 时原子更新 IDENTITY.md 追认为契约（延续 CONNECTOR-TASK-6——agy
  `3d0ad6e93` 落地的交互式选图卡片 + 一键原子更新 IDENTITY.md）。
- **0269**：`IDENTITY.md` 的 `avatar:` frontmatter 历史写法**退役，不再新增写入**；
  独立插件，不复用 widget 写入路径（§1 明确拒绝"扩展 assistant 插件"替代方案，
  理由是旧写入路径与 `profile.json` SSOT 冲突）。
- **待拍板**：前端交互式换装（CONNECTOR-TASK-6）保留独立写入路径，还是统一走 avatar 插件状态？
  双写（用户手动改 IDENTITY.md vs 插件 `state.json`）的冲突消解需要产品拍板。

### X2 `avatar` 工具域（第九域）

- 0269 新增 `avatar` 工具域；ADR-0256 的 8 域划分（core/file/shell/memory/skill/web/agent/ext）
  未预留扩展位，`namespace` 闭集被实质改动。
- 影响面：0256 的 namespace 闭集、`test_namespace_declaration.py` conformance 套件、
  DeferPolicy 8 域闭环均需修订联动。
- arch 轮提案：0256 出修订案（域清单 8→9，或 avatar 并入现有域——如 `agent` 域），
  由李超拍板方向后再动手；本轮只记录冲突。

### X3 视频异步与 0268 四类异步执行体的衔接

- 0269 §5：视频走 `POST /v1/videos` + 轮询，完成后推 `avatar_video_ready`；§6 WS 用
  Redis pub/sub 独立 `/events` 通道（§6 明确拒绝"复用 run 级网关 WS"）。
- 缺口：0269 未声明视频异步任务落在 0268 四类异步执行体的**哪一类**；
  0269 §0 第 6 问已有"视频失败 `video_status=failed`、可重触发"（可接受），缺的是类型归属声明。
- 待拍板/补齐：视频任务的 0268 类型归属 + 重试语义归属声明。

## 3. 新契约条目（0269 未覆盖，Proposed）

### N1 并发/重入守卫（硬契约）

同一 assistant 同时只许**一个在途生成**（create/create 互斥、create/set 互斥）；
客户端双击用幂等 key 去重。守卫失败 **fail-closed**，不排队。
（0269 有 set 幂等，无生成并发守卫。）

### N2 候选池上限（硬契约）

上限 **20** 个候选，超限时 FIFO 淘汰未激活候选（已激活永不淘汰）。
与 24h TTL 正交：防"24h 内高频 create"把池撑爆。

### N3 隐私补强

- 用户照片作 `reference_image` 必须用户**明确提供**（显式上传或路径指定）；
  agent 不得自行从媒体库/相册取用。（0269 §7 只约束了 provenance=user，
  未排除"agent 自行取用媒体库照片"。）
- 生成图片落**本地路径**，不走鉴权 CDN；`prompt_used` 只记文本 prompt，不含照片二进制。

### N4 第一人称话术（提示级）

头像变更回执用第一人称（"我已换上新头像" / "候选已生成，还没换上"），
与 ADR-0267 行为机制（推理不复述规则、拟人表达）一致。
（0269 §0 第 1 问是用户视角描述，未定话术。）

### N5 原草稿待拍板 5 项的归宿

- ① 落盘位置 → 0269 已决策（assistant home `avatar/`），草稿撤回。
- ② 默认头像 → 0269 已决策（emoji / SVG 萌宠回退），草稿撤回。
- ③ clear 时 variants 去留 → **仍待拍板**（见下）。
- ④ 视频异步载体 → 0269 已决策（独立 `AvatarCostumeScheduler` + 0268 CronJob 混合，
  正式 worker 后退役，§5），草稿撤回。
- ⑤ opt-in 粒度 → **仍待拍板**（见下）。

## 4. 验收（N 条目测试形状，tests 轮认领）

- **T-N1**：并发 create，第二个被拒（fail-closed），`active_id` 不变。
- **T-N2**：池满 20 时 create 新候选，最早的未激活候选被 FIFO 淘汰。
- **T-N3**：`reference_image` 来自非 user-provenance 路径 → 工具入口拒绝。
- **T-N4**：set 回执文案第一人称断言（提示级，宽松匹配）。

## 待拍板（只提案，不擅自决定）

1. X1：IDENTITY.md 写入路径去留（双写冲突怎么解）。
2. X2：avatar 第九域 vs 并入现有域（0256 修订方向）。
3. X3：视频异步在 0268 四类中的类型归属声明。
4. N5③：clear 时 variants 保留还是随激活态清理。
5. N5⑤：定时换装 opt-in 按 assistant 开关 vs 全局开关。

## 决策记录

- 2026-10-03 iter-arch 轮落盘（worktree 隔离自 main@`d43ec9c04`）：
  原 0271 草稿（C1–C11）撤回，改为本对齐+补遗 ADR；0269 仍是头像系统主契约，
  本 ADR 不 supersede 0269；实证行号指本轮 worktree（HEAD `d43ec9c04`）。

---

## 附：与 0269 的边界（防重复立案）

| 主题 | 0269《助理头像生成系统》 | 0271（本 ADR） |
|---|---|---|
| 插件边界/数据模型/生成管线 | ✅ | 不重复，引用 |
| REST/WS/定时换装载体/验证矩阵 | ✅ | 不重复，引用 |
| 两轮分离/24h TTL/verbatim/edit 参考图 | ✅ | §1 重叠清单记录 |
| 冲突记录（X1–X3） | 未覆盖 | ✅ 本 ADR |
| 并发守卫/池上限/隐私补强/第一人称话术 | 未覆盖 | ✅ N1–N4 |
| 草稿待拍板 5 项归宿 | 部分已决策 | ✅ N5 |
