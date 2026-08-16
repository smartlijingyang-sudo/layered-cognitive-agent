"""Profile 组合器 —— 委托到 plugin/include/。

保持向后兼容：现有 import 路径 ``lca.layer4_app.profile`` 仍然有效。
实际实现在 ``lca.layer0_infra.plugin.include._profile``。
"""

from __future__ import annotations

from lca.layer0_infra.plugin.include._profile import (
    ProfileError as ProfileError,
)
from lca.layer0_infra.plugin.include._profile import (
    ProfileLoader as ProfileLoader,
)
from lca.layer0_infra.plugin.include._profile import (
    compose_bundles as compose_bundles,
)
from lca.layer0_infra.plugin.include._profile import (
    expand_profile as expand_profile,
)
