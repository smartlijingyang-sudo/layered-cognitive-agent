"""One-shot script to convert LCA plugins from manifest+apply to @plugin decorator.

Reads each lca/plugins/X/__init__.py, extracts the manifest and apply() body,
and writes a new lca/plugins/X.py with @plugin decorator.
"""
from __future__ import annotations

import importlib
import os
import re
from pathlib import Path

PLUGINS_DIR = Path("lca/plugins")

# Mapping of plugin name -> (provides_key, file name for the new module)
# Each plugin provides a single service typically. Some provide multiple.
PLUGINS = {
    "agent_service": ("agent_service", "agent_service"),
    "budget_policy": (None, "step_budget"),  # rename to guards/
    "file_store_service": ("file_store", "file_store_service"),
    "gateway_starlette": ("gateway_starlette_router_factory", "gateway_starlette"),
    "llm_provider": (None, "llm_provider"),  # Tier-2 inline
    "llm_service": ("llm", "llm_service"),
    "loop_cognitive": ("agent_loop", "loop_cognitive"),
    "loop_dsh_bridge": ("agent_loop", "loop_dsh_bridge"),
    "loop_intervention_policy": (None, "loop_intervention"),  # rename to guards/
    "loop_replay": ("agent_loop", "loop_replay"),
    "memory_service": ("memory", "memory_service"),
    "observability_service": ("observability", "observability_service"),
    "sandbox_service": ("sandbox", "sandbox_service"),
    "seam_definitions": (None, "seam_definitions"),  # DELETE later
    "search_service": ("search", "search_service"),
    "session_service": ("session_service", "session_service"),
    "skills_service": ("skills", "skills_service"),
    "state_store_service": ("state_store", "state_store_service"),
    "system_prompt": ("system_prompt", "system_prompt"),
    "tools_service": ("tools", "tools_service"),
    "transport_service": ("transport", "transport_service"),
}


def convert_plugin(name: str, provides: str | None, new_name: str) -> str:
    """Generate the new plugin file content."""
    pkg_path = PLUGINS_DIR / name
    src_path = pkg_path / "__init__.py"
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    # Read source
    src = src_path.read_text()

    # Extract body of apply() function (between def apply and next def/class at same indent)
    apply_match = re.search(r"def apply\([^)]*\) -> None:\n((?:.*\n)*?)(?=\n(?:def |class |[a-zA-Z]))", src)
    apply_body = ""
    if apply_match:
        # Re-indent - 4 spaces
        apply_body = apply_match.group(1)
        # remove leading 4 spaces from each line
        apply_body = "\n".join(line[4:] if line.startswith("    ") else line for line in apply_body.split("\n"))
        apply_body = apply_body.rstrip()

    # Extract manifest string
    manifest_match = re.search(r'manifest = PluginManifest\(\s*\n(.*?)\)', src, re.DOTALL)
    if not manifest_match:
        raise ValueError(f"no manifest in {src_path}")

    inject = ""
    if requires_match := re.search(r"requires=\(([^)]+)\)", manifest_match.group(1)):
        requires = requires_match.group(1).strip()
        inject = f"@plugin(name='lca-{new_name.replace("_", "-")}', inject=[{requires}])\n"
    else:
        inject = f"@plugin(name='lca-{new_name.replace("_", "-")}')\n"

    # Build new file
    new_content = f'''"""{name.replace("_", " ").title()} plugin — Tier-1 (cordis @plugin).

Migrated from manifest+apply pattern (compat shim kept working during
migration; this rewrite removes the dependency).
"""
from __future__ import annotations

from cordis import plugin


{inject}async def setup(ctx, config) -> None:
{apply_body}
'''
    return new_content


def main() -> None:
    for name, (provides, new_name) in PLUGINS.items():
        if name in ("seam_definitions", "loop_intervention_policy", "budget_policy"):
            # These are handled separately / rewritten differently
            continue
        try:
            content = convert_plugin(name, provides, new_name)
        except Exception as exc:
            print(f"SKIP {name}: {exc}")
            continue

        # Write new file
        new_path = PLUGINS_DIR / f"{new_name}.py"
        new_path.write_text(content)
        print(f"WROTE {new_path}")

        # Remove old package
        pkg_path = PLUGINS_DIR / name
        os.system(f"git rm -r {pkg_path}")
        print(f"REMOVED {pkg_path}")


if __name__ == "__main__":
    main()
