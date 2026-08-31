"""Patch: guard WriteFile Render against undefined args / args.path.

Journal-driven paths can surface tool messages whose ``plugin.arguments``
is undefined or empty after DB reload.  The sibling Intervention and
Streaming components already guard with ``|| ''``; the Render component
was the only one that called ``path.parse(undefined)`` and crashed.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_TARGET = "packages/builtin-tool-local-system/src/client/Render/WriteFile/index.tsx"

meta = PatchMeta(
    name="writefile_undefined_path_guard",
    description="Guard WriteFile Render against undefined args / args.path from DB reload",
    files=(_TARGET,),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "safeParseJSON returns undefined when plugin.arguments is missing or empty "
        "(e.g. after optimisticUpdatePluginState triggers replaceMessages from DB). "
        "path.parse(undefined) throws TypeError, unmounting the whole conversation."
    ),
    technical_detail=(
        "Add early-return Skeleton when args is falsy (existing guard only checks !args, "
        "but after safeParseJSON({}) args is {} and args.path is undefined). "
        "Default path to empty string for path.parse / path.extname / isHtmlFile."
    ),
    verify_file=_TARGET,
    verify_marker="LCA: guard undefined args.path",
)


def apply(ctx: PatchContext) -> bool:
    text = ctx.read(_TARGET)
    if "LCA: guard undefined args.path" in text:
        return False

    # 1. Tighten the early-return: bail out when args OR args.path is missing.
    old_guard = "  if (!args) return <Skeleton active />;"
    new_guard = (
        "  if (!args) return <Skeleton active />;\n"
        "\n"
        "  // LCA: guard undefined args.path — safeParseJSON can return {} when\n"
        "  // plugin.arguments is lost during DB reload, leaving args.path undefined.\n"
        "  const safePath = args.path || '';"
    )
    if old_guard not in text:
        raise SystemExit("[writefile_undefined_path_guard] !args guard not found")
    text = text.replace(old_guard, new_guard, 1)

    # 2. Replace all subsequent args.path references in the render body with safePath.
    text = text.replace(
        "  const { base, dir } = path.parse(args.path);",
        "  const { base, dir } = path.parse(safePath);",
        1,
    )
    text = text.replace(
        "  const ext = path.extname(args.path).slice(1).toLowerCase();",
        "  const ext = path.extname(safePath).slice(1).toLowerCase();",
        1,
    )
    text = text.replace(
        "  const isHtml = isHtmlFile({ path: args.path });",
        "  const isHtml = isHtmlFile({ path: safePath });",
        1,
    )

    # 3. Patch remaining args.path references in the JSX (LocalFile path prop, buildNewFilePatch).
    text = text.replace(
        "patch={buildNewFilePatch(args.path, args.content)}",
        "patch={buildNewFilePatch(safePath, args.content)}",
        1,
    )
    text = text.replace(
        "<LocalFile name={base} path={args.path} />",
        "<LocalFile name={base} path={safePath} />",
        1,
    )

    ctx.write(_TARGET, text)
    return True
