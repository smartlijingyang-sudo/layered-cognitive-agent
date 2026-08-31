from __future__ import annotations

from dataclasses import dataclass

from lca.infrastructure.observability.adapters.policy import AttributePolicy


def test_credential_named_attributes_are_fully_redacted() -> None:
    prepared = AttributePolicy().prepare(
        {
            "authorization": "Bearer very-secret-value",
            "cookie": "session=private",
            "ordinary": "contains token_abc123456789",
        }
    )

    assert prepared["authorization"] == "[REDACTED]"
    assert prepared["cookie"] == "[REDACTED]"
    assert "[REDACTED]" in prepared["ordinary"]


def test_nested_dicts_stay_json_objects() -> None:
    prepared = AttributePolicy().prepare(
        {
            "payload": {"node": "perceive.main", "semantic_phase": "perceive"},
            "tags": ["a", {"k": 1}],
        }
    )

    assert prepared["payload"] == {"node": "perceive.main", "semantic_phase": "perceive"}
    assert prepared["tags"] == ["a", {"k": 1}]


def test_dataclass_attributes_are_json_objects() -> None:
    @dataclass
    class Sample:
        name: str
        ok: bool

    prepared = AttributePolicy().prepare({"observation": Sample(name="joke.py", ok=True)})
    assert prepared["observation"] == {"name": "joke.py", "ok": True}
