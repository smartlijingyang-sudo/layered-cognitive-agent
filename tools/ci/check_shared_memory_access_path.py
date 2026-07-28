#!/usr/bin/env python3
"""CI 15.6：cognition/embodiment 实现不得直接 import 共享存储具体类。

允许：
- contracts 中的 SharedMemoryStore Protocol
- layer3_agent 的 TeamOrchestrator / shared_memory 包自身
- layer1 memory 实现绑定 store（MemorySystem 路径，既有 CoALA 模型）

禁止：
- layer1_cognitive/brain/**、body/**（除 memory 协作接口外）直接 import
  TeamSharedMemoryStore / SharedMemoryTool 具体实现
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_IMPORTS = frozenset(
    {
        "lca.layer1_cognitive.memory.team_shared_memory",
        "lca.layer3_agent.shared_memory.shared_memory_tool",
        "lca.layer3_agent.shared_memory",
    }
)
# body/brain 不得直接依赖共享存储具体实现
SCAN_DIRS = [
    ROOT / "lca" / "layer1_cognitive" / "brain",
    ROOT / "lca" / "layer1_cognitive" / "body",
]


def main() -> int:
    violations: list[str] = []
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            rel = path.relative_to(ROOT)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_IMPORTS or any(
                            alias.name.startswith(f + ".") for f in FORBIDDEN_IMPORTS
                        ):
                            violations.append(f"{rel}:{node.lineno} import {alias.name}")
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and (
                        node.module in FORBIDDEN_IMPORTS
                        or any(node.module.startswith(f + ".") for f in FORBIDDEN_IMPORTS)
                    )
                ):
                    violations.append(f"{rel}:{node.lineno} from {node.module} import ...")

    if violations:
        print("FAIL: brain/body 不得直接 import 共享存储具体实现（应经 Tool 注入，ADR-0016）:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: check_shared_memory_access_path")
    return 0


if __name__ == "__main__":
    sys.exit(main())
