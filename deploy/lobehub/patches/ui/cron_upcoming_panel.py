"""Patch: add "即将到来" (upcoming) cron jobs tab to the agent working sidebar (ADR-0268 P5).

Installs ``CronUpcomingPanel.tsx`` into the Conversation components and wires
``useBusinessWorkingSidebarTabs`` to return an ``upcoming`` tab that reads the
``cron.list`` projection (GET ``/v1/assistants/{id}/jobs``). Per ADR-0268 §10
the browser renders only the server-computed ``next_run_local`` string and
never guesses fire times locally.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_COMPONENT_REL = "src/features/Conversation/components/CronUpcomingPanel.tsx"
_TABS_REL = "src/business/client/features/WorkingSidebarTabs.tsx"

_PATCHED_TABS_SOURCE = """\
import type { ReactNode } from 'react';

import CronUpcomingPanel from '@/features/Conversation/components/CronUpcomingPanel';
import { useAgentStore } from '@/store/agent';

export interface BusinessWorkingSidebarTab {
  key: string;
  label: ReactNode;
  pane: ReactNode;
}

export interface BusinessWorkingSidebarTabsContext {
  activeAgentId?: string;
  topicId?: string;
}

export function useBusinessWorkingSidebarTabs(
  context: BusinessWorkingSidebarTabsContext,
): BusinessWorkingSidebarTab[] {
  const { activeAgentId } = context;
  // 与 Conversation Header 的 targetAssistantId 一致：优先 LCA assistant id，否则退回 agent id。
  const lcaAssistantId = useAgentStore((s) =>
    activeAgentId ? (s.agentMap[activeAgentId] as any)?.agencyConfig?.lcaAssistantId : undefined,
  );
  const assistantId = lcaAssistantId || activeAgentId;

  if (!assistantId) {
    return [];
  }

  return [
    {
      key: 'upcoming',
      label: '即将到来',
      pane: <CronUpcomingPanel assistantId={assistantId} />,
    },
  ];
}
"""

meta = PatchMeta(
    name="cron_upcoming_panel",
    description="Add upcoming cron jobs tab to the agent working sidebar (ADR-0268 P5)",
    files=(_COMPONENT_REL, _TABS_REL),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "ADR-0268 §10 requires an upcoming tab that reads the cron.list projection "
        "and never computes fire times in the browser"
    ),
    technical_detail=(
        "Writes CronUpcomingPanel.tsx and patches useBusinessWorkingSidebarTabs to return "
        "an 'upcoming' tab rendering the panel for the active agent"
    ),
    verify_file=_TABS_REL,
    verify_marker="CronUpcomingPanel",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    component_source = _HERE / "CronUpcomingPanel.tsx"
    if not component_source.is_file():
        raise SystemExit(f"[cron_upcoming_panel] missing component source: {component_source}")
    if ctx.write_if_changed(_COMPONENT_REL, component_source.read_text(encoding="utf-8")):
        changed = True

    if ctx.write_if_changed(_TABS_REL, _PATCHED_TABS_SOURCE):
        changed = True

    return changed
