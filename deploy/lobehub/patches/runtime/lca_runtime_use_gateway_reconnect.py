"""Patch: rewrite ``useGatewayReconnect`` to source the running
operation from LCA's plain-HTTP ``/lca-api/topics/{topicId}/running-op``
endpoint instead of the legacy LobeHub topic table.

The native hook calls ``useChatStore.reconnectToGatewayOperation(...)``
which proxies through the LobeHub tRPC/gateway stack. LCA's P1
transport owns the running operation table (lca_running_operations),
so the hook fetches it via plain HTTP and forwards the (operationId,
ws_token) pair to the chat store's reconnect handler.

The patch is idempotent: it appends a single ``/* LCA-P1: ... */``
marker at the end of the file on first apply; re-apply is a no-op.
The fetcher body is rewritten by anchor replacement; if the upstream
shape ever drifts the apply() call will raise SystemExit instead of
silently rewriting the wrong block.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_REL = "src/hooks/useGatewayReconnect.ts"
_MARKER = "/* LCA-P1: read from lca_running_operations via plain HTTP */"

# Anchor: the original fetcher block. The patch swaps the SWR fetcher
# body to call the LCA plain-HTTP endpoint instead of the tRPC path.
_OLD_FETCHER = """    async () => {
      if (!runningOperation || !topicId) return;

      await useChatStore.getState().reconnectToGatewayOperation({
        assistantMessageId: runningOperation.assistantMessageId,
        operationId: runningOperation.operationId,
        scope: runningOperation.scope,
        threadId: runningOperation.threadId,
        topicId,
      });
    },"""

_NEW_FETCHER = """    /* LCA-P1: read from lca_running_operations via plain HTTP */
    async () => {
      if (!runningOperation || !topicId) return;

      const lca = await import(
        '@/store/chat/agents/transports/lcaGateway/reconnect'
      );
      const op = await lca.lcaReconnectToGatewayOperation(topicId);
      if (!op) return;

      const token = op.token
        ? op.token
        : await lca.lcaRefreshWsToken(op.operationId, 'lca-local');

      await useChatStore.getState().reconnectToGatewayOperation({
        assistantMessageId: runningOperation.assistantMessageId,
        operationId: op.operationId,
        scope: runningOperation.scope,
        threadId: runningOperation.threadId,
        topicId,
        token,
      });
    },"""


meta = PatchMeta(
    name="lca_runtime_use_gateway_reconnect",
    description=(
        "useGatewayReconnect reads lca_running_operations via plain HTTP."
    ),
    files=(_REL,),
    risk="low",
    category="runtime",
    depends_on=("lca_runtime_agent_gateway",),
    why=(
        "The LobeHub-native useGatewayReconnect reads from "
        "topic.metadata.runningOperation; the LCA equivalent is "
        "`lca_running_operations`. The patch swaps the fetcher for "
        "a plain HTTP GET against /lca-api/topics/{topicId}/running-op."
    ),
    technical_detail=(
        "Marker `/* LCA-P1: read from lca_running_operations via "
        "plain HTTP */` is appended on first apply. The fetcher body "
        "is replaced by anchor replacement against the upstream "
        "shape; re-apply is a no-op once the marker is present."
    ),
    verify_file=_REL,
    verify_marker=_MARKER,
)


def apply(ctx: PatchContext) -> bool:
    text = ctx.read(_REL)
    if _MARKER in text:
        return False  # already applied

    if _OLD_FETCHER not in text:
        raise SystemExit(
            "[lca_runtime_use_gateway_reconnect] fetcher anchor not found; "
            "the upstream shape likely drifted. Update _OLD_FETCHER."
        )

    new_text = text.replace(_OLD_FETCHER, _NEW_FETCHER, 1)
    # Append the marker at end-of-file so a re-apply detects it.
    new_text = new_text.rstrip() + "\n\n" + _MARKER + "\n"
    ctx.write(_REL, new_text)
    return True