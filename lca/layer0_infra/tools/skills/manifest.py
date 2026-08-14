"""Operational skill tools manifest (lobe-skills / lobe-skill-store alignment)."""

from __future__ import annotations

from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta

IDENTIFIER = "lobe-skills"
_SKILL_STORE_IDENTIFIER = "lobe-skill-store"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="searchSkill",
            description=(
                "检索操作技能库（不会做的任务先搜这里）。"
                "优先查 LobeHub Market，否则搜本机已安装 skill。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                },
                "required": ["query"],
            },
            is_idempotent=True,
        ),
        ToolApi(
            name="importSkill",
            description="安装一个 skill 包到本地。",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "skill 名称"},
                    "version": {"type": "string", "description": "版本号"},
                },
                "required": ["name"],
            },
        ),
        ToolApi(
            name="activateSkill",
            description="激活已安装的 skill。",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "skill 名称"},
                },
                "required": ["name"],
            },
        ),
        ToolApi(
            name="readReference",
            description="读取 skill 的参考文档。",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "skill 名称"},
                    "reference": {"type": "string", "description": "参考文档路径"},
                },
                "required": ["name", "reference"],
            },
            is_idempotent=True,
        ),
        ToolApi(
            name="execScript",
            description="在沙箱中执行 skill 脚本。",
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "skill 名称"},
                    "script": {"type": "string", "description": "脚本路径或代码"},
                    "args": {"type": "string", "description": "脚本参数"},
                },
                "required": ["skill_name", "script"],
            },
        ),
    ),
    meta=ToolMeta(
        avatar="🛠️",
        title="Operational Skills",
        description="Search, install, and execute operational skills",
    ),
)
