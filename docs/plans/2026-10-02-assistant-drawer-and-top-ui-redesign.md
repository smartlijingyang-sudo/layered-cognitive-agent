# Assistant Drawer & Top UI Redesign

**Date**: 2026-10-02
**Autopilot Level**: `DRAFT`
**Status**: Approved by User

## 1. Context & Motivation

The assistant drawer and top header mascot have several UX and product-level issues:
1. **Low-level wording**: The drawer title uses "状态与真值中心" and subtitle "File as SSOT · 磁盘唯一真值文件架构", plus a technical banner explaining SHA-256 optimistic locking and File as SSOT. These are backend implementation details that should not be exposed in product UI.
2. **Tab redundancy**: Previously there were 5 tabs (`identity`, `rules`, `memory`, `workspace`, `connectors`). The first three represent the assistant's persona and standing files. The `workspace` tab duplicated these markdown files even though workspace files already have their own dedicated space in the main interface.
3. **Tab layout overflow**: With 5 lengthy tabs, the rightmost tab ("⚡ Connectors") was squeezed and pushed off-screen.
4. **Card layout**: File cards were stacked vertically with a technical "全屏编辑" (fullscreen edit) button. User requested a 2-column grid ("一行两个") where cards are directly clickable to edit.
5. **Chat input bug**: Editing avatar or name from the pencil menu announced "已将指令填入输入框", but nothing appeared in the chat box because it queried for `<textarea>` while LobeChat uses a rich ProseMirror editor (`window.__mainEditor`).
6. **Avatar head truncation**: The top Mascot avatar in `NavHeader` (height 44px) was positioned too high, causing the animal's head/ears to be cut off by the top boundary.

## 2. Boundaries & Scope

### Owns (In Scope)
- `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`:
  - Product-level title `{assistantName}` with online tag; remove SSOT banner and technical jargon.
  - Implement 5 tabs:
    1. `🕒 动态` (Activity timeline grouped by today/earlier, with status icons, summaries, and clickable rows opening a split modal: left item list, right detailed human-readable logs of commands & outputs).
    2. `⚖️ 批准` (Approvals list & status).
    3. `⏰ 即将到来` (Upcoming scheduled tasks & cron reminders).
    4. `🪪 身份` (2-column card grid for `IDENTITY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `MEMORY.md`, directly clickable to edit).
    5. `⚡ 连接器` (Upgraded top-tier connector cards).
  - Fix prompt autofill via `window.__mainEditor.setDocument('markdown', promptText)` + `window.__mainEditor.focus()`.
- `deploy/lobehub/patches/ui/ConnectorsPanel.tsx`:
  - Modern micro-textured card UI, responsive controls layout, ensure "立即连接" button never overflows right boundary.
- `deploy/lobehub/patches/ui/AssistantTopMascot.tsx`:
  - Adjust top margin and breathing bounds to prevent top clipping in `NavHeader`.
- `deploy/lobehub/patches/ui/assistant_status_drawer.py`:
  - Ensure patched UI files sync properly into `lobehub-ui/`.

### Does NOT Own (Strictly Out of Scope)
- No modifications to LCA backend core domain, loop driver, or event protocols.
- No modifications to host ops or external repository assets (`~/everything-library`).
- No modifications to out-of-scope LobeHub features.

## 3. Detailed Component Architecture

### 3.1 Tab 1: 🕒 动态 (Activity Timeline)
- Items grouped by date section (e.g., `今天`, `更早`).
- Item row layout:
  - Left icon: Action icon based on type (green checkmark for completion, browser icon for web navigation, terminal icon for command execution, document icon for file edit).
  - Center: Brief action title, concise action summary, bottom timestamp.
  - Right: Chevron indicator.
- Detail Modal:
  - Triggered by clicking any row.
  - Dual-pane layout: Left column lists recent activity steps; right pane displays human-readable execution details (tool name, command/query, outcome, friendly stage summary).

### 3.2 Tab 2: ⚖️ 批准 (Approvals)
- Display pending and recent approval requests with status tags (`待审批`, `已批准`, `已拒绝`), action target, and timestamp.

### 3.3 Tab 3: ⏰ 即将到来 (Upcoming)
- Reads assistant jobs (e.g. from `/v1/assistants/{id}/jobs` or configured cron/reminders).
- Clean list of upcoming tasks, schedule intervals, and target delivery actions.

### 3.4 Tab 4: 🪪 身份 (Identity Cards Grid)
- 2-column CSS Grid: `display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;`.
- Render cards for `IDENTITY.md`, `SOUL.md`, `USER.md`, `AGENTS.md`, `MEMORY.md`.
- Entire card is clickable (`cursor: pointer`), opening the editor directly.
- Clean presentation: Role icon, filename, tag, preview summary, line/byte count. No raw hash strings.

### 3.5 Tab 5: ⚡ 连接器 (Connectors)
- Redesigned cards with high-contrast brand icons, refined padding, status tags (`🟢 已连接` / `⚪ 未连接`), collapsible tool tags, and comfortably spaced "立即连接" button.

### 3.6 Chat Input Autofill Fix
```ts
if (typeof window !== 'undefined') {
  const mainEditor = (window as any)?.__mainEditor || (window as any)?.__editor;
  if (mainEditor && typeof mainEditor.setDocument === 'function') {
    mainEditor.setDocument('markdown', promptText);
    mainEditor.focus?.();
  } else {
    const editorEl = document.querySelector('.ProseMirror, [contenteditable="true"], textarea') as HTMLElement | null;
    if (editorEl) {
      if ('value' in editorEl) {
        (editorEl as HTMLTextAreaElement).value = promptText;
      } else {
        editorEl.textContent = promptText;
      }
      editorEl.dispatchEvent(new Event('input', { bubbles: true }));
      editorEl.focus();
    }
  }
}
```

### 3.7 Top Mascot Truncation Fix
- Container layout: Shift vertical alignment down by adding `margin-top: 5px;` and adjusting padding so that breath animation `translateY(-2.5px)` remains safely inside `NavHeader`'s 44px viewport.

## 4. Verification Plan
- Patch compilation & reconciliation: `python3 deploy/lobehub/patch_lobehub.py`
- Jest / Vitest / React testing or type-checking where applicable.
- Manual visual inspection via browser if needed.
