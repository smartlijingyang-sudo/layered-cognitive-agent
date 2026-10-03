"""Patch: render ConnectorsPanel below settle followup bubbles.

The naming widget appends ``[widget:connectors_panel]`` to the last
followup bubble content when the settle response carries
``show_connectors: true``. This patch teaches ``Assistant/index.tsx`` to
detect that marker, strip it from the displayed text, and mount the
existing ``ConnectorsPanel`` in the bubble's ``messageExtra`` so the card
appears after the three followup bubbles (Muse ordering).
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_ASSISTANT_REL = "src/features/Conversation/Messages/Assistant/index.tsx"

meta = PatchMeta(
    name="settle_connectors_panel",
    description="Render ConnectorsPanel after settle followup bubbles via [widget:connectors_panel] marker",
    files=(_ASSISTANT_REL,),
    risk="low",
    category="ui",
    depends_on=("assistant_naming_widget", "assistant_status_drawer", "connector_auth_card"),
    why="Show the connectors hub card below the post-naming followup bubbles",
    technical_detail=(
        "Patches Assistant/index.tsx to detect the [widget:connectors_panel] marker, strip it "
        "from displayed content, and mount ConnectorsPanel in messageExtra"
    ),
    verify_file=_ASSISTANT_REL,
    verify_marker="ConnectorsPanel",
)


def apply(ctx: PatchContext) -> bool:
    changed = False
    assistant_text = ctx.read(_ASSISTANT_REL)
    original = assistant_text

    # 1. Import the existing ConnectorsPanel component.
    import_anchor = "import ConnectorAuthCard from '../components/ConnectorAuthCard';"
    import_repl = (
        "import ConnectorAuthCard from '../components/ConnectorAuthCard';\n"
        "import ConnectorsPanel from '../../components/ConnectorsPanel';"
    )
    if "import ConnectorsPanel from '../../components/ConnectorsPanel';" not in assistant_text:
        if import_anchor not in assistant_text:
            raise AssertionError("settle_connectors_panel: import anchor not found")
        assistant_text = assistant_text.replace(import_anchor, import_repl, 1)

    # 2. Detect the marker emitted by the naming widget on the last followup bubble.
    detect_anchor = (
        "    const isNamingWidget = Boolean(content && content.includes('[widget:name_picker'));"
    )
    detect_repl = (
        "    const isConnectorsPanelWidget = Boolean(\n"
        "      content && content.includes('[widget:connectors_panel]'),\n"
        "    );\n" + detect_anchor
    )
    if "isConnectorsPanelWidget" not in assistant_text:
        if detect_anchor not in assistant_text:
            raise AssertionError("settle_connectors_panel: detection anchor not found")
        assistant_text = assistant_text.replace(detect_anchor, detect_repl, 1)

    # 3. Strip the marker from the displayed content.
    strip_anchor = (
        "    if (isAvatarPickerWidget && cleanContent) {\n"
        "      cleanContent = cleanContent.replace(/\\[widget:avatar_picker\\?[^\\]]+\\]/g, '').trim();\n"
        "    }"
    )
    strip_repl = (
        strip_anchor
        + "\n"
        + "    if (isConnectorsPanelWidget && cleanContent) {\n"
        + "      cleanContent = cleanContent.replace(/\\[widget:connectors_panel\\]/g, '').trim();\n"
        + "    }"
    )
    if "cleanContent.replace(/\\[widget:connectors_panel\\]/g" not in assistant_text:
        if strip_anchor not in assistant_text:
            raise AssertionError("settle_connectors_panel: strip anchor not found")
        assistant_text = assistant_text.replace(strip_anchor, strip_repl, 1)

    # 4. Mount ConnectorsPanel in messageExtra of the followup bubble.
    mount_anchor = (
        "            {connectorAuthProps && (\n"
        "              <ConnectorAuthCard\n"
        "                appName={connectorAuthProps.appName}\n"
        "                authUrl={connectorAuthProps.authUrl}\n"
        "                connectionId={connectorAuthProps.connectionId}\n"
        "              />\n"
        "            )}"
    )
    mount_repl = (
        mount_anchor
        + "\n"
        + "            {isConnectorsPanelWidget && (\n"
        + "              <ConnectorsPanel assistantId={agentId} />\n"
        + "            )}"
    )
    if "{isConnectorsPanelWidget && (" not in assistant_text:
        if mount_anchor not in assistant_text:
            raise AssertionError("settle_connectors_panel: mount anchor not found")
        assistant_text = assistant_text.replace(mount_anchor, mount_repl, 1)

    if assistant_text != original:
        ctx.write(_ASSISTANT_REL, assistant_text)
        changed = True

    return changed
