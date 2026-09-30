"""Focused tests for codecs extracted into ``routes_assistants.codecs``.

The JSON shaping / source-parsing helpers moved from the monolithic
``routes_assistants.py`` into the ``routes_assistants`` subpackage; these
tests pin their behavior directly so the codec layer has standalone
coverage independent of the (catalog-backed) handler tests.
"""

from __future__ import annotations

import pytest

from lca.plugins.transport.webserver.routes_1.routes_assistants.codecs import (
    _json,
    _parse_skill_source,
    _profile_patch_from_body,
)

_LOCAL_SKILL_PATH = "/tmp/s.md"  # noqa: S108 - test fixture


class TestJsonCodec:
    def test_json_returns_status_and_cors_headers(self) -> None:
        response = _json({"a": 1}, status_code=201)
        assert response.status_code == 201
        assert response.headers.get("access-control-allow-origin") == "*"


class TestProfilePatchFromBody:
    def test_maps_scalar_fields(self) -> None:
        patch = _profile_patch_from_body(
            {
                "profile_name": "新名",
                "profile_description": "新描述",
                "soul_md": "# SOUL",
                "plan_yaml": "goals: []\n",
            }
        )
        assert patch.profile_name == "新名"
        assert patch.profile_description == "新描述"
        assert patch.soul_md == "# SOUL"
        assert patch.plan_yaml == "goals: []\n"
        assert patch.profile_runtime is None

    def test_none_means_untouched_empty_string_passes_through(self) -> None:
        patch = _profile_patch_from_body({"profile_name": None, "profile_description": ""})
        assert patch.profile_name is None
        assert patch.profile_description == ""

    def test_profile_runtime_dict_is_copied(self) -> None:
        runtime = {"model": "gpt-x"}
        patch = _profile_patch_from_body({"profile_runtime": runtime})
        assert patch.profile_runtime == {"model": "gpt-x"}
        assert patch.profile_runtime is not runtime

    def test_unknown_field_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="未知字段"):
            _profile_patch_from_body({"profile_nam": "typo"})

    def test_non_string_field_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="必须为字符串或 null"):
            _profile_patch_from_body({"profile_name": 42})

    def test_non_dict_profile_runtime_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="profile_runtime 必须为 object 或 null"):
            _profile_patch_from_body({"profile_runtime": "gpt-x"})


class TestParseSkillSource:
    def test_dict_url(self) -> None:
        source = _parse_skill_source({"url": "https://example.com/s.md"})
        assert source is not None
        assert source.url == "https://example.com/s.md"

    def test_dict_local_path(self) -> None:
        source = _parse_skill_source({"local_path": _LOCAL_SKILL_PATH})
        assert source is not None
        assert source.local_path == _LOCAL_SKILL_PATH

    def test_bare_http_string_maps_to_url(self) -> None:
        source = _parse_skill_source("https://example.com/s.md")
        assert source is not None
        assert source.url == "https://example.com/s.md"

    def test_bare_path_string_maps_to_local_path(self) -> None:
        source = _parse_skill_source(_LOCAL_SKILL_PATH)
        assert source is not None
        assert source.local_path == _LOCAL_SKILL_PATH

    @pytest.mark.parametrize("raw", [None, "", 42, {"url": "ftp://bad"}, {"unknown": "x"}])
    def test_unsupported_shapes_return_none(self, raw: object) -> None:
        assert _parse_skill_source(raw) is None
