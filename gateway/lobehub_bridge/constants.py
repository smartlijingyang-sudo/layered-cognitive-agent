"""LobeHub-aligned limits for file bridge (mirrors builtin-tool-cloud-sandbox)."""

from __future__ import annotations

# Guest mount directory inside Onlyboxes / cloud sandbox.
SANDBOX_UPLOADED_FILES_DIR = "/mnt/data"

# Skip individual files larger than this when ingesting (LobeHub SANDBOX_INIT_MAX_FILE_SIZE).
MAX_INGEST_FILE_BYTES = 100 * 1024 * 1024

# Hard cap on how many uploaded files are ingested per run (LobeHub SANDBOX_INIT_MAX_FILES).
MAX_INGEST_FILES = 50

# Per-file HTTP download timeout (seconds).
FILE_DOWNLOAD_TIMEOUT_S = 120

# Conversation history injected before the latest user turn.
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 6000

# Markers LobeHub context engine injects into user-visible content.
SYSTEM_CONTEXT_BEGIN = "<!-- SYSTEM CONTEXT"
SYSTEM_CONTEXT_END = "<!-- END SYSTEM CONTEXT -->"

# LobeHub agent runtime injects tool/agent XML into user turns — strip for LCA prompt.
AVAILABLE_TOOLS_BEGIN = "<available_tools"
AVAILABLE_TOOLS_END = "</available_tools>"
AGENT_MGMT_BEGIN = "<agent_management_context>"
AGENT_MGMT_END = "</agent_management_context>"

# Agent Signal feedback-analysis envelope (must not enter LCA user task / history).
FEEDBACK_ANALYSIS_BEGIN = "<feedback_analysis_context>"
FEEDBACK_ANALYSIS_END = "</feedback_analysis_context>"
