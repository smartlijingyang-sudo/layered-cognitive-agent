"""LobeHub wire protocol constants.

Defines the naming convention that LobeHub's frontend uses to route tool calls
to the correct plugin and API method: ``identifier____apiName``.
"""

from __future__ import annotations

# ── Wire format ─────────────────────────────────────────────

PLUGIN_SCHEMA_SEPARATOR = "____"

# ── Plugin identifiers ──────────────────────────────────────

LOBE_SKILLS_ID = "lobe-skills"
LOBE_SKILL_STORE_ID = "lobe-skill-store"
LOBE_LOCAL_SYSTEM_ID = "lobe-local-system"
LOBE_WEB_BROWSING_ID = "lobe-web-browsing"
LOBE_USER_INTERACTION_ID = "lobe-user-interaction"
LOBE_CLOUD_SANDBOX_ID = "lobe-cloud-sandbox"

# ── API method names — Skills ───────────────────────────────

SKILLS_API_ACTIVATE = "activateSkill"
SKILLS_API_EXEC = "execScript"
SKILLS_API_READ_REF = "readReference"

# ── API method names — Skill store ──────────────────────────

SKILL_STORE_API_SEARCH = "searchSkill"
SKILL_STORE_API_IMPORT = "importSkill"
SKILL_STORE_API_IMPORT_MARKET = "importFromMarket"

# ── API method names — Web browsing ─────────────────────────

WEB_BROWSING_API_SEARCH = "search"

# ── API method names — User interaction ─────────────────────

USER_INTERACTION_API_ASK = "askUserQuestion"

# ── API method names — Cloud sandbox (computer tools) ───────

API_EXECUTE_CODE = "executeCode"
API_RUN_COMMAND = "runCommand"
API_LIST_FILES = "listFiles"
API_READ_FILE = "readFile"
API_WRITE_FILE = "writeFile"
API_EDIT_FILE = "editFile"
API_SEARCH_FILES = "searchFiles"
API_MOVE_FILES = "moveFiles"
API_GREP_CONTENT = "grepContent"
API_GLOB_FILES = "globFiles"
API_GET_COMMAND_OUTPUT = "getCommandOutput"
API_KILL_COMMAND = "killCommand"
API_EXPORT_FILE = "exportFile"

# ── Limits ──────────────────────────────────────────────────

SKILL_CONTENT_MAX_LEN = 32_000
TOOL_RESULT_PREVIEW_LIMIT = 500
