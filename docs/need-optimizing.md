> **状态（2026-07-29）**：下列三项已在 `docs/refactor-pr-list.md` 对应 PR 中落地。
> 详见 `assembly.py` / `semantic_keys.py` / `InternalTransport.wait_result` / `docs/registry-catalog.md`。

~~Registry 越来越多…~~ → **已收敛**：发现型 vs 运行时绑定型分类 + `ensure_defaults` + registry-catalog。

~~TypedState working_memory 字符串键…~~ → **已类型化**：`final_output` / `last_error` / `active_template` / `team_progress_text` 一等字段；扩展袋用 `semantic_keys`。

~~DelegateOperation 50ms 轮询…~~ → **已 await 化**：`InternalTransport` Future + `wait_result`；远程 transport 保留 poll 回退。
