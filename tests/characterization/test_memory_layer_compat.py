"""MemoryLayer enum compatibility tests.

Verifies that str, Enum mixin provides full backward compatibility with
all three downstream usage patterns:
  - layer == "semantic" (direct string comparison)
  - f"layer={layer}" (formatting into logs/prompts)
  - json.dumps(...) (serialization)
"""

from __future__ import annotations

import json

from lca.contracts.enums import SHAREABLE_LAYERS, MemoryLayer


class TestStringEquality:
    """MemoryLayer members compare equal to their string values."""

    def test_working_equals_string(self) -> None:
        assert MemoryLayer.WORKING == "working"

    def test_semantic_equals_string(self) -> None:
        assert MemoryLayer.SEMANTIC == "semantic"

    def test_episodic_equals_string(self) -> None:
        assert MemoryLayer.EPISODIC == "episodic"

    def test_procedural_equals_string(self) -> None:
        assert MemoryLayer.PROCEDURAL == "procedural"

    def test_string_in_shareable_set(self) -> None:
        assert MemoryLayer.SEMANTIC in SHAREABLE_LAYERS
        assert MemoryLayer.PROCEDURAL in SHAREABLE_LAYERS
        assert MemoryLayer.WORKING not in SHAREABLE_LAYERS
        assert MemoryLayer.EPISODIC not in SHAREABLE_LAYERS


class TestStringFormatting:
    """MemoryLayer.value formats into strings using the str value.

    Note: Python 3.12+ changed str(EnumMember) to return 'EnumName.MEMBER'
    instead of the value. Use .value in f-strings and str() calls.
    """

    def test_format_with_value(self) -> None:
        assert f"layer={MemoryLayer.SEMANTIC.value}" == "layer=semantic"

    def test_format_in_list(self) -> None:
        layers = [MemoryLayer.WORKING, MemoryLayer.SEMANTIC]
        text = ", ".join(layer.value for layer in layers)
        assert text == "working, semantic"

    def test_value_not_repr(self) -> None:
        """Ensure .value produces the plain string, not enum repr."""
        formatted = f"[{MemoryLayer.EPISODIC.value}]"
        assert formatted == "[episodic]"


class TestJsonSerialization:
    """MemoryLayer serializes to its string value in JSON.

    json.dumps uses __str__ which returns 'EnumName.MEMBER' in Python 3.12+,
    so callers must use .value for serialization.
    """

    def test_json_dumps_value_produces_string(self) -> None:
        result = json.dumps({"layer": MemoryLayer.SEMANTIC.value})
        assert json.loads(result) == {"layer": "semantic"}

    def test_json_roundtrip_with_value(self) -> None:
        data = {"layer": MemoryLayer.PROCEDURAL.value}
        result = json.loads(json.dumps(data))
        assert result == {"layer": "procedural"}

    def test_json_dumps_list_with_value(self) -> None:
        layers = [MemoryLayer.SEMANTIC.value, MemoryLayer.PROCEDURAL.value]
        result = json.loads(json.dumps(layers))
        assert result == ["semantic", "procedural"]


class TestHashCompatibility:
    """MemoryLayer hashes the same as its string value (dict key compat)."""

    def test_hash_matches_string(self) -> None:
        assert hash(MemoryLayer.SEMANTIC) == hash("semantic")

    def test_usable_as_dict_key(self) -> None:
        d: dict[MemoryLayer, int] = {MemoryLayer.SEMANTIC: 1}
        assert d[MemoryLayer.SEMANTIC] == 1

    def test_construct_from_value(self) -> None:
        assert MemoryLayer("working") is MemoryLayer.WORKING
        assert MemoryLayer("semantic") is MemoryLayer.SEMANTIC
