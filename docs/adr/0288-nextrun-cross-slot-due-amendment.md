# ADR-0288: ADR-0268 修正案 —— next_run 跨越式 due 语义

> **Status: Proposed**（2026-10-05 起草）
> 本提案是 ADR-0268（Proposed，2026-10-02）的修正案：修订其 §5 的 `due` 判据。
> **未落地任何代码，不改变任何现状**；语义修由 quality lane 认领，契约测试已由 tests lane 钉住。

## 1. Context（发现）

ADR-0268 §5 规定 `next_run` 是纯函数："`now` 正好落在触发点上时 `due` 为真"。
实现（`lca/domain/cron/next_run.py`）把"正好落在"翻译成了微秒级 datetime 相等：
hourly/daily/weekly 要求 `second == 0 and microsecond == 0`；interval 要求 `candidate == now_local`。

daemon 的采样时刻来自 `asyncio.sleep` 唤醒后的 `datetime.now(UTC)`，几乎不可能恰好落在
触发档的零微秒上 → **周期任务永不触发**。真机实测（ADR-0287 / commit `21d8aec53` 的
message）：tick 1s / every 5s，30 秒内触发 0 次；同 store 的 oneshot 触发 1 次。
这是"调度器看着正常、任务永远不跑"的 P0 级缺陷（backlog todo-47）。

tests lane 已在 `tests/domain/cron/test_next_run_catchup_contract.py` 用 5 个
`xfail(strict=True)` 契约测试钉住期望语义（todo-47，2026-10-05 01:09 轮 `12d09f73b` 落盘）；
本修正案把该语义写进 ADR，实施链：arch 修正案 → quality 语义修 → tests 摘 marker。

## 2. Decision（提案，待裁决）

**D1（跨越式 due）。** `due` 的判据从"采样时刻 == 触发档（微秒相等）"改为
"采样时刻已越过（含命中）最近一档触发点 T，且 T 未被 `last_run` 服务"：

- 小时/日/周：T 为本周期最近一档墙钟触发点，`T <= now_local` 即 due 为真；
- 间隔：候选档按 `every_seconds` 前进，`T <= now` 的最近一档未被服务即 due 为真。

**D2（档归属防重，同一档只触发一次）。** "T 未被 last_run 服务"的判定：

- 小时/日/周：`last_run` 落在 T 的档区间内即视为已服务
  （小时档：`[T, 下一小时同 minute)`；日档：T 当天；周档：T 本周）；
- 间隔：`last_run` 的相位档（自 `anchor_at`/`last_run` 起按 `every_seconds` 步进的落点区间）覆盖 T 即视为已服务。

已服务档内重复采样 → due 为假，不重复触发。

**D3（只补最近一档）。** 跨越式 due 只认最近一档；更早的未服务档不逐个补跑
（间隔按 `last_run` 相位自然前进）。0268 原文"早于 `now` 的档不补跑"
收缩为"早于最近一档的不补跑"。多档积压的 missed-run 补偿是 ADR-0278
（routine/cron 双调度器收敛）的议题，本修正案不越界。

**D4（`upcoming` 不变量不变）。** `upcoming` 仍是严格晚于 `now` 的下一档；
due 为真时 upcoming 取再下一档。`NextFire` 的"不返回早于或等于 `now` 的 datetime"
不变量保持，投影语义（`next_run_local`）不受影响。

**实施链。** quality lane：`next_run.py` 按 D1–D4 改判据（行为变更，仅 cron 调度路径）；
回归边界为现有 `tests/domain/cron/test_next_run.py`（18 tests）+ `test_service.py`；
语义修落地后 tests lane 摘掉 5 个 `xfail(strict=True)` marker
（XPASS(strict) 会强制变红提醒，不会静默通过）。

## 3. Alternatives considered（凝练）

- **A（维持微秒相等，daemon 端 sleep 对齐触发档）。** daemon 无法控制 `asyncio.sleep`
  的唤醒微秒；对齐是玄学，重试只会放大抖动。驳回。
- **B（跨越式但逐档补跑所有错过档）。** 停机三天后 daily 任务一次补三天 run，
  run 记录爆炸且用户无感知价值；missed-run 补偿属 ADR-0278 议题。驳回。
- **C（把 due 判据放宽到"整分钟内"等固定窗口）。** 窗口宽度是魔法数，
  且与 interval 的任意 `every_seconds` 不兼容；跨越式（`T <= now`）无窗口参数。驳回。

## 4. 验收标准

- `tests/domain/cron/test_next_run_catchup_contract.py` 6 tests 全绿
  （5 个摘 marker 后真绿 + 1 个恰好命中对照测试）。
- 现有 `test_next_run.py` 18 tests + `test_service.py` 零回归
  （如有断言旧相等语义的用例，由 quality 轮按本修正案同步，而非放水改测试）。
