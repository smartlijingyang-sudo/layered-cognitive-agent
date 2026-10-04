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
    description="Drop code-inspector-plugin from vite and turbopack (5678 EADDRINUSE)",
    files=(
        "plugins/vite/sharedRendererConfig.ts",
        "src/libs/next/config/define-config.ts",
    ),
    risk="low",
    category="devux",
    depends_on=(),
    why=(
        "code-inspector-plugin locks TCP 5678 at dev startup. A leaked vite or "
        "turbopack worker holding the port turns the dev run into a 500 page."
    ),
    technical_detail=(
        "Drop codeInspectorPlugin from plugins/vite/sharedRendererConfig.ts and "
        "src/libs/next/config/define-config.ts so dev startup compiles without "
        "the inspector server."
    ),
    verify_file="plugins/vite/sharedRendererConfig.ts",
    verify_marker="LCA: code-inspector disabled",
)

_VITE_NEEDLE = """    isDev &&
      codeInspectorPlugin({
        bundler: 'vite',
        exclude: [/\\.(css|json|html)$/],
        hotKeys: ['altKey', 'ctrlKey'],
      }),"""

_VITE_REPLACEMENT = """    // LCA: code-inspector disabled (5678 EADDRINUSE under dev)
    null,"""

_NEXT_IMPORT_NEEDLE = "import { codeInspectorPlugin } from 'code-inspector-plugin';"
_NEXT_IMPORT_REPLACEMENT = "// LCA: code-inspector disabled (5678 EADDRINUSE under dev)"

_NEXT_RULES_NEEDLE = """        ...(isTest
          ? void 0
          : // Narrow the plugin's `**/*.{jsx,tsx,js,ts,mjs,mts}` rule to JSX
            // files only. The broad glob also matches Turbopack-internal
            // virtual assets like `[turbopack-ecmascript]/worker/browser/createWorker.ts`
            // (injected for `new Worker(new URL(...))`), which the webpack
            // loader shim then tries to read from disk — any page whose module
            // graph pulls in a web worker dies with "Reading source code for
            // parsing failed". The inspector only instruments JSX elements, so
            // jsx/tsx keeps click-to-source fully functional.
            Object.fromEntries(
              Object.entries(
                codeInspectorPlugin({
                  bundler: 'turbopack',
                  hotKeys: ['altKey', 'ctrlKey'],
                }) as Record<string, unknown>,
              ).map(([glob, rule]) => [glob.replace('{jsx,tsx,js,ts,mjs,mts}', '{jsx,tsx}'), rule]),
            )),"""

_NEXT_RULES_REPLACEMENT = "        // LCA: code-inspector disabled (5678 EADDRINUSE under dev)"


def apply(ctx: PatchContext) -> bool:
    applied = False

    # 1. Vite config
    rel_vite = "plugins/vite/sharedRendererConfig.ts"
    if ctx.path(rel_vite).is_file():
        text = ctx.read(rel_vite)
        if _VITE_NEEDLE in text and _VITE_REPLACEMENT not in text:
            ctx.write(rel_vite, text.replace(_VITE_NEEDLE, _VITE_REPLACEMENT, 1))
            applied = True

    # 2. Next.js Turbopack config
    rel_next = "src/libs/next/config/define-config.ts"
    if ctx.path(rel_next).is_file():
        text = ctx.read(rel_next)
        changed = False
        if _NEXT_IMPORT_NEEDLE in text:
            text = text.replace(_NEXT_IMPORT_NEEDLE, _NEXT_IMPORT_REPLACEMENT, 1)
            changed = True
        if _NEXT_RULES_NEEDLE in text:
            text = text.replace(_NEXT_RULES_NEEDLE, _NEXT_RULES_REPLACEMENT, 1)
            changed = True
        if changed:
            ctx.write(rel_next, text)
            applied = True

    return applied


__all__ = ["apply", "meta"]
