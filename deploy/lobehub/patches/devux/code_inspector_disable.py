"""Patch: code_inspector_disable — disable the code-inspector dev plugin.

ADR-0121 PR-9 regression follow-up. The lobehub-ui dev server bundles
``code-inspector-plugin`` (a dev-only Alt+Ctrl "jump to source" helper).
That plugin tries to bind TCP port 5678 at startup. When a previous
lobehub dev session leaked its vite process, port 5678 stayed occupied
and the next dev start crashed with::

    ./src/components/Analytics/Desktop.tsx
    Error: listen EADDRINUSE: address already in use :::5678
    [at @code-inspector/core/dist/index.js]

That failed ``Next.js`` compilation then surfaced as a 500 HTML error
page for every tRPC request — including LCA-driven runs from the UI
(misleadingly logged as ``lambda.ts:128 ... 500``). The fix is purely a
dev-ergonomics patch on lobehub-ui itself: stop importing the plugin.
Production builds already exclude it (``isDev === false`` short-circuit),
so this only affects dev mode.

The change is idempotent: a one-line ``codeInspectorPlugin(...)`` entry
inside ``plugins/vite/sharedRendererConfig.ts`` is replaced by ``null``.
The surrounding plugin array keeps its trailing commas so re-application
is safe.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="code_inspector_disable",
    description="Drop the code-inspector-plugin vite entry (5678 EADDRINUSE)",
    files=("plugins/vite/sharedRendererConfig.ts",),
    risk="low",
    category="devux",
    depends_on=(),
    why=(
        "code-inspector-plugin locks TCP 5678 at dev startup. A leaked vite "
        "process holding the port turns the next dev run into a 500 page."
    ),
    technical_detail=(
        "Replace the ``isDev && codeInspectorPlugin({...})`` entry with "
        "``null`` so dev startup compiles Analytics/Desktop.tsx without "
        "the inspector WebSocket. The Alt+Ctrl click-to-source feature is "
        "lost; everything else (PWA, dev tools) is unchanged."
    ),
    verify_file="plugins/vite/sharedRendererConfig.ts",
    verify_marker="LCA: code-inspector disabled",
)

_INSPECTOR_NEEDLE = """    isDev &&
      codeInspectorPlugin({
        bundler: 'vite',
        exclude: [/\\.(css|json|html)$/],
        hotKeys: ['altKey', 'ctrlKey'],
      }),"""

_INSPECTOR_REPLACEMENT = """    // LCA: code-inspector disabled (5678 EADDRINUSE under dev)
    null,"""


def apply(ctx: PatchContext) -> bool:
    rel = "plugins/vite/sharedRendererConfig.ts"
    text = ctx.read(rel)
    if _INSPECTOR_NEEDLE not in text:
        # Already disabled or upstream refactor; idempotent no-op.
        return False
    if _INSPECTOR_REPLACEMENT in text:
        return False
    ctx.write(rel, text.replace(_INSPECTOR_NEEDLE, _INSPECTOR_REPLACEMENT, 1))
    return True


__all__ = ["apply", "meta"]
