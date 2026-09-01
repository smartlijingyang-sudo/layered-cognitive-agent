"""Patch: Make inspector ``shinyText`` legible while the tool is still running.

Tool call rows in the chat (e.g. ``Execute code``, ``Run command``) wrap the
inspector title in ``cx(inspectorTextStyles.root, isLoading &&
shinyTextStyles.shinyText)`` to communicate "this is still executing".  The
upstream ``shinyText`` rule sets the base ``color`` to ``45 %`` opacity and
relies on ``background-clip: text`` + an animated gradient to draw the sheen
across the characters.  Two effects compound on top of one another:

1. Webkit family honors ``-webkit-text-fill-color`` and treats it as
   authoritative; without ``-webkit-text-fill-color: transparent`` the
   foreground stays opaque and the gradient sweep never paints, so the
   shimmer effect simply does not run on Safari / iOS Safari / WebkitGTK.
2. Even where the sweep does paint, a 45 % base colour plus a 1.5 s cycle
   reads as "the title is gone" in practice — a user looking at the
   inspector row during a slow tool (cold-start interpreter, large prompt)
   sees no label until the tool finishes.  That was filed as "执行代码
   那一行标题没有 / 出现得晚".

The patch bumps the base ``color`` to ``70 %``, adds the missing
``-webkit-text-fill-color: transparent``, and re-asserts the
``prefers-reduced-motion`` guard on the shared-tool-ui copy (upstream
already has it on ``src/styles/loading.ts``).  No DOM, no JSX, no SSE — the
fix lives entirely in the CSS rule consumed by every inspector that wraps
its title in ``shinyText``.

The verify marker comment is appended above the rule so re-running
``deploy/lobehub engine verify`` can confirm the patch is in place even
after a fresh ``sync_lobehub_ui.sh`` wipes the vendored tree.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_VERIFY_MARKER = "lca-patch:inspector_shiny_text_legibility"

# Paths inside lobehub-ui/.
_SHARED_STYLES = "packages/shared-tool-ui/src/styles.ts"
_APP_STYLES = "src/styles/loading.ts"

# Anchor is two contiguous lines: the rule opener ``shinyText: css```
# followed by the original ``color: color-mix(... 45%, transparent)`` line
# we are about to rewrite.  Both targets share this verbatim in v2.2.13;
# rewriting just these two lines is enough to (a) keep ``background-clip:
# text`` + ``animation`` semantics untouched, and (b) sneak the
# ``-webkit-text-fill-color`` declaration onto the next line via the
# replacement.
_ANCHOR = (
    "  shinyText: css`\n"
    "    color: color-mix(in srgb, ${cssVar.colorText} 45%, transparent);\n"
)

# shared-tool-ui upstream rule has NO ``prefers-reduced-motion`` guard.  Add
# one as part of the patch so accessibility ties in cleanly with the
# existing rule on the app-side copy.  The replacement is the opening line
# of the css template literal + the rewritten ``color:`` rule +
# ``-webkit-text-fill-color: transparent`` — the rest of the rule (background
# gradient, clip, size, animation, closing backtick) is left untouched in
# the file, and the comment block above carries the lca-patch marker so
# ``verify_marker`` finds it on a fresh sync.
_REPLACEMENT_SHARED = (
    "  /* lca-patch:inspector_shiny_text_legibility\n"
    "     Bumped base color 45% -> 70% so the inspector title stays readable\n"
    "     between shimmer sweeps, added -webkit-text-fill-color: transparent\n"
    "     so Webkit paints the gradient sweep. No DOM/component/SSE changes.\n"
    "     Added prefers-reduced-motion guard to mirror src/styles/loading.ts. */\n"
    "  shinyText: css`\n"
    "    color: color-mix(in srgb, ${cssVar.colorText} 70%, transparent);\n"
    "    -webkit-text-fill-color: transparent;\n"
)

# src/styles/loading.ts upstream rule ALREADY carries a reduced-motion
# guard further down.  Keep that exactly as is and only rewrite the
# visibility color + add the webkit fill.  Same marker comment.
_REPLACEMENT_APP = (
    "  /* lca-patch:inspector_shiny_text_legibility\n"
    "     Bumped base color 45% -> 70% so the inspector title stays readable\n"
    "     between shimmer sweeps, added -webkit-text-fill-color: transparent\n"
    "     so Webkit paints the gradient sweep. The existing\n"
    "     prefers-reduced-motion guard below is preserved verbatim. */\n"
    "  shinyText: css`\n"
    "    color: color-mix(in srgb, ${cssVar.colorText} 70%, transparent);\n"
    "    -webkit-text-fill-color: transparent;\n"
)


meta = PatchMeta(
    name="inspector_shiny_text_legibility",
    description="Inspector shinyText stays readable while tools run (webkited + 70% base color)",
    files=(_SHARED_STYLES, _APP_STYLES),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "工具调用折叠行在执行时整段标题被 shinyText 样式压成 45% 不透明 + 流光扫过，"
        "Webkit 缺 -webkit-text-fill-color 导致流光不渲染，肉眼看不到标题直到结束。"
        "影响 lobe-cloud-sandbox executeCode、Lobe 其它 inspector 共用样式。"
    ),
    technical_detail=(
        "Anchor-replace the shinyText CSS rule in two style modules; "
        "70% base color + -webkit-text-fill-color: transparent + reduced-motion guard."
    ),
    verify_file=_SHARED_STYLES,
    verify_marker=_VERIFY_MARKER,
)


def apply(ctx: PatchContext) -> bool:
    shared = ctx.replace_once(_SHARED_STYLES, _ANCHOR, _REPLACEMENT_SHARED, label="inspector_shiny_text_legibility#shared")
    app = ctx.replace_once(_APP_STYLES, _ANCHOR, _REPLACEMENT_APP, label="inspector_shiny_text_legibility#app")
    changed = False
    if ctx.write_if_changed(_SHARED_STYLES, shared):
        changed = True
    if ctx.write_if_changed(_APP_STYLES, app):
        changed = True
    return changed
