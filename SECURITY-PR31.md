# SECURITY-PR31: Doctor spine.jsonl / fold 路径安全快速审

**范围**: `step_check.py` + `fold_source.py` 的读路径( spine.jsonl / fold 重建)
**日期**: 2026-09-04
**审者**: Security subagent
**状态**: 报告交付,不改代码(除非明确 CWE)

---

## 审计路径链

```
GET /runs/{run_id}/doctor
  → query_endpoints.get_run_doctor(run_id)
  → RunPort.doctor(run_id)
  → RegistryRunQueries.doctor(run_id)
  → self._registry.spine_path_for(run_id)
  → FilesystemRunLocator.events_path(run_id)
  → self._root / "runs" / run_id / spine_filename_for_run(run_id)
  → diagnose(session, spine_path)
  → diagnose_step_tree(journal_path)
  → _scan_xref(run_dir, run_id, scan)  ← read_text() ×2
  → fold_model_visible(run_dir, run_id, step_id)
  → _iter_spine_records(spine_path)  ← SpineReader.events() 逐行
```

---

## 发现

### F-01 · `run_id` 无输入校验 — 路径穿越(防御纵深缺失)

**文件**: `FilesystemRunLocator.run_dir()` (`run_locator_fs.py:48-49`),
`_profile_snapshot_path()` (`query_endpoints.py:51-56`),
`spine_filename_for_run()` (`naming.py:33-38`)

**严重度**: MEDIUM(CWE-22)

**现状**: `run_id` 从 URL path param 直接流入 `Path` 拼接,全链路无 format/sanitize。

**缓解因素**: Starlette `{run_id}` 路由 pattern 匹配单段(不吞 `/`),所以
`GET /runs/..%2F..%2Fetc/doctor` 不会匹配路由。但:

1. `_profile_snapshot_path` 有 fallback:`_DEFAULT_PROFILE_SNAPSHOT_ROOT / run_id / _PROFILE_SNAPSHOT_NAME`。若未来路由改成 `{run_id:path}` 或内部调用方传 `../` 构造的 run_id,即可穿越。
2. `spine_filename_for_run(run_id)` → `f"{run_id}.spine.jsonl"`。若 run_id = `"foo\0bar"`,Path 行为依赖 OS。
3. 内部调用方(脚本、CLI、测试)不经 HTTP,无路由保护。

**建议**: 在 `RunLocator` 入口或 `run_id` 构造处加正则白名单:`^[a-zA-Z0-9_\-\.]+$`。

---

### F-02 · `step_check._scan_xref` 全文件 `read_text()` 两次 — OOM 风险

**文件**: `step_check.py:89, 146`

**严重度**: MEDIUM(CWE-400 / Uncontrolled Resource Consumption)

**现状**: `_scan_xref()` 对同一 spine ledger 调 `spine_path.read_text()` **两次**:
一次计 EP 分布,一次扫 payload schema。每次把整个文件加载进内存后 `.splitlines()` 再建中间 dict。

**风险**: 长 session 的 spine.jsonl 可达数百 MB。Doctor 是 GET 端点,无认证 + 无 rate limit,攻击者可触发对大 run 的 doctor 请求制造 OOM。

**建议**:
- 改 `SpineReader.events()` 逐行迭代(已有),单次遍历完成两种扫描;
- 或加文件大小上限(`if spine_path.stat().st_size > MAX: skip`)。

`fold_source._iter_spine_records()` 走 `SpineReader.events()` 是逐行读取,无此问题。

---

### F-03 · DoctorReport 泄漏服务端文件系统路径

**文件**: `step_check.py:196`, `models.py:62, 78`

**严重度**: LOW-MEDIUM(CWE-200)

**现状**: `DoctorReport.journal_path` 和 `StepScan.spine_path`(经 H-xref `extra["spine_path"]`)直接包含服务端绝对路径,随 JSON 响应返回客户端。

```json
{
  "journal_path": "/home/deploy/lca/traces/runs/run_abc/spine.jsonl",
  "hops": {"H-xref": {"spine_path": "/home/deploy/lca/traces/runs/run_abc/run_abc.spine.jsonl"}}
}
```

**风险**: 暴露部署目录结构,辅助后续攻击(已知路径写文件、LFI 验证等)。

**建议**: 响应中只返回 `run_id` 相对路径或去除 `journal_path` / `spine_path` 字段;完整路径仅落 logger(已做)。

---

### F-04 · 异常信息泄漏到 API 响应

**文件**: `query_endpoints.py:192, 228, 243`

**严重度**: LOW(CWE-209)

**现状**:
- `get_run_profile`: `"error": "invalid profile snapshot", "run_id": run_id` — 低风险,但 `run_id` 未校验即可反射。
- `get_run_evidence`: `"detail": str(exc)` 直接序列化 `EvidenceIntegrityError` / `PermissionError` / `KeyError`,可泄漏内部路径或堆栈细节。

**建议**: Error response 返回稳定 code + 人类可读 message,异常详情仅 log。

---

### F-05 · 无认证 / 无 rate limit

**文件**: `routes_runs_sessions.py:55`, 全 webserver transport

**严重度**: HIGH(若网络暴露) / LOW(若仅 loopback)

**现状**: 全 `/runs/*` 路由树无 authentication middleware、无 rate limiting。Doctor endpoint 是只读 GET,但可触发大文件读取(F-02)。

**缓解因素**: 默认绑定 `127.0.0.1:8765`(loopback)。若生产部署在反向代理后无 auth,则任意客户端可枚举 run_id + 触发 OOM。

**建议**: 至少对 `/runs/{run_id}/doctor` 加 `express-rate-limit` 等价物;生产部署强制 auth middleware。

---

### F-06 · `fold_source._iter_spine_records` 异常吞没

**文件**: `fold_source.py:137-149`

**严重度**: INFO(非漏洞,可观测性缺口)

**现状**: `SpineReader` 构造失败和 `events()` 抛错均 `log.debug` 后 return。Doctor 层面看 spine "不存在"。若 spine 文件存在但格式错误导致 `SpineReader` 抛错,fold 路径返回 `None`,caller 走 sidecar fallback — 行为正确但 debug 日志在生产环境默认不可见。

**建议**: 升级 `_log.debug` → `_log.warning`(带 run_id + path),便于运维诊断。

---

## 汇总

| ID | 严重度 | CWE | 文件 | 问题 | 需要立即修? |
|---|---|---|---|---|---|
| F-01 | MEDIUM | CWE-22 | `run_locator_fs.py`, `naming.py` | run_id 无格式校验,路径穿越纵深缺失 | 建议加白名单 |
| F-02 | MEDIUM | CWE-400 | `step_check.py:89,146` | spine 全文件 read_text ×2,OOM 风险 | 建议改迭代 |
| F-03 | LOW-MED | CWE-200 | `step_check.py`, `models.py` | 绝对路径泄漏到 API 响应 | 建议去除 |
| F-04 | LOW | CWE-209 | `query_endpoints.py` | 异常详情反射到客户端 | 建议稳定 code |
| F-05 | HIGH* | CWE-799 | `routes_runs_sessions.py` | 无 auth / rate limit | 取决于部署 |
| F-06 | INFO | — | `fold_source.py` | 异常吞没,debug 级日志 | 建议升 warning |

\* F-05 仅在生产暴露于非 loopback 时为 HIGH。

## 明确 CWE 需修复项

**无 CRITICAL**。F-01(路径穿越) 有 CWE-22 但被 Starlette 路由 pattern 缓解,实际触发需内部调用方传恶意 run_id。F-02(OOM) 有 CWE-400 但需大文件 + 公网暴露组合。**均不满足"明确 CWE 立即修"阈值**,列入 backlog 跟踪。

---

*报告结束。不改代码,不 commit 代码变更。*
