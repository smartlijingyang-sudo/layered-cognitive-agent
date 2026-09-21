# TypeSafe (Jev) 记忆反思前置门禁与弹性降级架构设计

**文档编号**: `DESIGN-2026-09-21-TYPESAFE-MEMORY-PREFILTER`  
**状态**: Approved  
**创建时间**: 2026-09-21  
**影响范围**: `lca/contracts/protocols/memory/`, `lca/infrastructure/memory/`, `lca/nodes/reflect/memory_extract/`

---

## 1. 背景与核心诉求

在 LCA 认知主循环的反射阶段（`phase.reflect`），当轮次结束时需评估当前用户输入是否包含应持久化沉淀的画像、偏好或事实事实。

### 1.1 现状痛点
- 当前 `phase.reflect.memory.extract` 采用静态硬编码代词与动词元组（`_SELF_REFERENCE_TOKENS`，如「我」「我的」「喜欢」「偏好」）作为粗暴的成本门（Cost Gate）。
- **泛化缺陷**：诸如「还是简洁一点好」「别太啰嗦」「按新规范执行」等隐式偏好难以泛化捕获，容易造成记忆沉淀漏报；
- **误报缺陷**：若单纯放宽关键词，又会引发大量向通用大模型发起抽取提炼的不必要开销。

### 1.2 引入 TypeSafe Jev 的价值
TypeSafe 提供的 **Jev (System One)** 模型具有高精度、低延迟（~900ms）、0 生成 Token、类型化概率输出的特性。通过 `Noul` 原语，可以在毫秒级对用户意图是否具有持久记忆价值给出高标定（calibrated）概率判断。

### 1.3 核心约束（用户明确要求）
1. **API 配额与成本控制**：Jev 作为外部托管 API，存在配额有限、网络抖动、Rate Limit (429) 的现实约束。
2. **优雅架构设计模式**：必须采用经典设计模式（策略模式 Strategy + 降级装饰器 Fallback Decorator + 断路器 Circuit Breaker），绝不允许硬编码强依赖。
3. **零阻断与平滑兜底 (Fail-Soft)**：无论发生 429、网络超时、未配 Key 还是开关关闭，必须 0 毫秒静默降级至本地规则，主认知循环 100% 保证不阻断、不卡死。

---

## 2. 架构分层与设计模式

遵循 LCA 领域依赖法则（`contracts → infrastructure → cognition → runtime`）：

```text
               ┌────────────────────────────────────────────────────────┐
               │         lca/contracts/protocols/memory/filter.py        │
               │  - FilterDecision (NamedTuple: should_extract, reason) │
               │  - MemoryPreFilter (Protocol: evaluate)                │
               └───────────────────────────┬────────────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
     ┌───────────────────────────────────┐ ┌───────────────────────────────────┐
     │         RegexMemoryFilter         │ │        TypeSafeMemoryFilter       │
     │  - 纯本地规则 (无外部 I/O)         │ │  - AsyncTypeSafeClient (Jev Noul) │
     │  - 零延迟保底策略                  │ │  - 语义理解与置信度门限判定       │
     └─────────────────┬─────────────────┘ └─────────────────┬─────────────────┘
                       │                                     │
                       └──────────────────┬──────────────────┘
                                          ▼
                      ┌───────────────────────────────────────┐
                      │          FallbackMemoryFilter         │
                      │  - 断路器 (Circuit Breaker)           │
                      │  - 特性开关 (Feature Flag)            │
                      │  - 优雅平滑降级装饰器 (Decorator)    │
                      └───────────────────┬───────────────────┘
                                          │ 依赖注入
                                          ▼
                      ┌───────────────────────────────────────┐
                      │      ReflectMemoryExtractExecutor     │
                      │  - 保持现有节点端口契约 NodeInput/Output │
                      │  - 记录 C13 信息血统 extra["pre_filter"] │
                      └───────────────────────────────────────┘
```

---

## 3. 详细契约与组件设计

### 3.1 契约接口 (`lca/contracts/protocols/memory/filter.py`)

```python
from typing import NamedTuple, Protocol, runtime_checkable

class FilterDecision(NamedTuple):
    """前置过滤判定结果。"""
    should_extract: bool   # 是否需要进入后续 LLM 记忆提炼
    reason: str            # 决策原因说明
    source: str            # 决策源: "typesafe" | "regex" | "circuit_breaker"
    confidence: float      # 判定置信度 (0.0 ~ 1.0)

@runtime_checkable
class MemoryPreFilter(Protocol):
    """前置记忆过滤协议。"""
    async def evaluate(self, text: str) -> FilterDecision:
        ...
```

### 3.2 策略实现 (`lca/infrastructure/memory/pre_filter/`)

1. **`RegexMemoryFilter`**：
   - 提取并维护现有 `_SELF_REFERENCE_TOKENS` 词表。
   - 命中返回 `FilterDecision(should_extract=True, reason="token_matched", source="regex", confidence=0.8)`。
   - 未命中返回 `FilterDecision(should_extract=False, reason="no_token_matched", source="regex", confidence=0.0)`。

2. **`TypeSafeMemoryFilter`**：
   - 使用 `AsyncTypeSafeClient`。
   - 问询 `Noul`：`instructions="该用户陈述是否表达了应当被长期记住的个人身份、角色、习惯偏好或项目指导方针？"`。
   - 判定：`prob >= 0.65` 时判定 `should_extract=True`。

3. **`FallbackMemoryFilter`（熔断降级引擎）**：
   - **状态机**：
     - `CLOSED`：默认正常态，优先调用 `TypeSafeMemoryFilter`；
     - `OPEN`：捕获 429、QuotaExceeded 或超时后进入，熔断静默期（默认 10 分钟）内直接返回 `RegexMemoryFilter`，**不发起任何网络 I/O，耗时 0ms**；
     - `HALF_OPEN`：静默期结束后放行 1 个探测请求，成功则自动闭合恢复。
   - **开关安全**：
     - 若 `LCA_TYPESAFE_ENABLED=false` 或环境变量 `TYPESAFE_API_KEY` 为空，直接旁路调用 `RegexMemoryFilter`。

### 3.3 节点消费 (`ReflectMemoryExtractExecutor`)

- `ReflectMemoryExtractExecutor` 支持构造注入 `pre_filter: MemoryPreFilter | None = None`；
- 执行时调用 `await self._pre_filter.evaluate(task)`；
- 写入 `reflection.extra["pre_filter"]` 追踪元数据，确保决策透明可追溯。

---

## 4. 配置项规范 (SSOT)

| 配置项 | 环境变量 | 默认值 | 作用说明 |
|---|---|---|---|
| 增强总开关 | `LCA_TYPESAFE_ENABLED` | `true` | 全局开关，关闭时 100% 走本地正则 |
| API Key | `TYPESAFE_API_KEY` | *(可选)* | TypeSafe 凭证，未配置时静默走本地正则 |
| 请求超时阈值 | `LCA_TYPESAFE_TIMEOUT_SECONDS` | `1.5` | 超时立即切本地规则，保护主循环延迟 |
| 熔断冷却时间 | `LCA_TYPESAFE_CIRCUIT_MINUTES` | `10` | 发生 429 后短路本地规则的分钟数 |

---

## 5. 异常处理与降级矩阵

| 输入场景 | 外部条件 | 系统行为 | 产出 source | 耗时开销 |
|---|---|---|---|---|
| 普通指令（如“查一下文件”） | 正常调用 | Jev 返回概率 < 0.65，过滤拦截 | `typesafe` | ~900ms |
| 偏好指令（如“别写测试，直接看代码”） | 正常调用 | Jev 识别为偏好 (≥0.65)，放行进入提炼 | `typesafe` | ~900ms + LLM |
| 额度耗尽 / 限流 | HTTP 429 | 告警日志，熔断器置为 OPEN，切本地正则 | `circuit_breaker` | 首次 ~900ms，后续 0ms |
| 服务断网 / DNS 失败 | 异常抛出 | 吞没异常，切本地正则 | `regex` | 极短 (异常捕获耗时) |
| 网络超时 | 超过 1.5s | 终止请求，切本地正则 | `regex` | 1.5s |
| 离线单测环境 | 无网络 / 无 KEY | 跳过网络请求，切本地正则 | `regex` | 0ms |

---

## 6. 测试与验证计划

1. **单元测试 (`tests/reflect/test_memory_pre_filters.py`)**：
   - 规则策略单测：覆盖各种主谓宾、无主偏好句；
   - Jev 策略单测：Mock `AsyncTypeSafeClient` 响应，覆盖概率高/低阈值；
   - 降级与熔断器单测：Mock 429 / Timeout，断言状态迁移 `CLOSED → OPEN → HALF_OPEN → CLOSED`；
   - 环境变量开关单测：开关关闭时断言零网络请求。
2. **集成与回归测试 (`tests/reflect/test_memory_extract_with_prefilter.py`)**：
   - 注入 Mock 后的 `FallbackMemoryFilter` 到 `ReflectMemoryExtractExecutor`，验证 `reflection.extra` 中的指标；
   - 回归运行既有 `tests/reflect/test_memory_extract_distills_identity.py`，保证 100% 通过。
3. **代码卫生与门禁**：
   - `ruff check --fix`
   - `git diff --check`
