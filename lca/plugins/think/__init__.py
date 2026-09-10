"""think 子图节点插件集中导入入口。

每个节点文件独立可被 profile / tests 直接 load;本文件批量导入 6 个节点,
让 profile resolve 时自动触发所有节点的 setup()(Cordis 双键注册)。

节点清单(per ADR-0218 §3.3,扁平化 6 个 think 节点 plugin):
- shortcut     : try deterministic shortcut before reason
- route        : skill router picks active template; reducer folds state
- reason       : call LLM via Reasoner, emitting spine facts
- classify     : convert LLMResponse to Decision via DecisionClassifier
- gate         : enforce Decision via DecisionGate
- local_gate   : enforce Decision via agent_gates (per-agent guard)

每个 ``setup`` 由 Cordis 装饰器工厂生成(``@plugin``);
``requires`` 真正起作用 — Cordis inject 校验 + runtime.resolve 取实例。
"""

from lca.plugins.think.classify import setup as _setup_classify
from lca.plugins.think.gate import setup as _setup_gate
from lca.plugins.think.local_gate import setup as _setup_local_gate
from lca.plugins.think.reason import setup as _setup_reason
from lca.plugins.think.route import setup as _setup_route
from lca.plugins.think.shortcut import setup as _setup_shortcut

__all__ = [
    "_setup_classify",
    "_setup_gate",
    "_setup_local_gate",
    "_setup_reason",
    "_setup_route",
    "_setup_shortcut",
]
