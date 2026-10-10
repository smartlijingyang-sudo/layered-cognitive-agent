import pytest
from lca.contracts.mechanisms.seam.seam import consume

def test_consume_returns_provider_when_valid():
    obj = object()
    result = consume("test_seam", obj, "consumer_x")
    assert result is obj

def test_consume_raises_value_error_on_none_provider():
    with pytest.raises(ValueError, match="cannot be consumed with None provider"):
        consume("llm", None, "PromptReasoner")
