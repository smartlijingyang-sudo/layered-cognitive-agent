# Agent Note: 派生产物增量派生与取消路径终态闭环

Status: implemented

## Problem

`journal.json` / `journal.narrative.md` / `manifest.json` 只在 `RunTerminalizer.terminalize` 一处生成。run 在 `WAITING_INPUT`(askUserQuestion 等 HIL 暂停)被取消时,`RegistryRunCommands.cancel()` 只翻转状态就返回——任务协程早已退出,生命周期 `finally` 不会再跑,终态物化从不执行。被取消的 run 只剩原始流(`<run_id>.spine.jsonl` / `<run_id>.session.jsonl`),`lca-ops debug-run` / `journal trace` 这类读 `journal.json` 的消费方对它们报"找不到文件"。同一缺陷家族还有两处:覆盖写产物各写各的(`manifest.json` / `journal.narrative.md` 非原子写,读方可能看到半截文件);step-tree flush 逻辑与状态→outcome 映射私有在 `terminal/materialization.py`,第二个触发点无处复用。

## Decision

真值流(`<run_id>.spine.jsonl` + `<run_id>.session.jsonl`)与派生产物的边界不变;改变的是派生的**触发时机与所有权**:

1. **单一派生 owner**:`runs/observability/step_tree_flush.py` 持有 `flush_step_tree_artifacts(session, *, outcome=None)`(写 journal.json + narrative.md,异常收进返回的 `flush_errors`,不上抛)与 `journal_outcome_from_session(session)`(状态→outcome 唯一映射)。`terminal/materialization.py` 删除私有副本改为消费;不允许旁路自带映射或绕过 owner 直写。
2. **暂停点是增量派生点**:`RunLifecycleCoordinator._finish_or_pause` 的 `WAITING_INPUT` 分支在 `mark_paused` 前调 `flush_step_tree_artifacts`(outcome 推导为 `paused`)。派生物在等待输入期间即可读;派生失败只留痕,不阻塞暂停(控制/观察分离,不变量 C7)。
3. **取消闭环**:`cancel()` 排空任务后,若循环未在执行(暂停态 / 任务已退出)且 `session.closed` 为假,补 `RunTerminalizer.terminalize(session, workspace=None, success=False)`。运行中被取消的 run 由生命周期 `finally` 独家收口(被取消协程的 `finally` 中的 `await` 不会被再次取消,terminalize 能完整跑完),命令路径不重复物化;`RunSession.closed` 是 exactly-once 守卫。
4. **覆盖写单一原语**:`lca/infrastructure/atomic_write.py` 的 `atomic_write_text`(同目录临时文件 + `os.replace`)是全部覆盖写产物的落盘机制;journal.json(原自带临时文件逻辑)、narrative.md、manifest.json(原非原子 `write_text`)三处接入。追加流(`FileSink` / `JsonlSessionPersistence`)语义不同(append + flush/fsync 策略、hash 链、header 信封),不走本原语。

## Alternatives considered

### 只在 cancel() 补 terminalize,不做暂停点派生?

能修复"取消后无 journal"的直接症状,但无限期暂停的 run(用户一直不回答)在暂停期间仍然没有派生物,进程崩溃 / 重启也丢掉暂停点之前的所有派生现场;调试"这个 run 卡在等什么"时仍要手工 fold。暂停点 flush 是 O(run 长度) 的无状态全量 fold,暂停稀有,成本可忽略。

### 每个 step / turn 边界都增量 fold?

派生物会更"实时",但 fold 是无状态全量重算,长 run 每步一次意味着 O(n²) 读盘;且需要把触发点埋进认知循环 / loop driver,跨越 transport 与 cognition 的 seam。暂停 + 终态两个自然挂起点已覆盖全部已知失败模式,原始流本身逐步完整,不为未观察到的需求加写盘。

### 把 manifest.json 也在暂停点写?

manifest 承载终态语义(`terminal_event_seq`、doctor 诊断、终态水位),暂停时写会产出内容错误的"终态"文件,消费方无法区分。保持终态专属。

### 把 `FileSink` / `JsonlSessionPersistence` / 覆盖写抽成同一个写原语?

追加流各自携带不同不变量(spine 的 fsync 协议与异常双写、session 的 header 首行与每行 flush),强行统一只会造出一个参数爆炸的上帝写入器;三处重复的是覆盖写,抽覆盖写。

## Consequences

- 任何到达终态状态(completed / failed / canceled)的 run 必有 `journal.json` + `journal.narrative.md` + `manifest.json`;暂停中的 run 至少有暂停时刻的 journal + narrative。
- `cancel()` 对非运行态 run 的终态收口会释放 cursor token 与 per-run Session 绑定(`session.close`),取消不再泄漏 run-local ContextVar。
- 新增派生触发点只能挂在 `flush_step_tree_artifacts`;新增覆盖写产物必须走 `atomic_write_text`。
- 回归锁:`tests/transport/test_cancel_materializes_artifacts.py`(暂停取消物化、运行中取消不二次物化、exactly-once 守卫、暂停增量派生、派生失败不阻塞暂停)。
