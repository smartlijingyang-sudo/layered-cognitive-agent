"""Patch: route Composio UI connection flows to LCA gateway REST API."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_ACTION = "src/store/tool/slices/composioStore/action.ts"
_CLIENT = "src/libs/composio/lcaComposioClient.ts"

meta = PatchMeta(
    name="lca_composio_api",
    description="Composio connect/refresh/list/delete via LCA :8765 API",
    files=(_CLIENT, _ACTION),
    risk="medium",
    category="runtime",
    depends_on=(),
    why="LCA owns Composio OAuth SSOT; LobeHub lambda router is bypassed",
    technical_detail=(
        "Copies LcaComposioApi.ts and rewires composioStore actions to "
        "fetch /composio/connections on the LCA gateway."
    ),
    verify_file=_ACTION,
    verify_marker="/* LCA: composio via gateway */",
)


def apply(ctx: PatchContext) -> bool:
    changed = False
    client_src = (_HERE / "LcaComposioApi.ts").read_text(encoding="utf-8")
    if not ctx.has_marker(_CLIENT, "LCA-native Composio connection API"):
        ctx.write(_CLIENT, client_src)
        changed = True

    text = ctx.read(_ACTION)
    if "/* LCA: composio via gateway */" in text:
        return changed

    if "import { lambdaClient, toolsClient } from '@/libs/trpc/client';" not in text:
        raise SystemExit("[lca_composio_api] trpc import anchor not found")

    text = text.replace(
        "import { lambdaClient, toolsClient } from '@/libs/trpc/client';",
        "/* LCA: composio via gateway */\n"
        "import { toolsClient } from '@/libs/trpc/client';\n"
        "import { lcaComposioClient } from '@/libs/composio/lcaComposioClient';",
        1,
    )

    text = text.replace(
        "const response = await lambdaClient.composio.createConnection.mutate({\n"
        "        agentId,\n"
        "        appSlug,\n"
        "        identifier,\n"
        "        label,\n"
        "      });",
        "const response = await lcaComposioClient.createConnection({\n"
        "        agentId,\n"
        "        appSlug,\n"
        "        identifier,\n"
        "        label,\n"
        "      });",
        1,
    )

    text = text.replace(
        "const connectionStatus = await lambdaClient.composio.getConnection.query({\n"
        "        connectedAccountId: server.connectedAccountId,\n"
        "      });",
        "const connectionStatus = await lcaComposioClient.getConnection(server.connectedAccountId);",
        1,
    )

    old_refresh_block = """      // ACTIVE — fetch tools
      const toolsResponse = await toolsClient.composio.listActions.query({
        appSlug: server.appSlug,
      });

      const tools = toolsResponse.tools as ComposioTool[];

      this.#set(
        produce((draft: ComposioStoreState) => {
          const serverIndex = draft.composioServers.findIndex((s) => s.identifier === identifier);
          if (serverIndex >= 0) {
            draft.composioServers[serverIndex].tools = tools;
            draft.composioServers[serverIndex].status = ComposioServerStatus.ACTIVE;
            draft.composioServers[serverIndex].redirectUrl = undefined;
            draft.composioServers[serverIndex].errorMessage = undefined;
          }
          draft.loadingComposioServerIds.delete(identifier);
        }),
        false,
        n('refreshComposioConnectionStatus/success'),
      );

      await lambdaClient.composio.updateComposioPlugin.mutate({
        agentId: server.agentId,
        appSlug: server.appSlug,
        authConfigId: server.authConfigId,
        connectedAccountId: server.connectedAccountId,
        identifier,
        label: server.label,
        status: 'ACTIVE',
        tools: tools.map((t) => ({
          description: t.description,
          inputSchema: t.inputSchema,
          name: t.name,
        })),
      });"""

    new_refresh_block = """      const refreshed = await lcaComposioClient.refreshConnection(identifier);
      const tools = (refreshed.tools || []).map((tool) => ({
        description: tool.description || '',
        inputSchema: tool.input_schema || { properties: {}, type: 'object' },
        name: tool.name,
      })) as ComposioTool[];

      this.#set(
        produce((draft: ComposioStoreState) => {
          const serverIndex = draft.composioServers.findIndex((s) => s.identifier === identifier);
          if (serverIndex >= 0) {
            draft.composioServers[serverIndex].tools = tools;
            draft.composioServers[serverIndex].status = ComposioServerStatus.ACTIVE;
            draft.composioServers[serverIndex].redirectUrl = undefined;
            draft.composioServers[serverIndex].errorMessage = undefined;
          }
          draft.loadingComposioServerIds.delete(identifier);
        }),
        false,
        n('refreshComposioConnectionStatus/success'),
      );"""

    if old_refresh_block not in text:
        raise SystemExit("[lca_composio_api] refresh block anchor not found")
    text = text.replace(old_refresh_block, new_refresh_block, 1)

    text = text.replace(
        "await lambdaClient.composio.deleteConnection.mutate({\n"
        "        connectedAccountId: existing.connectedAccountId,\n"
        "        identifier,\n"
        "      });",
        "await lcaComposioClient.deleteConnection(identifier);",
        1,
    )

    text = text.replace(
        "await lambdaClient.composio.deleteConnection.mutate({\n"
        "          connectedAccountId: server.connectedAccountId,\n"
        "          identifier,\n"
        "        });",
        "await lcaComposioClient.deleteConnection(identifier);",
        1,
    )

    text = text.replace(
        "const composioPlugins = await lambdaClient.composio.getComposioPlugins.query();",
        "const composioPlugins = await lcaComposioClient.listPlugins();",
        1,
    )

    ctx.write(_ACTION, text)
    return True
