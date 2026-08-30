"""LCA tool name → LobeHub (identifier, apiName). Table only.

Identifiers are LobeHub-native builtin plugin identifiers so the frontend
resolves i18n labels and renderers without additional mapping.

Computer tools split by execution context:
- Cloud sandbox APIs → ``lobe-cloud-sandbox``
- Local machine APIs (``local_`` prefix) → ``lobe-local-system``
"""

from __future__ import annotations

from lca.infrastructure.tools.ask_user import IDENTIFIER as _USER_INTERACTION
from lca.infrastructure.tools.lca_computer.manifest import LOCAL_SYSTEM_ID as _LOCAL_SYSTEM
from lca.infrastructure.tools.lca_sandbox import IDENTIFIER as _CLOUD_SANDBOX
from lca.infrastructure.tools.skills.manifest import _SKILL_STORE_IDENTIFIER as _SKILL_STORE
from lca.infrastructure.tools.skills.manifest import IDENTIFIER as _SKILLS
from lca.infrastructure.tools.web_search import IDENTIFIER as _WEB_BROWSING

# Cloud sandbox computer APIs (non-prefixed tool names).
_CS = _CLOUD_SANDBOX
# Local machine computer APIs (local_-prefixed tool names).
_LS = _LOCAL_SYSTEM

WIRE: dict[str, tuple[str, str]] = {
    # ── cloud sandbox ──
    "executeCode": (_CS, "executeCode"),
    "sandbox_execute": (_CS, "executeCode"),
    "runCommand": (_CS, "runCommand"),
    "listFiles": (_CS, "listFiles"),
    "readFile": (_CS, "readFile"),
    "writeFile": (_CS, "writeFile"),
    "editFile": (_CS, "editFile"),
    "searchFiles": (_CS, "searchFiles"),
    "moveFiles": (_CS, "moveFiles"),
    "grepContent": (_CS, "grepContent"),
    "globFiles": (_CS, "globFiles"),
    "getCommandOutput": (_CS, "getCommandOutput"),
    "killCommand": (_CS, "killCommand"),
    "exportFile": (_CS, "exportFile"),
    # ── local machine ──
    "local_executeCode": (_LS, "executeCode"),
    "local_runCommand": (_LS, "runCommand"),
    "local_listFiles": (_LS, "listFiles"),
    "local_readFile": (_LS, "readFile"),
    "local_writeFile": (_LS, "writeFile"),
    "local_editFile": (_LS, "editFile"),
    "local_searchFiles": (_LS, "searchFiles"),
    "local_moveFiles": (_LS, "moveFiles"),
    "local_grepContent": (_LS, "grepContent"),
    "local_globFiles": (_LS, "globFiles"),
    "local_getCommandOutput": (_LS, "getCommandOutput"),
    "local_killCommand": (_LS, "killCommand"),
    # ── skills ──
    "activate_skill": (_SKILLS, "activateSkill"),
    "run_skill_script": (_SKILLS, "execScript"),
    "read_skill_reference": (_SKILLS, "readReference"),
    "search_skill": (_SKILL_STORE, "searchSkill"),
    "import_skill": (_SKILL_STORE, "importSkill"),
    # ── web search / user interaction ──
    "search": (_WEB_BROWSING, "search"),
    "askUserQuestion": (_USER_INTERACTION, "askUserQuestion"),
}


def resolve(name: str) -> tuple[str, str] | None:
    return WIRE.get(name)
