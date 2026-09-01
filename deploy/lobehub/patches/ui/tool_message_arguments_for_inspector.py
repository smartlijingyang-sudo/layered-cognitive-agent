"""Patch: forward ``requestArgs`` to ``Inspectors`` in Tool message.

LobeHub's Tool message component renders the per-tool header
(``Inspectors``) inside an Accordion title; the body shows the full
``RunCommandRender`` / ``ExecuteCodeRender`` / etc.  When ``requestArgs``
is not forwarded, the Inspector header chip shows an empty ``runCommand:``
tag instead of the actual command / code, so the user sees the command
"twice" — once blank at the top of the folded card, once filled in the
expanded body.

ADR-0101 followup (2026-09-01): the streaming preview from the backend
lands on this path; without forwarding the args the inspector chip stays
blank for the entire streaming duration.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

_TARGET = "src/features/Conversation/Messages/Tool/Tool/index.tsx"

meta = PatchMeta(
    name="tool_message_arguments_for_inspector",
    description="Forward requestArgs and isArgumentsStreaming to Inspectors in Tool message header",
    files=(_TARGET,),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "Without requestArgs, the header Inspector (RunCommandInspector, "
        "ExecuteCodeInspector, etc.) renders an empty chip — the user only "
        "sees the command / code in the body, which surfaces as a "
        "duplicated or empty header at the top of the folded card. "
        "Forwarding args + streaming state makes the header reflect "
        "partial arguments as they stream, matching the body Render."
    ),
    technical_detail=(
        "Replace the Inspectors usage so it forwards arguments={requestArgs} "
        "and isArgumentsStreaming={loading}. The Inspectors component already "
        "accepts these props and uses them to render the partial preview."
    ),
    verify_file=_TARGET,
    verify_marker="LCA: forward requestArgs to Inspectors",
)


def apply(ctx: PatchContext) -> bool:
    text = ctx.read(_TARGET)

    # Detect already-applied by looking for the LCA marker comment, not the
    # bare prop name (which is also passed to Detail below).
    if "LCA: forward requestArgs to Inspectors" in text:
        return False

    old_block = (
        "          title={\n"
        "            <Inspectors\n"
        "              apiName={apiName}\n"
        "              identifier={identifier}\n"
        "              result={result}\n"
        "              toolCallId={toolCallId}\n"
        "            />\n"
        "          }"
    )
    new_block = (
        "          title={\n"
        "            <Inspectors\n"
        "              apiName={apiName}\n"
        "              // LCA: forward requestArgs to Inspectors so the header chip\n"
        "              // shows the streaming command / code, not an empty tag.\n"
        "              arguments={requestArgs}\n"
        "              identifier={identifier}\n"
        "              isArgumentsStreaming={loading}\n"
        "              result={result}\n"
        "              toolCallId={toolCallId}\n"
        "            />\n"
        "          }"
    )

    if old_block not in text:
        raise SystemExit(
            "[tool_message_arguments_for_inspector] Inspectors title block "
            "not found in current Tool/index.tsx — rebase the patch."
        )

    text = text.replace(old_block, new_block, 1)
    return ctx.write_if_changed(_TARGET, text)
