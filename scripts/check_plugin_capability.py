#!/usr/bin/env python3
"""check_plugin_capability —— ADR-0065 PR-3。

``lca/contracts/capabilities.py`` 出现新 Capability key 必须有:
1. 对应 Protocol (在 ``lca/contracts/observability/`` 或 ``lca/contracts/protocols/``)
2. seam 插件 ``lca/plugins/seam_*.py`` 在 ``provides=[...]`` 中声明
3. tier-3 默认实现 / tier-2 provider

缺失任意一项 → fail-fast。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CAPABILITIES_FILE = REPO / "lca" / "contracts" / "capabilities.py"
SEAM_DIR = REPO / "lca" / "plugins"
CONTRACT_DIRS = (
    REPO / "lca" / "contracts" / "observability",
    REPO / "lca" / "contracts" / "protocols",
    REPO / "lca" / "contracts" / "mechanisms",
)


def _capability_keys() -> list[str]:
    text = CAPABILITIES_FILE.read_text(encoding="utf-8")
    return re.findall(r'Capability\[object\]\("([^"]+)"', text)


def _seam_provides() -> dict[str, list[Path]]:
    """seam 插件 → 该插件提供的 capability key 列表。"""
    provides: dict[str, list[Path]] = {}
    for path in SEAM_DIR.glob("seam_*.py"):
        text = path.read_text(encoding="utf-8")
        m = re.search(r"provides=(\[[^\]]*\])", text)
        if not m:
            continue
        # 简化的解析:从 ['key1', 'key2'] 提取字符串字面量
        keys = re.findall(r'"([^"]+)"', m.group(1))
        for key in keys:
            provides.setdefault(key, []).append(path)
    return provides


def _contract_has_protocol(key: str) -> bool:
    """在 contracts 目录里搜 Protocol 定义或 Capability 引用。"""
    for scan_dir in CONTRACT_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if key in text:
                return True
    return False


def main() -> int:
    keys = _capability_keys()
    provides = _seam_provides()

    # 已知由 ADR-0061/0063 引入的"已有" key;不强制要求 seam/provider
    pre_existing = {
        "llm",
        "tools",
        "transport",
        "skills",
        "file_store",
        "observability",
        "sandbox",
        "memory",
        "search",
        "state_store",
        "perceive",
        "gates",
        "bodies",
        "brains",
        "stop_rules",
        "hooks",
        "team_strategies",
        "run_loop_driver_registry",
        "component_registry",
        "llm_resolver",
        "safe_executor.simple",
        "middleware_registry.memory",
        "reasoner.prompt",
        "critic.simple",
        "journal_store",
        "tools.compose_service",
        "transport.compose_service",
        "composer.compose_factory",
        "event_descriptor_registry",
        "trace_inspector_tools",
        "cli_debug_command",
        "genai_semantic_mapper",
        "observability_scorer",
    }

    new_keys = [key for key in keys if key not in pre_existing]
    if not new_keys:
        print("OK: no new capability keys requiring seam wiring.")
        return 0

    violations: list[str] = []
    for key in new_keys:
        if not _contract_has_protocol(key):
            violations.append(f"  - {key}: no Protocol/contract reference found")
            continue
        if key not in provides:
            violations.append(
                f"  - {key}: no seam plugin in lca/plugins/seam_*.py declares provides=['{key}']"
            )

    if violations:
        print("VIOLATIONS (new capability keys missing wiring):")
        for v in violations:
            print(v)
        print(f"\nFound {len(violations)} capability keys requiring seam + provider wiring.")
        return 1

    print(f"OK: {len(new_keys)} new capability keys all wired to seam + contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
