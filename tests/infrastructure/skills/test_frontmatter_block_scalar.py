"""A YAML block scalar in SKILL.md frontmatter must survive installation.

``create_assistant_skill`` writes whatever frontmatter the model produced. A
folded ``description: >`` used to be read as the literal indicator, so the
installed manifest carried ``summary: ">"`` and ``search_skill`` could no longer
match the package on its own description (``run_cf67920f2e39``). ``version`` was
dropped on the same path because ``install_package`` only ever took it from the
caller.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.frontmatter.frontmatter import split_frontmatter
from lca.infrastructure.skills.settings.settings import SkillSettings

_FOLDED = """---
name: psychological-counselor
version: 1.0.0
description: >
  整合取向心理咨询技能：以人为中心疗法为基底，
  整合认知行为疗法（CBT）和正念技术。
  支持结构化初诊评估与危机筛查。
references: []
---

# 正文
"""

_LITERAL = """---
name: literal-skill
description: |
  第一行
  第二行
references: []
---

body
"""


def test_folded_block_scalar_becomes_the_description_text() -> None:
    meta, body = split_frontmatter(_FOLDED)

    assert meta["description"] == (
        "整合取向心理咨询技能：以人为中心疗法为基底， "
        "整合认知行为疗法（CBT）和正念技术。 支持结构化初诊评估与危机筛查。"
    )
    assert meta["version"] == "1.0.0"
    assert body == "# 正文"


def test_literal_block_scalar_keeps_its_newlines() -> None:
    meta, _ = split_frontmatter(_LITERAL)

    assert meta["description"] == "第一行\n第二行"


def test_block_scalar_body_is_not_reparsed_as_keys() -> None:
    text = "---\ndescription: >\n  Note: keep me inside the description\nname: n\nreferences: []\n---\nb\n"

    meta, _ = split_frontmatter(text)

    assert meta["description"] == "Note: keep me inside the description"
    assert meta["name"] == "n"
    assert "Note" not in meta


def test_install_persists_folded_summary_and_frontmatter_version(tmp_path: Path) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))

    package = store.install_package(
        skill_id="psychological-counselor",
        skill_md_text=_FOLDED,
        resource_files={},
        source_url="u",
    )

    assert package.summary.startswith("整合取向心理咨询技能")
    assert package.version == "1.0.0"
    assert package.name == "psychological-counselor"


def test_install_keeps_an_explicit_version_over_frontmatter(tmp_path: Path) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))

    package = store.install_package(
        skill_id="psychological-counselor",
        skill_md_text=_FOLDED,
        resource_files={},
        source_url="u",
        version="2.3.4",
    )

    assert package.version == "2.3.4"
