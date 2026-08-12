"""Patch: market_fork — Skip Market OIDC on HTTP local dev."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="market_fork",
    description="Skip Market OIDC on HTTP local dev",
    files=(
        "src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
        "src/routes/(main)/community/(detail)/group_agent/features/Sidebar/ActionButton/ForkGroupAndChat.tsx",
    ),
    risk="low",
    category="route",
    depends_on=("dev_auth_files",),
    why="Market fork requires OIDC which needs HTTPS; local dev is HTTP",
    technical_detail="Check isLocalDevNoAuth() and skip OIDC redirect, directly fork to local agent.",
    verify_file="src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
    verify_marker="isLocalDevNoAuth",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    changed = False
    targets = [
        (
            "src/routes/(main)/community/(detail)/agent/features/Sidebar/ActionButton/ForkAndChat.tsx",
            "let forkResult: { agent:",
            [
                (
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';",
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';\n"
                    "import { isLocalDevNoAuth } from '@/layout/AuthProvider/localDevNoAuth';",
                ),
                (
                    "    if (!canCreate || isLoading) return;\n"
                    "    // Check if user is authenticated\n"
                    "    if (!isAuthenticated) {",
                    "    if (!canCreate || isLoading) return;\n"
                    "    // LCA local dev: HTTP lacks secure context for Market OIDC PKCE — fork locally.\n"
                    "    const localDevFork = isLocalDevNoAuth();\n"
                    "    // Check if user is authenticated\n"
                    "    if (!localDevFork && !isAuthenticated) {",
                ),
            ],
            """      let actAs: number | undefined;
      if (activeWorkspaceId) {
        const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
          autoProvision: true,
        });
        actAs = marketAccountId;
      }

      // Step 2: Fork the agent via Market API (single-item batch)
      const [forkOutcome] = await marketApiService.forkAgent([
        {
          actAs,
          identifier: newIdentifier,
          name: title,
          sourceIdentifier: identifier!,
          status: 'published',
          visibility: 'public',
        },
      ]);

      if (!forkOutcome.success) {
        throw new Error(forkOutcome.error?.message || 'Forking failed');
      }

      const forkResult = forkOutcome.data;""",
            """      let forkResult: { agent: { identifier: string; name: string } };
      if (localDevFork) {
        forkResult = { agent: { identifier: newIdentifier, name: title! } };
      } else {
        let actAs: number | undefined;
        if (activeWorkspaceId) {
          const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
            autoProvision: true,
          });
          actAs = marketAccountId;
        }

        // Step 2: Fork the agent via Market API (single-item batch)
        const [forkOutcome] = await marketApiService.forkAgent([
          {
            actAs,
            identifier: newIdentifier,
            name: title,
            sourceIdentifier: identifier!,
            status: 'published',
            visibility: 'public',
          },
        ]);

        if (!forkOutcome.success) {
          throw new Error(forkOutcome.error?.message || 'Forking failed');
        }

        forkResult = forkOutcome.data;
      }""",
        ),
        (
            "src/routes/(main)/community/(detail)/group_agent/features/Sidebar/ActionButton/ForkGroupAndChat.tsx",
            "let forkResult: { group:",
            [
                (
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';",
                    "import { useMarketAuth } from '@/layout/AuthProvider/MarketAuth';\n"
                    "import { isLocalDevNoAuth } from '@/layout/AuthProvider/localDevNoAuth';",
                ),
                (
                    "    if (!canCreate || isLoading) return;\n"
                    "    // Check if user is authenticated\n"
                    "    if (!isAuthenticated) {",
                    "    if (!canCreate || isLoading) return;\n"
                    "    // LCA local dev: HTTP lacks secure context for Market OIDC PKCE — fork locally.\n"
                    "    const localDevFork = isLocalDevNoAuth();\n"
                    "    // Check if user is authenticated\n"
                    "    if (!localDevFork && !isAuthenticated) {",
                ),
            ],
            """      let actAs: number | undefined;
      if (activeWorkspaceId) {
        const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
          autoProvision: true,
        });
        actAs = marketAccountId;
      }

      // Step 2: Fork the group via Market API
      const forkResult = await marketApiService.forkAgentGroup(identifier!, {
        actAs,
        identifier: newIdentifier,
        name: title,
        status: 'published',
        visibility: 'public',
      });""",
            """      let forkResult: { group: { identifier: string } };
      if (localDevFork) {
        forkResult = { group: { identifier: newIdentifier } };
      } else {
        let actAs: number | undefined;
        if (activeWorkspaceId) {
          const { marketAccountId } = await lambdaClient.workspace.ensureMarketOrganization.mutate({
            autoProvision: true,
          });
          actAs = marketAccountId;
        }

        // Step 2: Fork the group via Market API
        forkResult = await marketApiService.forkAgentGroup(identifier!, {
          actAs,
          identifier: newIdentifier,
          name: title,
          status: 'published',
          visibility: 'public',
        });
      }""",
        ),
    ]

    for rel, done_marker, import_anchors, old_fork, new_fork in targets:
        text = ctx.read(rel)
        if done_marker in text or "const localDevFork = isLocalDevNoAuth()" in text:
            continue
        for old_imp, new_imp in import_anchors:
            if old_imp not in text:
                raise SystemExit(f"[market_fork] import anchor not found in {rel}")
            text = text.replace(old_imp, new_imp, 1)
        if old_fork not in text:
            raise SystemExit(f"[market_fork] fork block anchor not found in {rel}")
        text = text.replace(old_fork, new_fork, 1)
        ctx.write(rel, text)
        changed = True

    return changed
