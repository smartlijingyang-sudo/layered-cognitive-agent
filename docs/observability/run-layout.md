# Run Layout — ADR-0065 §七

## 目录布局

```
traces/
├── latest.json                    # { "run_id": ..., "kind": "run_pointer" }
│                                  # 临时文件 + 原子 rename;非事实来源
└── runs/<unguessable_run_id>/     # run_id 即目录名(ULID)
    ├── journal.jsonl              # JournalRecord 的 durable 序列化
    ├── manifest.json              # RunManifest(timestamp + terminal event + 高水位 + 完整性)
    ├── evidence/                  # 内容寻址对象
    │   ├── sha256-<digest>.txt
    │   └── sha256-<digest>.json
    └── materializations/<generator-id>/<generator-version>/
        ├── summary.md
        ├── cost.json
        └── decision-tree.md
```

## latest.json 原子更新

写 `latest.json.tmp-{pid}-{counter}` → `os.replace()` 到 `latest.json`;
每次 fsync 内容。损坏则重建。**不是事实 owner**(L6)。

## 目录命名

`<unguessable_run_id>` 由 `lca/contracts/atoms/ids.py:new_run_id()` 生成
(ULID-like,12 hex,128 bit 随机性)。

**禁止**:
- 本地时间戳(身份语义不应带时钟)
- 部分 hash(不可逆)
- 人类命名(不稳定)

## check 脚本

`scripts/check_run_naming.py` 扫描 `traces/runs/` 下目录名必须是 `<run_id>`(不可猜测 ULID),不允许 `<timestamp>_<hash>`。