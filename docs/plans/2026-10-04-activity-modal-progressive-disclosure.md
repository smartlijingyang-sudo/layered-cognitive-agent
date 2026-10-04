# Progressive Disclosure Activity Modal Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Transform the activity detail modal (`AssistantStatusDrawer.tsx`) into an informative, elegant progressive disclosure interface with a continuous left timeline, top Hero verdict card, smooth handling of long reasoning/scripts, and a collapsible engineering inspection zone.

**Architecture:** Frontend component enhancement in `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx` preserving zero mock values, verified with automated tests in `tests/deploy/test_step_state_machine_purity.py` and synced via `deploy/lobehub/patch_lobehub.py`.

**Tech Stack:** React, TypeScript, Ant Design, Lucide icons, CSS Modules, Python (pytest for contract tests).

---

### Task 1: Contract & Pure Parsing Invariants Test Suite (TDD)

**Files:**
- Modify: `tests/deploy/test_step_state_machine_purity.py`
- Does NOT own: Backend routes, `query_endpoints.py`, external storage, LobeHub core engine [AP-01].
- Invariants to test:
  - `INV-MODAL-01`: Model metrics (`model`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `decision`) are extracted purely from `s.thinking` when present, without fabrication [AP-02].
  - `INV-MODAL-02`: Strict exit code check: `undefined` is never error; only `typeof exit_code === 'number' && exit_code !== 0` or `ok === false` [AP-02].
  - `INV-MODAL-03`: Zero mock values invariant: no hardcoded token or latency fallbacks [AP-02].

**Step 1: Write the failing tests**
Add test functions in `tests/deploy/test_step_state_machine_purity.py`:
- `test_modal_step_item_preserves_thinking_and_tool_call_telemetry()`
- `test_modal_zero_mock_contract_no_fake_tokens()`

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_step_state_machine_purity.py -k "test_modal_step_item_preserves_thinking" -v`
Expected: FAIL (attributes or assertions not yet in TSX/helper).

**Step 3: Write minimal implementation in `AssistantStatusDrawer.tsx`**
Ensure `ModalStepItem` interface includes:
```typescript
interface ModalStepItem {
  id: string;
  step_title: string;
  stateVisual: StepStateVisual;
  iconType: StepIconType;
  narrative: string;
  command?: string;
  exit_code?: number;
  duration_ms?: number;
  truncated_boundary?: boolean;
  code_snippets?: Array<{ label: string; code: string; language?: string }>;
  search_results?: Array<{ index: number; location: string; match: string }>;
  conclusion?: string;
  stage?: string;
  params?: Record<string, any>;
  result?: string;
  // Engineering Telemetry
  thinking?: {
    model?: string;
    latency_ms?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    decision?: string;
    reasoning?: string;
  };
  tool_call?: {
    name?: string;
    arguments?: Record<string, any>;
  };
  tool_result?: {
    ok?: boolean;
    exit_code?: number;
    latency_ms?: number;
    stdout_head?: string;
    stderr?: string;
    delta_summary?: string;
    error?: string;
  };
}
```
And populate them inside `runDetail.steps.forEach(...)`.

**Step 4: Run test to verify it passes**
Run: `pytest tests/deploy/test_step_state_machine_purity.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add tests/deploy/test_step_state_machine_purity.py deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "test(ui): add modal progressive disclosure telemetry contract tests"
```

---

### Task 2: Left Sidebar Visual Upgrade - Vertical Timeline & Latency Badges

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_step_state_machine_purity.py`
- Does NOT own: Backend API, Drawer title, or unrelated tabs (`identity`, `approvals`, `upcoming`, `connectors`) [AP-01].
- Invariants to test:
  - Continuous vertical line connector connecting sequential step nodes [AP-02].
  - Latency badge rendered cleanly on the right of step title if `duration_ms` exists [AP-02].
  - Semantic icon mapping (`●`, `✔`, `📄`, `✕`, `◐`) with subtle pulse animation limited strictly to `running` state [AP-02].

**Step 1: Write test for timeline rendering and latency formatting**
Add test in `tests/deploy/test_step_state_machine_purity.py`:
- `test_sidebar_timeline_semantic_icons_and_latency_badge()`

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_step_state_machine_purity.py -k "test_sidebar_timeline" -v`
Expected: FAIL.

**Step 3: Implement timeline styles & markup in `AssistantStatusDrawer.tsx`**
Update `detailSidebar`, `detailSidebarItem`, add connector line CSS (`detailSidebarTrack`, `detailSidebarNode`), latency badge tag (`stepLatencyBadge`), and pulse effect for running state only.

**Step 4: Run test & apply hot patch**
Run: `python3 deploy/lobehub/patch_lobehub.py assistant_status_drawer && pytest tests/deploy/test_step_state_machine_purity.py -v`
Expected: PASS (45 ok, 0 broken).

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/test_step_state_machine_purity.py
git commit -m "feat(ui): implement continuous vertical timeline and latency badges in modal sidebar"
```

---

### Task 3: Right Main Body - Hero Verdict Card & Long Content Viewports

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_step_state_machine_purity.py`
- Does NOT own: Backend API, drawer outer structure [AP-01].
- Invariants to test:
  - `conclusion` is hoisted to the top Hero Verdict Card directly beneath the step title [AP-02].
  - Long narrative text has gradient mask + toggle button (`展开全部思考 / 收起`) when text length exceeds 120 chars [AP-02].
  - Long command/code blocks display line count header (e.g. `bash · 86 行`) and constrained scrolling viewport (`maxHeight: 240px`, `overflowX: 'auto'`) [AP-02].

**Step 1: Write test for top Hero Verdict Card & long content boundaries**
Add test in `tests/deploy/test_step_state_machine_purity.py`:
- `test_right_panel_hero_verdict_card_hoisted_on_top()`
- `test_right_panel_long_narrative_and_code_viewport_guards()`

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_step_state_machine_purity.py -k "hero_verdict" -v`
Expected: FAIL.

**Step 3: Implement Hero Verdict Card & Viewport Guards in `AssistantStatusDrawer.tsx`**
- Move `verdictBanner` to immediately follow the step title header.
- Add `narrativeExpanded` state and toggle button for long text.
- Add code header with language & line count, set `maxHeight: 240` and `overflowX: 'auto'`.

**Step 4: Run test & apply hot patch**
Run: `python3 deploy/lobehub/patch_lobehub.py assistant_status_drawer && pytest tests/deploy/test_step_state_machine_purity.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/test_step_state_machine_purity.py
git commit -m "feat(ui): hoist hero verdict card and add long text/code viewport guards"
```

---

### Task 4: Collapsible Engineering Inspection Zone (Devin-grade On-Demand Telemetry)

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_step_state_machine_purity.py`
- Does NOT own: Backend schemas, database models [AP-01].
- Invariants to test:
  - Collapsible inspection zone titled `🔍 深度工程观测与诊断数据 (按需展开)` [AP-02].
  - Card A: Model name, thinking latency, prompt tokens, completion tokens, decision [AP-02].
  - Card B: Structured arguments JSON with copy button [AP-02].
  - Card C: Raw stdout/stderr terminal view with boundary indicator [AP-02].
  - Card D: Full thinking chain Markdown renderer with internal scrollable viewport (`maxHeight: 380px`) [AP-02].
  - Zero mock fallback: sections only render if true values exist [AP-02].

**Step 1: Write test for inspection zone structure and zero-mock invariant**
Add test in `tests/deploy/test_step_state_machine_purity.py`:
- `test_inspection_zone_telemetry_cards_and_zero_mock_invariant()`

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_step_state_machine_purity.py -k "inspection_zone" -v`
Expected: FAIL.

**Step 3: Implement Collapsible Inspection Zone in `AssistantStatusDrawer.tsx`**
- Add accordion/collapse component below metadata bullets.
- Implement Cards A, B, C, D using Ant Design and Lucide icons.
- Ensure strict conditional rendering (no fabricated numbers).

**Step 4: Run test & apply hot patch**
Run: `python3 deploy/lobehub/patch_lobehub.py assistant_status_drawer && pytest tests/deploy/test_step_state_machine_purity.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/test_step_state_machine_purity.py
git commit -m "feat(ui): implement collapsible engineering inspection zone in activity modal"
```

---

### Task 5: End-to-End Validation & Verification Matrix

**Files:**
- Test: `tests/deploy/test_step_state_machine_purity.py`
- Sync: `deploy/lobehub/patch_lobehub.py assistant_status_drawer`
- Diff: `git diff --check`
- Does NOT own: Host machine files, unrelated modules [AP-01].

**Step 1: Run comprehensive tests and patch verification**
```bash
python3 deploy/lobehub/patch_lobehub.py assistant_status_drawer
pytest tests/deploy/test_step_state_machine_purity.py -v
git diff --check
```

**Step 2: Update live task tracker in `<project-root>/docs/plans/task.md`**

**Step 3: Commit final integration**
```bash
git add docs/plans/task.md
git commit -m "docs(task): complete progressive disclosure activity modal implementation"
```
