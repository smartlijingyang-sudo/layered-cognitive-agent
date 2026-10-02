# Assistant Drawer & Top UI Redesign Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Redesign the assistant right status drawer and top mascot avatar to provide product-level clean UI, 5 distinct tabs (动态, 批准, 即将到来, 身份, 连接器), 2-column identity cards with direct click-to-edit, dual-pane activity log modal, and fix chat input autofill and avatar head truncation.

**Architecture:**
- Frontend React/Ant Design components in `deploy/lobehub/patches/ui/`.
- Managed and synchronized into `lobehub-ui/` via `deploy/lobehub/patch_lobehub.py`.
- Pure frontend styling, state management, and API integration with existing assistant endpoints.

**Tech Stack:** React, TypeScript, Ant Design, antd-style, Next.js (LobeHub).

---

### Task 1: Fix Top Mascot Truncation & Chat Input Autofill

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantTopMascot.tsx`
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Does NOT own: Backend files, contracts, LobeHub global router.
- Invariants to test:
  - Mascot container has downward vertical offset (`margin-top: 5px` / `padding-top: 4px`) so avatar head does not get clipped in `NavHeader` (44px height).
  - `handleTriggerChatEdit` updates `window.__mainEditor` via `setDocument('markdown', text)` and calls `focus()`.

**Step 1: Edit `AssistantTopMascot.tsx`**
Adjust styles for `container` to add `margin-top: 5px` and safe padding so `translateY(-2.5px)` breathing animation does not breach top bounds.

**Step 2: Edit `AssistantStatusDrawer.tsx` `handleTriggerChatEdit`**
Update `handleTriggerChatEdit` to query `window.__mainEditor` or `window.__editor` first, then fall back to DOM elements.

**Step 3: Verification**
Check code compilation and exports.

**Step 4: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantTopMascot.tsx deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "fix(ui): adjust top mascot vertical offset and fix chat editor prompt fill"
```

---

### Task 2: Clean Up Technical Wording & Setup 5-Tab Layout

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Does NOT own: Backend files, contracts, LobeHub global router.
- Invariants to test:
  - Title shows `{assistantName}` with online tag; no "状态与真值中心" or "File as SSOT".
  - Bottom `ssotBanner` is removed.
  - Tab bar has 5 tabs: `动态`, `批准`, `即将到来`, `身份`, `连接器`.
  - Tab bar fits without squeezing the 5th tab off-screen.

**Step 1: Remove low-level wording**
Remove "· 状态与真值中心", "File as SSOT · 磁盘唯一真值文件架构", and `styles.ssotBanner`.

**Step 2: Update `SectionKey` and `Segmented` options**
Define `type SectionKey = 'activity' | 'approvals' | 'upcoming' | 'identity' | 'connectors'`.
Set options:
- `🕒 动态`
- `⚖️ 批准`
- `⏰ 即将到来`
- `🪪 身份`
- `⚡ 连接器`

**Step 3: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "feat(ui): clean technical wording and set up 5 product tabs in assistant drawer"
```

---

### Task 3: Implement `🪪 身份` 2-Column Grid & Click-to-Edit

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Does NOT own: Backend files, contracts.
- Invariants to test:
  - Cards for standing files (`IDENTITY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `MEMORY.md`) displayed in 2-column grid (`grid-template-columns: repeat(2, 1fr)`).
  - No "全屏编辑资源" button.
  - Entire card is clickable (`cursor: pointer`), triggering `onEditFile`.

**Step 1: Update styles for 2-column grid**
Add `identityGrid` style:
```css
display: grid;
grid-template-columns: repeat(2, 1fr);
gap: 12px;
```

**Step 2: Update card render**
Make the whole card clickable and remove the "全屏编辑" button. Display icon, filename, role tag, summary, and size.

**Step 3: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "feat(ui): implement 2-column grid and direct click-to-edit for identity cards"
```

---

### Task 4: Implement `🕒 动态` (Activity Timeline) with Dual-Pane Log Modal

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Does NOT own: Backend files, contracts.
- Invariants to test:
  - Grouped by date (今天, 昨天, 较早).
  - Row shows status/action icon (green checkmark, browser, terminal, file), short title, summary, timestamp.
  - Clicking any row opens a dual-pane modal: left sidebar item list, right detailed human-readable execution log (commands, inputs, results).

**Step 1: Define activity data model & mock/fetch pipeline**
Define `ActivityItem` interface with id, type, title, summary, timestamp, details (command, result, output, humanExplanation).

**Step 2: Render timeline list in drawer**
Render grouped date sections with clickable cards.

**Step 3: Implement Dual-Pane Detail Modal**
Modal with left item list and right detail display.

**Step 4: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "feat(ui): implement activity timeline and dual-pane detail log modal"
```

---

### Task 5: Implement `⚖️ 批准` & `⏰ 即将到来` Panels

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Does NOT own: Backend files, contracts.
- Invariants to test:
  - Approvals shows pending and recent approval records with status tags.
  - Upcoming shows scheduled reminders / cron jobs fetched from `/v1/assistants/${id}/jobs`.

**Step 1: Implement `ApprovalsPanel` inside Drawer**
Render approval cards with status tags (`待审批`, `已批准`, `已拒绝`), action name, description, timestamp.

**Step 2: Implement `UpcomingPanel` inside Drawer**
Fetch or display cron jobs (`/v1/assistants/${assistantId}/jobs`) with title, cron expression / interval, next run, enabled switch.

**Step 3: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx
git commit -m "feat(ui): implement approvals and upcoming cron panels in drawer"
```

---

### Task 6: Upgrade `ConnectorsPanel.tsx` UI & Prevent Button Overflow

**Files:**
- Modify: `deploy/lobehub/patches/ui/ConnectorsPanel.tsx`
- Does NOT own: Backend files, contracts.
- Invariants to test:
  - "立即连接" / "运行中" button does not overflow right boundary.
  - Top-tier modern visual design (subtle border, refined gradients, clean tags).

**Step 1: Update styles in `ConnectorsPanel.tsx`**
Refine card header, padding, action buttons flex layout.

**Step 2: Verification**
Check layout in 480px drawer.

**Step 3: Commit**
```bash
git add deploy/lobehub/patches/ui/ConnectorsPanel.tsx
git commit -m "feat(ui): polish connectors panel design and fix right boundary overflow"
```

---

### Task 7: Patch Engine Synchronization & Verification

**Files:**
- Verify: `deploy/lobehub/patch_lobehub.py`
- Does NOT own: External repositories.
- Invariants to test:
  - `python3 deploy/lobehub/patch_lobehub.py` succeeds with exit code 0.
  - All patched files in `lobehub-ui` match the sources.

**Step 1: Run patch engine**
`python3 deploy/lobehub/patch_lobehub.py`

**Step 2: Run verification**
`python3 deploy/lobehub/patch_lobehub.py verify`

**Step 3: Commit any metadata if needed**
```bash
git add deploy/lobehub/
git commit -m "chore(lobehub): reconcile and verify ui patches"
```
