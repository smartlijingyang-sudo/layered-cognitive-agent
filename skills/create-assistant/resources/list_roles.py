#!/usr/bin/env python3
"""List role cards by department. Usage:

  list_roles.py                        # Show all departments with counts
  list_roles.py <department>           # Show roles in a department
  list_roles.py --search <keyword>     # Search roles by name/description
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent / "department-catalog.json"


def main() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    departments = catalog["departments"]
    args = sys.argv[1:]

    if not args:
        print(f"角色档案库：{catalog['total_roles']} 个角色，{len(departments)} 个部门\n")
        for dept_id, info in departments.items():
            print(f"  {info['label']} ({dept_id}): {info['count']} 个角色")
        return

    if args[0] == "--search" and len(args) > 1:
        keyword = " ".join(args[1:]).lower()
        found = []
        for dept_id, info in departments.items():
            for role in info["roles"]:
                if keyword in role["name"].lower() or keyword in role["description"].lower():
                    found.append((dept_id, role))
        if not found:
            print(f"未找到包含 '{keyword}' 的角色")
            return
        print(f"搜索 '{keyword}' 找到 {len(found)} 个角色：\n")
        for dept_id, role in found:
            emoji = role.get("emoji", "")
            desc = role.get("description", "")
            print(f"  {emoji} {role['name']} ({role['role_id']})")
            if desc:
                print(f"    {desc}")
        return

    dept_id = args[0]
    if dept_id not in departments:
        print(f"未知部门: {dept_id}")
        print(f"可用部门: {', '.join(sorted(departments.keys()))}")
        sys.exit(1)

    info = departments[dept_id]
    print(f"{info['label']}（{dept_id}）：{info['count']} 个角色\n")
    for role in info["roles"]:
        emoji = role.get("emoji", "")
        desc = role.get("description", "")
        print(f"  {emoji} {role['name']}")
        print(f"    role_id: {role['role_id']}")
        if desc:
            print(f"    {desc}")
        print()


if __name__ == "__main__":
    main()
