"""Static Composio app catalog — mirrors LobeHub ``COMPOSIO_APP_TYPES`` identifiers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComposioAppType:
    app_slug: str
    identifier: str
    label: str
    description: str


COMPOSIO_APP_TYPES: tuple[ComposioAppType, ...] = (
    ComposioAppType("GMAIL", "gmail", "Gmail", "Gmail email service"),
    ComposioAppType(
        "GOOGLECALENDAR",
        "google-calendar",
        "Google Calendar",
        "Google Calendar scheduling",
    ),
    ComposioAppType("AIRTABLE", "airtable", "Airtable", "Airtable database"),
    ComposioAppType("GOOGLESHEETS", "google-sheets", "Google Sheets", "Google Sheets"),
    ComposioAppType("GOOGLEDOCS", "google-docs", "Google Docs", "Google Docs"),
    ComposioAppType("SUPABASE", "supabase", "Supabase", "Supabase backend"),
    ComposioAppType("GOOGLEDRIVE", "google-drive", "Google Drive", "Google Drive storage"),
    ComposioAppType("SLACK", "slack", "Slack", "Slack messaging"),
    ComposioAppType("CONFLUENCE", "confluence", "Confluence", "Confluence wiki"),
    ComposioAppType("JIRA", "jira", "Jira", "Jira issue tracking"),
    ComposioAppType("CLICKUP", "clickup", "ClickUp", "ClickUp project management"),
    ComposioAppType("DROPBOX", "dropbox", "Dropbox", "Dropbox storage"),
    ComposioAppType("FIGMA", "figma", "Figma", "Figma design"),
    ComposioAppType("HUBSPOT", "hubspot", "HubSpot", "HubSpot CRM"),
    ComposioAppType("ONE_DRIVE", "onedrive", "OneDrive", "Microsoft OneDrive"),
    ComposioAppType("OUTLOOK", "outlook-mail", "Outlook Mail", "Outlook Mail"),
    ComposioAppType("SALESFORCE", "salesforce", "Salesforce", "Salesforce CRM"),
    ComposioAppType("WHATSAPP", "whatsapp", "WhatsApp", "WhatsApp Business"),
    ComposioAppType("YOUTUBE", "youtube", "YouTube", "YouTube"),
    ComposioAppType("ZENDESK", "zendesk", "Zendesk", "Zendesk support"),
    ComposioAppType("CALCOM", "cal-com", "Cal.com", "Cal.com scheduling"),
    ComposioAppType("NOTION", "notion", "Notion", "Notion workspace"),
    ComposioAppType("TWITTER", "twitter", "X (Twitter)", "X social"),
    ComposioAppType("GITHUB", "github", "GitHub", "GitHub repositories"),
)

_IDENTIFIERS = {app.identifier for app in COMPOSIO_APP_TYPES}
_BY_IDENTIFIER = {app.identifier: app for app in COMPOSIO_APP_TYPES}
_BY_SLUG = {app.app_slug.upper(): app for app in COMPOSIO_APP_TYPES}


def get_app_by_identifier(identifier: str) -> ComposioAppType | None:
    return _BY_IDENTIFIER.get(identifier)


def is_valid_identifier(identifier: str) -> bool:
    return identifier in _IDENTIFIERS


def resolve_identifier_for_tool_slug(tool_slug: str) -> str | None:
    """Best-effort map a Composio tool slug to a catalog identifier."""
    upper = tool_slug.upper()
    for app in COMPOSIO_APP_TYPES:
        prefix = app.app_slug.upper().replace("_", "")
        normalized_slug = upper.replace("_", "")
        if normalized_slug.startswith(prefix):
            return app.identifier
    return None
