"""assistant.skill_overlay plugin —— ADR-0187 §7 PR-6。

助理域 skill overlay 唯一实现:

- ``provides=("assistant.skill_overlay",)``;
- ``install`` —— 经 ADR-0048 ``SkillImporter`` 拉取/校验 ⇒ ADR-0067 三闸
  (identity / invariant / experiment) ⇒ ``DRAFT → VERIFIED`` ⇒ 落盘
  ``{home}/skills/<skill_id>/`` ⇒ manifest skills 索引 + ``revision_seq++``
  ⇒ 发 ``assistant.skill.installed`` EP;
- ``list_installed`` —— 扫 ``{home}/skills/``;
- ``activate`` —— 仅接受 VERIFIED/ACTIVE 包;未验证拒收(发
  ``assistant.skill.activated`` EP,不写 Home)。

写路径 ⊆ ``{home}/skills/``;``~/.lca/skills/`` 全局 store 只读不写。
拉取绑定到 Home 内 staging 的 ``DiskSkillPackageStore``,网络行为仍由
0048 机制(host allowlist / 大小上限 / ZIP 安全解压)治理。

包结构(拆分自原单文件 overlay.py):

- ``importing`` —— 0048 拉取 seam(URL / 本地目录);
- ``gating`` —— 0067 三闸 + 落盘/摘要/修订辅助与常量;
- ``receipts`` —— 从磁盘重建安装回执;
- ``overlay`` —— ``_AssistantSkillOverlayImpl`` 实现类;
- ``plugin`` —— Plugin manifest 与 boot。

本 barrel 再导出原单文件模块的全部顶层名字,既有导入方无需改动。
"""

from __future__ import annotations

from lca.plugins.assistant.skill.overlay.gating import (
    _ACTIVATABLE_STATES,
    _SKILLS_DIGEST_PREFIX,
    _STAGING_DIR_NAME,
    _gate_package,
    _mark_local,
    _package_digest,
    _place_package,
    _revision_of,
)
from lca.plugins.assistant.skill.overlay.importing import (
    _default_url_importer,
    _import_local_path,
)
from lca.plugins.assistant.skill.overlay.overlay import (
    AssistantSkillOverlayImpl,
    _AssistantSkillOverlayImpl,
)
from lca.plugins.assistant.skill.overlay.plugin import Config, setup
from lca.plugins.assistant.skill.overlay.receipts import _receipt_from_disk

__all__ = [
    "_ACTIVATABLE_STATES",
    "_SKILLS_DIGEST_PREFIX",
    "_STAGING_DIR_NAME",
    "AssistantSkillOverlayImpl",
    "Config",
    "_AssistantSkillOverlayImpl",
    "_default_url_importer",
    "_gate_package",
    "_import_local_path",
    "_mark_local",
    "_package_digest",
    "_place_package",
    "_receipt_from_disk",
    "_revision_of",
    "setup",
]
