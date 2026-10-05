"""Patch: discover a cron handoff run this browser did not start (ADR-0268 §6).

A scheduled fire starts a real run on the server and streams it to
``agent_runtime_stream:<run_id>``. The browser files messages by the operationId
it captured when it started a run itself, and ``agent_runtime_init`` is the only
event carrying ``topicId`` with no branch for it in the gateway handler, so a
server-started run is invisible until something resolves the topic to it.

Installs ``useCronHandoffWatch.ts`` and mounts it in ``ConversationArea.tsx``
beside ``useScheduledRunWatch``. It polls
``GET /lca-api/v1/topics/{id}/running-op``, which answers only for a live run,
and seeds ``metadata.runningOperation`` so the existing ``useGatewayReconnect``
attaches. ``useGatewayReconnect`` itself is not modified.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_HOOK_REL = "src/hooks/useCronHandoffWatch.ts"
_AREA_REL = "src/routes/(main)/agent/features/Conversation/ConversationArea.tsx"
_SOURCE_NAME = "useCronHandoffWatch.ts"

_IMPORT_ANCHOR = "import { useScheduledRunWatch } from '@/hooks/useScheduledRunWatch';"
_IMPORT_ADDED = "import { useCronHandoffWatch } from '@/hooks/useCronHandoffWatch';"

_MOUNT_ANCHOR = "  useScheduledRunWatch(context.topicId);\n"
_MOUNT_ADDED = (
    "  useScheduledRunWatch(context.topicId);\n"
    "\n"
    "  // A cron handoff starts a run on the server, so this browser never captured\n"
    "  // its operationId and the reconnect above has nothing to key on. Resolve the\n"
    "  // topic to the live run and seed it, then the same reconnect attaches.\n"
    "  useCronHandoffWatch(context.topicId);\n"
)

meta = PatchMeta(
    name="cron_handoff_watch",
    description="Discover a server-started cron handoff run for the open topic (ADR-0268 §6)",
    files=(_HOOK_REL, _AREA_REL),
    risk="medium",
    category="ui",
    depends_on=(),
    why=(
        "Without it a fired cron job streams to a run_id no browser is subscribed to, "
        "the receipt says delivered and the user sees nothing"
    ),
    technical_detail=(
        "Writes useCronHandoffWatch.ts and mounts it in ConversationArea.tsx next to "
        "useScheduledRunWatch. Polls the liveness-filtered running-op endpoint and "
        "seeds metadata.runningOperation; useGatewayReconnect is unchanged."
    ),
    verify_file=_AREA_REL,
    verify_marker="useCronHandoffWatch",
)


def apply(ctx: PatchContext) -> bool:
    changed = False

    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[cron_handoff_watch] missing hook source: {source}")
    if ctx.write_if_changed(_HOOK_REL, source.read_text(encoding="utf-8")):
        changed = True

    area_text = ctx.read(_AREA_REL)

    if _IMPORT_ADDED not in area_text:
        if _IMPORT_ANCHOR not in area_text:
            raise SystemExit("[cron_handoff_watch] import anchor missing in ConversationArea.tsx")
        area_text = area_text.replace(_IMPORT_ANCHOR, f"{_IMPORT_ADDED}\n{_IMPORT_ANCHOR}", 1)
        changed = True

    if "useCronHandoffWatch(context.topicId)" not in area_text:
        if _MOUNT_ANCHOR not in area_text:
            raise SystemExit("[cron_handoff_watch] mount anchor missing in ConversationArea.tsx")
        area_text = area_text.replace(_MOUNT_ANCHOR, _MOUNT_ADDED, 1)
        changed = True

    if changed:
        ctx.write_if_changed(_AREA_REL, area_text)

    return changed
