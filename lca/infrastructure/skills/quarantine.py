"""Skill Quarantine Gate — 技能隔离待审门。

防止 Agent 自动结晶（Auto-crystallize）的技能直接落盘到 active skills/ 造成野蛮生长与 slop 蔓延。
所有未经人工或严审门禁审查的新技能，必须强制写入 skills/quarantine/<slug>/ 目录，待审核批准后晋级。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class SkillQuarantineGate:
    """技能隔离门：管理自动生成技能的隔离、审核与晋级流程。"""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.skills_dir = self.base_dir / "skills"
        self.quarantine_dir = self.skills_dir / "quarantine"

    def quarantine_skill(
        self,
        skill_slug: str,
        skill_md: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """将自动结晶的技能放入隔离区，等待人工或上层评审。

        Returns:
            落盘的隔离目录路径。
        """
        slug = skill_slug.strip()
        target_dir = self.quarantine_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)

        # 写入 SKILL.md
        skill_file = target_dir / "SKILL.md"
        skill_file.write_text(skill_md, encoding="utf-8")

        # 写入元数据
        meta = {
            "slug": slug,
            "status": "quarantined",
            "metadata": metadata or {},
        }
        meta_file = target_dir / "quarantine_meta.json"
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return target_dir

    def list_quarantined_skills(self) -> list[str]:
        """列出当前隔离区内所有待审技能 slug。"""
        if not self.quarantine_dir.is_dir():
            return []
        return [
            p.name
            for p in self.quarantine_dir.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file()
        ]

    def promote_quarantined_skill(self, skill_slug: str) -> Path:
        """审查通过：将技能从隔离区提升至活跃技能目录 skills/<slug>/。

        Returns:
            晋级后的活跃技能目录。
        """
        slug = skill_slug.strip()
        src_dir = self.quarantine_dir / slug
        if not src_dir.is_dir():
            raise FileNotFoundError(f"Quarantined skill not found: {slug}")

        target_dir = self.skills_dir / slug
        if target_dir.exists():
            shutil.rmtree(target_dir)

        # 移动到 active skills
        shutil.move(str(src_dir), str(target_dir))

        # 清除 quarantine 元数据（若存在）
        meta_file = target_dir / "quarantine_meta.json"
        if meta_file.is_file():
            meta_file.unlink()

        return target_dir


__all__ = ["SkillQuarantineGate"]
