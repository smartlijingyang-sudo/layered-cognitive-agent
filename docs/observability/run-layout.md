# Run Layout — ADR-0065 §七 + ADR-0167

## 目录布局（目标态）

```text
traces/
├── latest.json                         # { "run_id": ..., "kind": "run_pointer" }
│                                       # 临时文件 + 原子 rename；非事实来源
└── runs/<unguessable_run_id>/          # run_id 即目录名 (ULID)
    ├── events.jsonl                    # EventSpine SSOT（执行点账本）
    ├── journal.json                    # 物化视图 lca.journal/3.1（step 故事）
    ├── journal.narrative.md            # 人读轨迹（deriver）
    ├── manifest.json                   # RunManifest（封印 / 高水位 / 完整性）
    ├── profile_snapshot.json           # boot 组合快照
    ├── model_visible/                  # 模型所见正文（按 step）
    │   └── step_001/
    │       ├── request-header.json
    │       ├── system-prompt.md
    │       ├── tool-schemas.json
    │       ├── context-manifest.json   # 含 skill_catalog 等
    │       └── messages.json           # 实际送入 LLM 的 messages
    ├── evidence/                       # 内容寻址大对象
    │   ├── sha256-<digest>.txt
    │   └── sha256-<digest>.json
    └── materializations/<generator-id>/<generator-version>/
        ├── summary.md
        ├── cost.json
        └── decision-tree.md
```

可选遗留（非新 run 主路径）：`journal.raw.jsonl`（旧 stream 兼容）。

## 文件分工（读轨迹时按这个找）

| 你想知道 | 打开 |
|---|---|
| 发生了哪些执行点、耗时、错误链 | `events.jsonl` |
| 第几步想了什么、调了哪些工具（故事） | `journal.json` / `journal.narrative.md` |
| **当时模型完整看见了什么**（prompt / tools / skills） | `model_visible/step_NN/` |
| 大段工具输出 / 附件正文 | `evidence/` |
| Profile 装了谁 | `profile_snapshot.json` |

原则（ADR-0167）：**Model-visible ≡ logged**；journal 持 digest + 相对路径，不把整段 prompt 塞进 `objective`。

## 谁写什么 (ADR-0167.1 D1–D3)

| 文件 | 写者 | 触发 |
|---|---|---|
| `events.jsonl` | `RoutingFileSink` (registry 的 storage face) | 每个 spine EP |
| `journal.json` | `StepTreeAccumulatorDeriver.flush()` | transport 在 terminalize 时调 (run 末尾) |
| `journal.narrative.md` | `StepNarrativeWriter` 由 `_StepTreeBundle.flush()` 触发 | run 末尾 |
| `manifest.json` | `record_terminal_materialization()` | terminalize |
| `model_visible/` | `StepTreeAccumulatorDeriver._write_model_visible()` | 每次 step close |
| `evidence/` | body / tool / facade 任意 evidence 写入者 | 同步 content addressing |

**单一写入原则**：每个文件只有一个真实写入者（deriver 或 sink），不允许两个模块竞争同一文件。旧的 `StepGroupedBackend.flush` 已被删除（与 `StepTreeAccumulatorDeriver.flush` 重复写 `journal.json`）。

**StepTreeAccumulatorDeriver 装配位置**：`RunSessionBuilder.build` 阶段（**不是** boot 阶段）。
deriver 需要 `run_id / run_dir / agent_role / strategy_key / plan_ref`，这些字段是 per-run 的；
boot 阶段（`spine.core.setup`）不再订阅任何 per-run deriver。

```text
RunSessionBuilder.build(run_id=X)
    ├── StepCoordinator          ← Agent 唯一可见写入口 (ADR-0167 D2)
    ├── StepTreeAccumulatorDeriver(run_id=X, run_dir=...)
    │      └── event_spine.subscribe(deriver.on_event)
    └── assemble_run_hub(...)
```

## latest.json 原子更新

写 `latest.json.tmp-{pid}-{counter}` → `os.replace()` 到 `latest.json`；
每次 fsync 内容。损坏则重建。**不是事实 owner**。

## 目录命名

`<unguessable_run_id>` 由 `lca/contracts/atoms/ids.py:new_run_id()` 生成。

**禁止**: 本地时间戳目录名、部分 hash、人类随意命名。

## check 脚本

`scripts/check_run_naming.py` 扫描 `traces/runs/` 下目录名必须是 `<run_id>`。

## 参考

- [ADR-0167](../adr/0167-spine-ssot-and-step-materialization.md) D3/D4
- [ADR-0167.1](../adr/0167.1-step-tree-deriver-wiring-and-run-layout-cleanup.md) D1–D7
- [ADR-0166](../adr/0166-step-segment-phase-and-spine-hardening.md)
- [ADR-0065](../adr/0065-recoverable-evidence-ledger.md)
