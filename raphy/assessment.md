# Raphy Assessment — 2026-10-18 22:58 round (`raphy/arch-20261018-2258`)

Basis: main tip `f3f6ba97d` (clean worktree; RA-146 merge just landed in this
round's step B). 3 hot areas read end-to-end; runtime verification run on the
branch worktree with `LLM_API_KEY=<redacted> No code outside `raphy/` touched.

## Phase 1 — Explore

### Hot-spot scan (`git log --oneline -40`)

The last 40 commits are dominated by three lanes:
1. **browser tooling** (agy): 13-tool suite (`de18490a0`), live page wiring
   (`c0be39af2`), full-lifecycle scenario tests + transfer arbitration
   (`a9c32b409`), browser task layer integration (`f16373216`,
   `bf2faf54f`).
2. **raphy rounds** (RA-146 just merged this round): BrowserSubagent
   fabricated-results convergence onto the shared execution seam.
3. **iter-quality / iter-tests / memory**: N-series AST hygiene, memory
   layout budget bump (`877a6fc25`), sense-gate dead-store merge
   (`61462fc05`, in `lca/cognition/memory/` — frozen zone).

Hot areas chosen for the friction walk: (A) the browser 13-tool suite
(`lca/infrastructure/tools/browser/tools.py`, 1075L, read end-to-end),
(B) `parse_step_evidence` / `ActivityIntentNamer`
(`lca/contracts/models/observability/activity.py`), (C) memory sense gate
(`lca/cognition/memory/sensors.py`) — **skipped: ralph Round 2 frozen zone**,
recorded as examined-but-off-limits.

### Organic friction walk

#### Area A — browser 13-tool suite (`tools.py`, all 17 tool classes read)

1. **Bouncing between small modules?** No — good locality: all 17 tools live
   in one file. `BrowserNavigateTool(BrowserOpenTool)` is a pure rename
   alias ("向前兼容"); the deletion test is borderline (deleting it moves
   the alias need to callers), not a candidate.
2. **Shallow modules?** The `_get_driver` 6-line method is copy-pasted
   verbatim into 6 tool classes (Open/Find/Spawn/Click/Screenshot/Close) —
   mechanical duplication, weakest finding class; noted, not storied.
3. **Pure functions hiding call-site bugs?** No — the real finding is worse:
   **three tools fabricate `success=True` results with no real execution
   behind the seam**:
   - `BrowserSearchTool.execute` returns canned
     `"Search Results for: {query}"` + a fake google.com URL, `success=True`,
     without calling anything. A real search seam exists two directories
     away: `lca/infrastructure/search/service.py::web_search` (guarded by
     `any_search_provider_available()`), with Exa/SearXNG/Tavily providers.
     The tool bypasses the seam and lies.
   - `BrowserLookupCitationUrlTool.execute` returns
     `resolved_url=f"https://example.com/ref/{cid}"` — a URL that does not
     exist — with `success=True`. Any downstream consumer that opens it gets
     a 404 or, worse, trusts a fabricated citation.
   - `BrowserDeepResearchTool.execute` returns "已启动深度研究任务 …
     研究智能体已在独立登出沙箱中开始联网研判" with `success=True` and
     `status: "running"`, but dispatches nothing — no worker, no handoff
     wiring. The "running" status is a lie; nothing will ever report back.
4. **Leaky seams?** The task-layer tools (spawn/steer/peek/close/transfer)
   and the driver-backed tools (open/find/click/screenshot/close) are honest:
   real driver calls, real task_store reads, failures returned as failures.
   The leak is the opposite direction — the three fabricated tools *look*
   like the honest ones through the identical `Tool.execute` interface.
5. **Untested / can't test through the interface?** This is the sharpest
   point — **the lie is pinned as contract**:
   `tests/contracts/browser/test_browser_muse_full_suite.py::test_muse_lightweight_search_and_citation`
   asserts `obs.success is True` and `len(results) > 0` on the canned
   output, then feeds the fabricated `citation_id` into the lookup tool and
   asserts success. Per the RA-146 pattern ("伪造结果钉进测试 = 把谎言变成
   契约"): the test proves the fabrication is stable, not that search works.
   "The interface is the test surface" — through this interface you cannot
   distinguish "searched the web" from "returned a template".

#### Area B — `parse_step_evidence` / `ActivityIntentNamer` (`activity.py`)

1. **Bouncing?** No — single module, single call site
   (`infrastructure/observability/activity_feed.py`).
2. **Shallow?** The `parse_step_evidence` narrative chain is a long
   if/elif of hardcoded Chinese template strings keyed on tool-name
   substrings. It reads like content, not architecture: converting it to a
   data table would be a mechanical transform with zero seam movement.
3. **Deletion test**: deleting the chain moves per-tool narrative copy into
   callers or a table — moves, doesn't concentrate. Not a candidate.
4. **Verdict**: examined, no story. Single occurrence (no twin), no leaky
   seam, tested surface. The honest-engineering question here would be
   whether narratives should be LLM-generated, but that re-litigates product
   direction, out of scope.

#### Area C — memory sense gate — skipped (frozen zone)

`lca/cognition/memory/sensors.py` is ralph Round 2 territory (progress.txt
禁区). Not read beyond the commit stat.

### Runtime verification

- Agent smoke with `MockLLMAdapter`: `RUN1: completed | RUN2: completed`
  (two sequential runs on one agent, no crash/hang).
- Browser e2e: `tests/scenario/browser/test_browser_preview_and_takeover_e2e.py`
  passed as part of this round's merge verification (14 passed batch).
- No P0 crash/hang/silent-failure found.

### Duplication scan (secondary)

Only mechanical duplication found: the 6 identical `_get_driver` methods in
`tools.py`. Weakest class, not storied alone.

## Phase 2 — Self-grilling (RA-147)

- **Constraints**: the 13-tool contract is pinned (ADR-0248 §5.3 / ADR-0280;
  `test_browser_muse_full_suite.py` pins names/namespaces). Tool
  `name`/`namespace`/`parameters` must not change. INV-05 voice isolation
  untouched (these tools carry no vocal tools).
- **Dependencies**: callers = agent tool-calling loop via
  `build_browser_tools()`; the real seam is
  `lca/infrastructure/search/service.py` (`web_search`,
  `any_search_provider_available`, `format_search_content`) with provider
  registry (exa/searxng/tavily). `citation_id` values are minted by the
  search tool itself (`cit_{search_id}_N`) — the lookup tool can only resolve
  them against a result cache the search service retains.
- **Shape of the deepened module**: `BrowserSearchTool.execute` calls
  `web_search(query)` when `any_search_provider_available()`, maps
  `SearchResponse` hits to `citation_id`/`title`/`url`/`snippet` results;
  when no provider is configured it returns `success=False` with an honest
  error ("未配置搜索 provider"). The lookup tool resolves against the
  search service's recent-results cache; unknown citation → `success=False`.
  `BrowserDeepResearchTool` either gets a real dispatch path or returns
  `success=False` ("深度研究 worker 未实现") — the fake "running" claim is
  deleted either way.
- **Test survival**: `test_muse_lightweight_search_and_citation` pins the
  fabrication and must be rewritten (recording fake search service, or
  fail-closed assertions). The rest of `test_browser_muse_full_suite.py`
  (names, namespaces, task lifecycle, find) is unaffected.
- **Deletion test verdict**: deleting the three fabricated branches
  concentrates honesty at the seam — the fake code earns nothing. Concentrates.
- **Strength**: Strong. Same class as RA-146 (fabricated-results interface +
  testability gap), real seam exists two directories away, tests pin the lie.

## Phase 3 — Present and record

### Candidate table

| # | Files | Problem | Solution | Benefits (locality+leverage) | Strength |
|---|-------|---------|----------|------------------------------|----------|
| 1 | `lca/infrastructure/tools/browser/tools.py` (BrowserSearchTool / BrowserLookupCitationUrlTool / BrowserDeepResearchTool); `tests/contracts/browser/test_browser_muse_full_suite.py` | Three tools return `success=True` with fabricated payloads: canned "Search Results for: {query}", `https://example.com/ref/{cid}` URLs that don't exist, and a "deep research started / running" claim that dispatches nothing. A real search seam (`lca/infrastructure/search/service.py`, exa/searxng/tavily) sits unused two directories away. The fabrication is pinned as contract by `test_muse_lightweight_search_and_citation`. | Route `browser_search` through `web_search` (fail-closed when no provider); resolve citations against the search service's recent-results cache (unknown → fail-closed); delete the fake deep-research "running" claim (real dispatch or fail-closed). Rewrite the pinning test to assert honest behavior. | Locality: one file, one seam, one test — the honesty fix lives exactly where the lie lives. Leverage: every future consumer of these tools (agent loop, subagent executor) stops building on fabricated results; the search service becomes the single source of web-search truth. | **Strong** |

**Top recommendation**: RA-147 is the one story this round. It is RA-146's
twin in the adjacent module — the same "interface 声称执行、实现伪造结果"
shape, the same "测试把谎言钉成契约" evidence, and this time the real seam
already exists (`lca/infrastructure/search/`). Do it before more agent logic
builds on `browser_search` output.

**Diversity quota**: satisfied — the story comes from the friction walk
(fabricated-results interface + testability gap), not from duplication.

Assessment complete: 1 story written, top is RA-147.
