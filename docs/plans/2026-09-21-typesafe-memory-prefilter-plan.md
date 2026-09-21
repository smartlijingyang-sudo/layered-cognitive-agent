# TypeSafe Jev Memory PreFilter Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 为 LCA 的记忆反思抽取阶段 (`phase.reflect.memory.extract`) 接入 TypeSafe (Jev System One)，通过策略模式与熔断降级链实现高泛化记忆前置判定，并在 API 额度不足、超时或关闭时平滑秒级降级至本地规则。

**Architecture:** 在 `contracts` 层定义 `MemoryPreFilter` 协议与不可变 `FilterDecision` DTO；在 `infrastructure` 层实现 `RegexMemoryFilter`、`TypeSafeMemoryFilter` 与具备断路器（Circuit Breaker）的 `FallbackMemoryFilter`；在 `ReflectMemoryExtractExecutor` 中注入调用并记录透明审计追踪元数据。

**Tech Stack:** Python 3.11+, Pydantic/NamedTuple, `typesafe-sdk`, `pytest`, `pytest-asyncio`.

---

### Task 1: 契约层与判定结果 DTO

**Files:**
- Create: `lca/contracts/protocols/memory/filter.py`
- Modify: `lca/contracts/protocols/memory/__init__.py` (if exists or create)
- Test: `tests/reflect/test_memory_pre_filter_contract.py`

**Step 1: Write failing test**

```python
# tests/reflect/test_memory_pre_filter_contract.py
from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter

def test_filter_decision_structure():
    decision = FilterDecision(
        should_extract=True,
        reason="test",
        source="typesafe",
        confidence=0.95,
    )
    assert decision.should_extract is True
    assert decision.reason == "test"
    assert decision.source == "typesafe"
    assert decision.confidence == 0.95

def test_protocol_runtime_checkable():
    class DummyFilter:
        async def evaluate(self, text: str) -> FilterDecision:
            return FilterDecision(True, "dummy", "dummy", 1.0)

    assert isinstance(DummyFilter(), MemoryPreFilter)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reflect/test_memory_pre_filter_contract.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'lca.contracts.protocols.memory.filter'`

**Step 3: Implement contract**

```python
# lca/contracts/protocols/memory/filter.py
from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable

class FilterDecision(NamedTuple):
    """前置记忆过滤判定结果。"""
    should_extract: bool
    reason: str
    source: str
    confidence: float

@runtime_checkable
class MemoryPreFilter(Protocol):
    """前置记忆过滤协议。"""
    async def evaluate(self, text: str) -> FilterDecision:
        """评估文本是否包含值得提炼沉淀的长期记忆事实。"""
        ...
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/reflect/test_memory_pre_filter_contract.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/contracts/protocols/memory/filter.py tests/reflect/test_memory_pre_filter_contract.py
git commit -m "feat(contracts): add MemoryPreFilter protocol and FilterDecision DTO"
```

---

### Task 2: 本地规则策略 (RegexMemoryFilter)

**Files:**
- Create: `lca/infrastructure/memory/pre_filter/regex_filter.py`
- Test: `tests/reflect/test_regex_memory_filter.py`

**Step 1: Write failing test**

```python
# tests/reflect/test_regex_memory_filter.py
import pytest
from lca.infrastructure.memory.pre_filter.regex_filter import RegexMemoryFilter

@pytest.mark.asyncio
async def test_regex_filter_matches_explicit_tokens():
    filter_ = RegexMemoryFilter()
    hit = await filter_.evaluate("我是软件架构师")
    assert hit.should_extract is True
    assert hit.source == "regex"
    assert hit.confidence == 0.8

    miss = await filter_.evaluate("今天天气真不错，执行编译命令")
    assert miss.should_extract is False
    assert miss.source == "regex"
    assert miss.confidence == 0.0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reflect/test_regex_memory_filter.py -v`  
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Implement RegexMemoryFilter**

```python
# lca/infrastructure/memory/pre_filter/regex_filter.py
from __future__ import annotations

from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter
from lca.nodes.reflect.memory_extract.memory_extract import _SELF_REFERENCE_TOKENS

class RegexMemoryFilter(MemoryPreFilter):
    """基于硬编码代词/动词元组的保底本地过滤策略。"""

    def __init__(self, tokens: tuple[str, ...] = _SELF_REFERENCE_TOKENS) -> None:
        self._tokens = tokens

    async def evaluate(self, text: str) -> FilterDecision:
        lowered = text.lower()
        matched = [token for token in self._tokens if token in text or token in lowered]
        if matched:
            return FilterDecision(
                should_extract=True,
                reason=f"matched_tokens:{','.join(matched[:3])}",
                source="regex",
                confidence=0.8,
            )
        return FilterDecision(
            should_extract=False,
            reason="no_tokens_matched",
            source="regex",
            confidence=0.0,
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/reflect/test_regex_memory_filter.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/pre_filter/regex_filter.py tests/reflect/test_regex_memory_filter.py
git commit -m "feat(memory): implement RegexMemoryFilter fallback strategy"
```

---

### Task 3: TypeSafe Jev 语义策略 (TypeSafeMemoryFilter)

**Files:**
- Create: `lca/infrastructure/memory/pre_filter/typesafe_filter.py`
- Test: `tests/reflect/test_typesafe_memory_filter.py`

**Step 1: Write failing test**

```python
# tests/reflect/test_typesafe_memory_filter.py
from unittest.mock import AsyncMock, patch
import pytest
from lca.infrastructure.memory.pre_filter.typesafe_filter import TypeSafeMemoryFilter

@pytest.mark.asyncio
async def test_typesafe_filter_high_prob():
    mock_resp = AsyncMock()
    mock_resp.nouls = {"should_memorize": AsyncMock(noul=0.85)}
    
    with patch("typesafe_sdk.AsyncTypeSafeClient.system_one", return_value=mock_resp):
        filter_ = TypeSafeMemoryFilter(api_key="test_key", threshold=0.65)
        decision = await filter_.evaluate("以后关于架构的讨论都使用精简风格")
        assert decision.should_extract is True
        assert decision.source == "typesafe"
        assert decision.confidence == 0.85
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reflect/test_typesafe_memory_filter.py -v`  
Expected: FAIL

**Step 3: Implement TypeSafeMemoryFilter**

```python
# lca/infrastructure/memory/pre_filter/typesafe_filter.py
from __future__ import annotations

import os
from typesafe_sdk import AsyncTypeSafeClient, Noul
from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter

class TypeSafeMemoryFilter(MemoryPreFilter):
    """基于 TypeSafe (Jev) System One Noul 原语的语义记忆门禁。"""

    def __init__(
        self,
        api_key: str | None = None,
        threshold: float = 0.65,
        timeout_seconds: float = 1.5,
    ) -> None:
        self._api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        self._threshold = threshold
        self._timeout_seconds = timeout_seconds

    async def evaluate(self, text: str) -> FilterDecision:
        if not self._api_key:
            raise ValueError("TYPESAFE_API_KEY is not configured")

        async with AsyncTypeSafeClient(api_key=self._api_key) as client:
            res = await client.system_one(
                state={"statement": text},
                questions={
                    "should_memorize": Noul(
                        instructions="该用户陈述是否表达了应当被长期记住的个人身份、角色、习惯偏好或项目指导方针？"
                    )
                },
            )
            prob = float(res.nouls["should_memorize"].noul)
            should = prob >= self._threshold
            return FilterDecision(
                should_extract=should,
                reason=f"noul_prob:{prob:.2f}",
                source="typesafe",
                confidence=prob,
            )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/reflect/test_typesafe_memory_filter.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/pre_filter/typesafe_filter.py tests/reflect/test_typesafe_memory_filter.py
git commit -m "feat(memory): implement TypeSafeMemoryFilter with Jev Noul primitive"
```

---

### Task 4: 熔断降级链与开关 (FallbackMemoryFilter)

**Files:**
- Create: `lca/infrastructure/memory/pre_filter/fallback_filter.py`
- Test: `tests/reflect/test_fallback_memory_filter.py`

**Step 1: Write failing test**

```python
# tests/reflect/test_fallback_memory_filter.py
import pytest
from unittest.mock import AsyncMock
from lca.contracts.protocols.memory.filter import FilterDecision
from lca.infrastructure.memory.pre_filter.fallback_filter import FallbackMemoryFilter

@pytest.mark.asyncio
async def test_fallback_on_typesafe_error():
    primary = AsyncMock()
    primary.evaluate.side_effect = RuntimeError("429 Too Many Requests: Quota Exceeded")
    fallback = AsyncMock()
    fallback.evaluate.return_value = FilterDecision(True, "fallback_regex", "regex", 0.8)

    filter_ = FallbackMemoryFilter(primary=primary, fallback=fallback, circuit_breaker_seconds=600)
    decision = await filter_.evaluate("我是测试")
    
    assert decision.source == "regex"
    assert "fallback" in decision.reason
    assert filter_.is_circuit_open() is True

    # 第二次直接走熔断保底，不调 primary
    await filter_.evaluate("第二次测试")
    assert primary.evaluate.call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reflect/test_fallback_memory_filter.py -v`  
Expected: FAIL

**Step 3: Implement FallbackMemoryFilter**

```python
# lca/infrastructure/memory/pre_filter/fallback_filter.py
from __future__ import annotations

import logging
import os
import time
from typing import Any
from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter
from lca.infrastructure.memory.pre_filter.regex_filter import RegexMemoryFilter
from lca.infrastructure.memory.pre_filter.typesafe_filter import TypeSafeMemoryFilter

logger = logging.getLogger(__name__)

class FallbackMemoryFilter(MemoryPreFilter):
    """带断路器 (Circuit Breaker) 与优雅降级的复合记忆门禁。"""

    def __init__(
        self,
        primary: MemoryPreFilter | None = None,
        fallback: MemoryPreFilter | None = None,
        enabled: bool | None = None,
        circuit_breaker_seconds: float = 600.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback or RegexMemoryFilter()
        self._enabled = (
            enabled
            if enabled is not None
            else os.getenv("LCA_TYPESAFE_ENABLED", "true").lower() in ("true", "1", "yes")
        )
        self._circuit_breaker_seconds = circuit_breaker_seconds
        self._circuit_open_until: float = 0.0

    def is_circuit_open(self) -> bool:
        return time.time() < self._circuit_open_until

    async def evaluate(self, text: str) -> FilterDecision:
        if not self._enabled:
            return await self._fallback.evaluate(text)

        if self.is_circuit_open():
            res = await self._fallback.evaluate(text)
            return FilterDecision(
                should_extract=res.should_extract,
                reason=f"circuit_open_fallback:{res.reason}",
                source="circuit_breaker",
                confidence=res.confidence,
            )

        if self._primary is None:
            api_key = os.getenv("TYPESAFE_API_KEY")
            if not api_key:
                return await self._fallback.evaluate(text)
            self._primary = TypeSafeMemoryFilter(api_key=api_key)

        try:
            return await self._primary.evaluate(text)
        except Exception as exc:
            logger.warning(
                "TypeSafeMemoryFilter 调用失败或超额，启动熔断降级: %s", exc
            )
            self._circuit_open_until = time.time() + self._circuit_breaker_seconds
            res = await self._fallback.evaluate(text)
            return FilterDecision(
                should_extract=res.should_extract,
                reason=f"tripped_circuit_fallback:{res.reason}",
                source="circuit_breaker",
                confidence=res.confidence,
            )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/reflect/test_fallback_memory_filter.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/infrastructure/memory/pre_filter/fallback_filter.py tests/reflect/test_fallback_memory_filter.py
git commit -m "feat(memory): implement FallbackMemoryFilter with circuit breaker"
```

---

### Task 5: 节点集成与运行时装配 (ReflectMemoryExtractExecutor)

**Files:**
- Modify: `lca/nodes/reflect/memory_extract/memory_extract.py:153-245`
- Test: `tests/reflect/test_memory_extract_with_prefilter.py`
- Regression Test: `tests/reflect/test_memory_extract_distills_identity.py`

**Step 1: Write failing test**

```python
# tests/reflect/test_memory_extract_with_prefilter.py
import pytest
from unittest.mock import AsyncMock
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext, NodeInput
from lca.contracts.protocols.memory.filter import FilterDecision
from lca.nodes.reflect.memory_extract.memory_extract import ReflectMemoryExtractExecutor

@pytest.mark.asyncio
async def test_executor_records_prefilter_evidence():
    mock_filter = AsyncMock()
    mock_filter.evaluate.return_value = FilterDecision(
        should_extract=False, reason="blocked", source="typesafe", confidence=0.1
    )
    executor = ReflectMemoryExtractExecutor(pre_filter=mock_filter)
    
    reflection = type("Reflection", (), {"extra": {}})()
    state = type("State", (), {"task": "测试普通陈述"})()
    ctx = NodeContext(runtime={"agent_state": state, "adapter": AsyncMock()})
    inp = NodeInput(port_values={"reflection": reflection})
    
    out = await executor.node_execute(ctx, inp)
    # 阻断时不进入抽取，直接 passthrough
    assert "memory_candidates" not in reflection.extra
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/reflect/test_memory_extract_with_prefilter.py -v`  
Expected: FAIL

**Step 3: Update ReflectMemoryExtractExecutor**

Modify `lca/nodes/reflect/memory_extract/memory_extract.py`:
- 引入 `MemoryPreFilter` 与默认单例 `FallbackMemoryFilter`；
- 在 `ReflectMemoryExtractExecutor` 的 `__init__` 中接收 `pre_filter: MemoryPreFilter | None = None`；
- 在 `node_execute` 中调用 `decision = await self._pre_filter.evaluate(task)`；
- 若 `not decision.should_extract` 则透传退出；
- 记录 `extra["pre_filter"] = decision._asdict()`。

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/reflect/test_memory_extract_with_prefilter.py tests/reflect/test_memory_extract_distills_identity.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add lca/nodes/reflect/memory_extract/memory_extract.py tests/reflect/test_memory_extract_with_prefilter.py
git commit -m "feat(reflect): integrate MemoryPreFilter into ReflectMemoryExtractExecutor"
```

---

### Task 6: 全链路回归与卫生检查

**Files:**
- All touched files

**Step 1: Run comprehensive tests**

```bash
uv run pytest tests/reflect/ -v
```

**Step 2: Run linter and formatting**

```bash
uv run ruff check lca/contracts/protocols/memory/ lca/infrastructure/memory/ lca/nodes/reflect/ tests/reflect/ --fix
uv run ruff format lca/contracts/protocols/memory/ lca/infrastructure/memory/ lca/nodes/reflect/ tests/reflect/
git diff --check
```

**Step 3: Live end-to-end sanity check**

运行一次带有 `TYPESAFE_API_KEY` 的活体验证脚本，确认 Jev 真实命中与回退：
```bash
uv run python -c "
import asyncio
from lca.infrastructure.memory.pre_filter.fallback_filter import FallbackMemoryFilter

async def test():
    f = FallbackMemoryFilter()
    r = await f.evaluate('以后关于架构的回答都请精简要点')
    print('真实调用评估结果:', r)

asyncio.run(test())
"
```

**Step 4: Commit**

```bash
git commit --allow-empty -m "chore(reflect): complete TypeSafe Jev memory prefilter integration"
```
