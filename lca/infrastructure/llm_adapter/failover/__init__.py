"""Public exports for ``failover`` (auto-fixed)."""

from lca.infrastructure.llm_adapter.failover.failover import (
    FailoverLLMAdapter,
    LLMFailoverCandidate,
    LLMRetryPolicy,
    RetryingLLMAdapter,
    is_availability_error,
)

__all__ = ['FailoverLLMAdapter', 'LLMFailoverCandidate', 'LLMRetryPolicy', 'RetryingLLMAdapter', 'is_availability_error']
