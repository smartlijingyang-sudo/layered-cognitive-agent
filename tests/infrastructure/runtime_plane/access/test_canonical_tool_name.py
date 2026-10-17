"""RA-145 regression pin: ``canonical_tool_name`` is namespace-aware.

RA-132 was dropped because the twin normalizers mangled namespaced names
(``mcp_corp.do_thing`` → ``mcpCorp.doThing``, matching nothing). The seam
must split the namespace separator *first* and canonicalize only the bare
tool name, never across the separator.
"""

from __future__ import annotations

from lca.infrastructure.runtime_plane.access.approved_tools import canonical_tool_name


def test_namespace_never_mangled() -> None:
    # RA-132's trap: the namespace part must pass through untouched.
    assert canonical_tool_name("mcp_corp.do_thing") == "mcp_corp.doThing"


def test_namespaced_snake_camel_pair_round_trip() -> None:
    snake = canonical_tool_name("mcp_corp.do_thing")
    camel = canonical_tool_name("mcp_corp.doThing")
    assert snake == camel == "mcp_corp.doThing"


def test_dotted_system_names_preserved() -> None:
    assert canonical_tool_name("cron.update") == "cron.update"
    assert canonical_tool_name("cron.remove") == "cron.remove"


def test_bare_names_behave_as_before() -> None:
    assert canonical_tool_name("execute_code") == "executeCode"
    assert canonical_tool_name("executeCode") == "executeCode"
    assert canonical_tool_name("") == ""


def test_canonicalization_is_idempotent() -> None:
    names = ("mcp_corp.do_thing", "mcp_corp.doThing", "execute_code", "cron.update")
    for name in names:
        assert canonical_tool_name(canonical_tool_name(name)) == canonical_tool_name(name)
