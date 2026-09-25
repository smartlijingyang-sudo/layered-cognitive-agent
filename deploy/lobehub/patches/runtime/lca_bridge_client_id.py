"""Patch: lca_bridge_client_id — accept ``clientId`` in ``agent.createAgent``.

ADR-0252 D8：bridge 幂等注册需要 ``clientId="lca-<assistant_id>"`` 配合
``agents.client_id_user_id_unique``。``CreateAgentSchema`` 不含 ``clientId``，
在路由层加可选字段并透传给 ``agentModel.create``。
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="lca_bridge_client_id",
    description="Accept clientId in agent.createAgent for idempotent bridge registration",
    files=("apps/server/src/routers/lambda/agent.ts",),
    risk="medium",
    category="runtime",
    depends_on=(),
    why="ADR-0252 D8: idempotent LobeHub agent row creation via client_id_user_id_unique",
    technical_detail=(
        "Adds optional clientId to the createAgent Zod input and forwards it "
        "into ctx.agentModel.create."
    ),
    verify_file="apps/server/src/routers/lambda/agent.ts",
    verify_marker="LCA clientId",
)


def apply(ctx: PatchContext) -> bool:
    rel = "apps/server/src/routers/lambda/agent.ts"
    if ctx.has_marker(rel, "LCA clientId"):
        return False

    text = ctx.read(rel)

    anchor_input = """    .input(
      z.object({
        config: CreateAgentSchema.optional(),
        groupId: z.string().optional(),
        visibility: z.enum(['private', 'public']).optional(),
      }),
    )"""
    repl_input = """    .input(
      z.object({
        config: CreateAgentSchema.optional(),
        groupId: z.string().optional(),
        visibility: z.enum(['private', 'public']).optional(),
        // LCA clientId: idempotent bridge registration (ADR-0252 D8).
        clientId: z.string().optional(),
      }),
    )"""
    if anchor_input not in text:
        raise AssertionError("lca_bridge_client_id: input anchor not found")
    text = text.replace(anchor_input, repl_input, 1)

    anchor_create = """        plugins: input.config?.plugins as unknown as string[] | undefined,
        sessionGroupId: input.groupId,"""
    repl_create = """        plugins: input.config?.plugins as unknown as string[] | undefined,
        sessionGroupId: input.groupId,
        // LCA clientId: forwarded for idempotency (ADR-0252 D8).
        ...(input.clientId ? { clientId: input.clientId } : {}),"""
    if anchor_create not in text:
        raise AssertionError("lca_bridge_client_id: create anchor not found")
    text = text.replace(anchor_create, repl_create, 1)

    ctx.write(rel, text)
    return True