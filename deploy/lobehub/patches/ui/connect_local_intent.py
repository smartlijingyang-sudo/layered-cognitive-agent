"""Patch: chat intent 「连接本机」→ confirm → auto-install Companion → bind device."""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent

meta = PatchMeta(
    name="connect_local_intent",
    description="Chat intent 连接本机: confirm modal, auto-install Companion, bind device",
    files=(
        "src/features/ConnectLocalIntent/index.tsx",
        "src/features/Conversation/ChatInput/index.tsx",
    ),
    risk="medium",
    category="ui",
    depends_on=(),
    why="Conversational local-machine connection per ADR-0246 / CONV-INSTALL design",
    technical_detail=(
        "Intercept send of 连接本机 inside Conversation ChatInput (store-safe); "
        "confirmModal; preauth; download .cmd; poll /lca-api/api/device/devices; bind."
    ),
    verify_file="src/features/Conversation/ChatInput/index.tsx",
    verify_marker="LCA: connect-local intent",
)


def apply(ctx: PatchContext) -> bool:
    changed = ctx.write_if_changed(
        "src/features/ConnectLocalIntent/index.tsx",
        (_HERE / "ConnectLocalIntent.tsx").read_text(encoding="utf-8"),
    )

    rel = "src/features/Conversation/ChatInput/index.tsx"
    text = ctx.read(rel)
    original = text

    # import
    if "ConnectLocalIntent" not in text:
        # prefer after Conversation store import block
        anchor = "import { ChatInputProvider, DesktopChatInput } from '@/features/ChatInput';\n"
        if anchor not in text:
            raise SystemExit("[connect_local_intent] ChatInputProvider import anchor missing")
        text = text.replace(
            anchor,
            anchor + "import ConnectLocalIntent from '@/features/ConnectLocalIntent';\n",
            1,
        )

    # intercept — rewrite if marker exists, or insert fresh
    good_block = (
        "        const message = getMarkdownContent();\n"
        "        /* LCA: connect-local intent */\n"
        "        if (\n"
        "          typeof window !== 'undefined' &&\n"
        "          /^(连接本机|连接我的电脑|接入本机|连一下本机|connect\\s*(my\\s*)?(local\\s*)?(machine|computer|pc))\\s*[!！.。]?$/i.test(\n"
        "            message.trim(),\n"
        "          )\n"
        "        ) {\n"
        "          window.dispatchEvent(\n"
        "            new CustomEvent('lca:connect-local-intent', {\n"
        "              detail: { message, clearContent },\n"
        "            }),\n"
        "          );\n"
        "          return;\n"
        "        }\n"
    )

    if "/* LCA: connect-local intent */" in text:
        # replace from marker region
        import re as _re

        text = _re.sub(
            r"        const message = getMarkdownContent\(\);\n"
            r"        /\* LCA: connect-local intent \*/\n"
            r"        if \([\s\S]*?\) \{\n"
            r"          window\.dispatchEvent\([\s\S]*?\);\n"
            r"          return;\n"
            r"        }\n",
            lambda _: good_block,
            text,
            count=1,
        )
    else:
        needle = "        const message = getMarkdownContent();\n"
        if needle not in text:
            raise SystemExit("[connect_local_intent] getMarkdownContent anchor missing")
        text = text.replace(needle, good_block, 1)

    # mount inside ChatInput return — near children
    if "<ConnectLocalIntent" not in text:
        # DesktopChatInput children pattern
        mount_anchor = "        {children ?? defaultContent}\n"
        if mount_anchor not in text:
            raise SystemExit("[connect_local_intent] children mount anchor missing")
        text = text.replace(
            mount_anchor,
            "        {children ?? defaultContent}\n"
            "        {/* LCA: connect-local intent host (needs Conversation store) */}\n"
            "        <ConnectLocalIntent />\n",
            1,
        )

    # remove accidental SPAGlobalProvider mount from prior attempt
    spa = "src/layout/SPAGlobalProvider/index.tsx"
    spa_text = ctx.read(spa)
    if "ConnectLocalIntent" in spa_text:
        spa_text = spa_text.replace(
            "import ConnectLocalIntent from '@/features/ConnectLocalIntent';\n", ""
        )
        spa_text = spa_text.replace("\n            <ConnectLocalIntent />", "")
        ctx.write(spa, spa_text)
        changed = True

    if text != original:
        ctx.write(rel, text)
        changed = True
    return changed
