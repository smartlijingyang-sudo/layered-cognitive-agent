"""Gmail SKILL.md and Manifest Generator adhering to Muse 7-layer architecture (INV-03)."""

from __future__ import annotations

from pathlib import Path


def generate_gmail_skill_content() -> str:
    """Generates standard Muse-compliant SKILL.md for Gmail connector."""
    return """---
name: gmail
description: Access Gmail to search, read, draft, and send emails securely.
metadata:
  includeInPrompt: true
---

# Gmail Connector

## Connecting
Always check connection status first before invoking operations:
```bash
gmail status
```

If status returns `not_connected`, copy the `widget` line from the status output verbatim:
```text
[widget:connector_auth?appName=Gmail&intentId=<intentId>&connectionId=<connectionId>]
```
**CRITICAL**: Copy the widget tag exactly as returned — the real URL is sealed in the vault and resolved by the frontend; never substitute a URL for the intentId. Do NOT generate markdown links `[Connect Gmail](url)`. Do NOT invent URLs. Do NOT ask user for credentials.

## Commands

### Quick Commands (Preferred)
- `gmail +read [--account <id>]`: Read latest unread messages.
- `gmail +search <query> [--account <id>]`: Search messages by keywords.
- `gmail +send --to <email> --subject <title> --upload <path> [--account <id>]`: Send an email.

### Multi-Account
- `gmail accounts`: List configured accounts.
- `gmail connect --add-account`: Connect an additional Google account.
- `gmail disconnect --account <id>`: Disconnect specified account.

## Rate Limits & Cost Guide
- Quota: 250 units/minute (enforced mode).
- `+read` / `+search`: 1 unit
- `+send`: 100 units
- `users messages get`: 5 units

### Agent Optimization Rules
1. Execute sequentially; do not issue concurrent parallel bursts.
2. Start with small searches (`--max 5`) before requesting full bodies.
3. If `connector_rate_limited` is returned, back off for the specified `retry_after_seconds`.
"""


def materialize_gmail_skill(target_dir: Path) -> None:
    """Materializes SKILL.md and manifest.yaml into target skill directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_file = target_dir / "SKILL.md"
    skill_file.write_text(generate_gmail_skill_content(), encoding="utf-8")

    manifest_src = Path(__file__).parent / "manifest.yaml"
    manifest_dst = target_dir / "manifest.yaml"
    if manifest_src.is_file():
        manifest_dst.write_text(manifest_src.read_text(encoding="utf-8"), encoding="utf-8")
