"""LCA tool name → LobeHub (identifier, apiName). Table only."""

from __future__ import annotations

WIRE: dict[str, tuple[str, str]] = {
    "execute_code": ("lobe-cloud-sandbox", "executeCode"),
    "run_command": ("lobe-cloud-sandbox", "runCommand"),
    "list_files": ("lobe-cloud-sandbox", "listFiles"),
    "read_file": ("lobe-cloud-sandbox", "readFile"),
    "write_file": ("lobe-cloud-sandbox", "writeFile"),
    "edit_file": ("lobe-cloud-sandbox", "editFile"),
    "search_files": ("lobe-cloud-sandbox", "searchFiles"),
    "move_files": ("lobe-cloud-sandbox", "moveFiles"),
    "grep_content": ("lobe-cloud-sandbox", "grepContent"),
    "glob_files": ("lobe-cloud-sandbox", "globFiles"),
    "get_command_output": ("lobe-cloud-sandbox", "getCommandOutput"),
    "kill_command": ("lobe-cloud-sandbox", "killCommand"),
    "export_file": ("lobe-cloud-sandbox", "exportFile"),
    "activate_skill": ("lobe-skills", "activateSkill"),
    "run_skill_script": ("lobe-skills", "execScript"),
    "read_skill_reference": ("lobe-skills", "readReference"),
    "search_skill": ("lobe-skill-store", "searchSkill"),
    "import_skill": ("lobe-skill-store", "importSkill"),
    "web_search": ("lobe-web-browsing", "search"),
    "ask_user_question": ("lobe-user-interaction", "askUserQuestion"),
    "write_file_local": ("lobe-local-system", "writeFile"),
}


def resolve(name: str) -> tuple[str, str] | None:
    return WIRE.get(name)
