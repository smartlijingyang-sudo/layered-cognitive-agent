# Agent Note: FTS 记忆索引与检索决策树

Status: implemented

## Problem

`memory_search` 只做内存子串扫描，无法覆盖每日流水，也没有提示层面的检索义务。ADR 要求 `memory/index` 持有全文索引，并要求系统提示注入强制检索决策树与防幻觉终端闸门。

## Decision

新增 `MemoryIndex` 端口与 `SqliteFtsIndex` 适配器。索引构建服务读取语义记录与 `memory/*.md` 每日流水，写入 `memory/index/fts.sqlite3`。CJK 文本按字切分后存入 FTS5 的 searchable 列，中文查询按单字命中；FTS5 不可用时回退到 LIKE 子串扫描。`memory_search` 优先查询该索引，索引不存在时回退到原有扫描。系统提示新增 `memory_retrieval` 段落：豁免三类请求，其余实质请求必须多角度查询、未命中扫描文件兜底，仍落空时明确承认缺失、绝不编造。索引由 `lca-ops memory dream` 在慢路径重建。

## Alternatives considered

### 为什么不用 FTS5 原生 tokenizer 直接索引中文？

`unicode61` 把连续 CJK 串当成一个 token，多字中文查询无法命中。按字切分后 `"杭" OR "州"` 能匹配「用户住在杭州」，行为与子串检索一致。

### 为什么索引不参与写入路径？

索引是投影，可随时重建。写入仍走 `semantic.json` 与 `MEMORY.md` 投影，索引只服务检索。

## Verification

`tests/infrastructure/memory/test_retrieval_index.py` 覆盖索引构建、`memory_search` 查询索引与无索引回退、检索决策树渲染。`tests/scenario/memory/test_adr0254_conformance_evals.py` 的 EVAL-RETRIEVAL-DUTY 与 EVAL-ANTI-HALLUCINATION 覆盖提示中的决策树与终端闸门。