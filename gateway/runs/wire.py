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
    "local_run_command": ("lobe-local-system", "runCommand"),
    "local_list_files": ("lobe-local-system", "listFiles"),
    "local_read_file": ("lobe-local-system", "readFile"),
    "local_write_file": ("lobe-local-system", "writeFile"),
    "local_edit_file": ("lobe-local-system", "editFile"),
    "local_search_files": ("lobe-local-system", "searchFiles"),
    "local_move_files": ("lobe-local-system", "moveFiles"),
    "local_grep_content": ("lobe-local-system", "grepContent"),
    "local_glob_files": ("lobe-local-system", "globFiles"),
    "local_get_command_output": ("lobe-local-system", "getCommandOutput"),
    "local_kill_command": ("lobe-local-system", "killCommand"),
}


def resolve(name: str) -> tuple[str, str] | None:
    return WIRE.get(name)
