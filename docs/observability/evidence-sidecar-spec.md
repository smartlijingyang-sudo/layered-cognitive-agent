# Evidence Sidecar Spec — ADR-0065 §四

## 契约

```
EvidenceRef      → 指向 EvidenceStore 一份受治理载荷的不可变引用
EvidenceReceipt  → prepare() 成功后返回的不可变收据
EvidenceStore    → prepare() / get() / contains() / sweep_orphan()
EvidencePolicy   → classify() / retention() / should_inline()
```

## L5 摘要不匹配必须显式 raise

`EvidenceStore.get()` 重新读 + 重算 sha256 + 比对 byte_length;任何不一致
抛 `EvidenceIntegrityError`,**绝不**返回 None 掩盖失败。

## 准备/验证/引用/提交协议

1. `EvidenceStore.prepare(payload, ...)` → 写 staging + fsync + atomic rename
2. 验证:再读 + 重算 +比对
3. 引用:`EvidenceReceipt.content_sha256 == ref.digest`
4. 提交:账本 `JournalRecord.evidence` 携带 `ref`

## Audience 策略

PUBLIC ⊆ INTERNAL ⊆ RESTRICTED ⊆ CONFIDENTIAL。请求方 `audience < ref.classification` → `PermissionError`。

## 默认 Policy

- `restricted` / `confidential` 永不内联
- `public` / `internal` ≤64 KiB 内联
- 关键字触发升级:`password` / `secret` / `api_key` / `private_key` 等 → `restricted`

## sweep_orphan(ledger_index)

清掉不被任何 run 引用的对象;幂等。残留 staging 临时文件视作孤儿。

## check 脚本

`scripts/check_evidence_atomic.py` 扫描实现路径,确保 `prepare()` 内不静默
`try/except`(L5 摘要不匹配必须显式 raise)。