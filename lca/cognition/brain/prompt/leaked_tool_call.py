"""Classify one completion's text channel: prose, tool call, or wire failure.

LobeHub only executes ``assistant.tool_calls``, so a tool call the model writes
as visible text has to be read back off the text channel. Qwen-family providers
serialize one three ways: a bracketed ``[Tool call: name]`` header with a JSON
body, a function tag with a JSON body, and an invoke/parameter tag pair. They
also sometimes emit only a *fragment* of one — a trailing closing tag with no
opening tag, after the provider already stopped.

Those are three different facts and the caller must be able to tell them apart:
prose is an answer, a decoded call is work to dispatch, and a fragment is a wire
failure. Collapsing the third into the first is what delivers protocol markup to
the user as a final answer and stops the loop on ``StopReason.CONTINUE``, so a
fragment is reported in ``TextChannel.undecodable`` and never in ``prose``.

Markers inside a fenced code block are not protocol: an agent writing about a
tool-call grammar has to be able to quote one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.conversation.llm import NativeToolCall

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_TOOL_NAME = re.compile(r"^[A-Za-z_][\w]{0,63}$")
# Four-or-more dots, or a unicode ellipsis, is a model cutting a value off.
# Three dots stay legal so a Python ``...`` in a real argument still parses.
_TRUNCATED_VALUE = re.compile(r"\.{4,}|…")

_BRACKET_CALL = re.compile(r"\[Tool call:\s*([A-Za-z_][\w]*)\]\s*(\{.*\})\s*\Z", re.DOTALL)
_FUNCTION_CALL = re.compile(r"<function=\s*([A-Za-z_][\w]*)\s*>(.*?)</function\s*>", re.DOTALL)
_INVOKE_CALL = re.compile(r"<invoke\s+name=\"([^\"]+)\"\s*>(.*?)</invoke\s*>", re.DOTALL)
_TOOL_TAG_CALL = re.compile(r"<tool\s+name=\"([^\"]+)\"\s*>(.*?)</tool\s*>", re.DOTALL)
_TOOL_CALL_JSON = re.compile(r"<tool_call\s*>(.*?)</tool_call\s*>", re.DOTALL)
_DELEGATE_CALL = re.compile(
    r"<delegate_to(?:_role)?\s*>(.*?)</delegate_to(?:_role)?\s*>", re.DOTALL
)
_QWEN_SPECIAL_CALL = re.compile(
    r"<\|tool_call_begin\|>(?:function\s*)?(?:<\|tool_call_name\|>)?([A-Za-z_][\w]*)"
    r"(?:<\|tool_call_argument\|>)?(?:<\|tool_call_begin\|>)?(.*?)"
    r"(?:<\|tool_call_end\|>|<\|tool_call_begin\|>|\Z)",
    re.DOTALL,
)

_PARAMETER = re.compile(r"<parameter\s+name=\"([^\"]+)\"\s*>(.*?)</parameter\s*>", re.DOTALL)
_PARAM_OR_PARAMETER = re.compile(
    r"<param(?:eter)?\s+name=\"([^\"]+)\"\s*>(.*?)</param(?:eter)?\s*>", re.DOTALL
)
_CHILD_XML_TAG = re.compile(r"<([A-Za-z_][\w]*)\s*>(.*?)</\1\s*>", re.DOTALL)
_CALLS_WRAPPER = re.compile(r"</?tool_calls\s*>|<\|/?tool_calls\|>|<\|tool_call_end\|>")

# Every delimiter of the grammars above, opening and closing. A fragment that
# contains one of these is a tool call we could not read, never prose. The
# closing tags matter on their own: the degenerate completion that fired this
# was a bare trailing close with no opening tag anywhere in it.
_MARKERS = (
    "[Tool call:",
    "<tool_calls",
    "</tool_calls>",
    "<tool_call",
    "</tool_call>",
    "<invoke",
    "</invoke>",
    "<parameter",
    "</parameter>",
    "<function=",
    "</function>",
    "<tool name=",
    "</tool>",
    "<delegate_to",
    "</delegate_to>",
    "</delegate_to_role>",
    "<|tool_calls|>",
    "<|tool_call_begin|>",
    "<|tool_call_end|>",
)


@dataclass(frozen=True, slots=True)
class TextChannel:
    """What one completion's text channel actually carried.

    ``undecodable`` is the protocol markup that could not be read. It is never
    part of ``prose``, so a caller that renders ``prose`` to the user cannot
    render a fragment by accident.
    """

    prose: str
    calls: tuple[NativeToolCall, ...] = ()
    undecodable: str = ""


def parse_text_channel(text: str) -> TextChannel:
    """Split ``text`` into prose, decoded tool calls, and unreadable markup."""
    raw = (text or "").strip()
    if not raw:
        return TextChannel("")

    calls, residue = _decode_calls(raw)
    cut = _first_marker(_outside_fences(residue))
    if cut < 0:
        return TextChannel(residue.strip(), tuple(calls))
    return TextChannel(
        prose=residue[:cut].strip(),
        calls=tuple(calls),
        undecodable=residue[cut:].strip(),
    )


def _decode_calls(text: str) -> tuple[list[NativeToolCall], str]:
    """Replace every decodable call region with a space; return calls + residue."""
    calls: list[NativeToolCall] = []
    residue = text
    for pattern, decoder in _ENCODINGS:

        def _replace(match: re.Match[str], decoder: Any = decoder) -> str:
            call = decoder(match)
            if call is None:
                return match.group(0)
            calls.append(call)
            return " "

        residue = pattern.sub(_replace, residue)
    return calls, _CALLS_WRAPPER.sub(" ", residue)


def _from_bracket(match: re.Match[str]) -> NativeToolCall | None:
    return _call(match.group(1), _json_object(match.group(2)))


def _from_function(match: re.Match[str]) -> NativeToolCall | None:
    return _call(match.group(1), _json_object(_unfence(match.group(2))))


def _from_invoke(match: re.Match[str]) -> NativeToolCall | None:
    arguments = {name: _scalar(value) for name, value in _PARAMETER.findall(match.group(2))}
    return _call(match.group(1), arguments)


def _from_tool_tag(match: re.Match[str]) -> NativeToolCall | None:
    name = match.group(1).strip()
    body = _unfence(match.group(2).strip())
    # 1. Try JSON body
    json_args = _json_object(body)
    if json_args is not None:
        return _call(name, json_args)
    # 2. Try <param name="..."> or <parameter name="...">
    params = _PARAM_OR_PARAMETER.findall(body)
    if params:
        return _call(name, {k: _scalar(v) for k, v in params})
    # 3. Try child XML tags <tag>value</tag>
    tags = _CHILD_XML_TAG.findall(body)
    if tags:
        return _call(name, {k: _scalar(v) for k, v in tags})
    return None


def _from_tool_call_json(match: re.Match[str]) -> NativeToolCall | None:
    body = _unfence(match.group(1).strip())
    parsed = _json_object(body)
    if parsed is None:
        return None
    if "function" in parsed and isinstance(parsed["function"], dict):
        parsed = parsed["function"]
    name = str(parsed.get("name") or "").strip()
    raw_args = parsed.get("arguments")
    args: dict[str, Any] = {}
    if isinstance(raw_args, dict):
        args = raw_args
    elif isinstance(raw_args, str) and raw_args.strip():
        parsed_args = _json_object(raw_args)
        args = parsed_args if parsed_args is not None else {"value": raw_args}
    return _call(name, args)


def _from_delegate(match: re.Match[str]) -> NativeToolCall | None:
    body = _unfence(match.group(1).strip())
    parsed_json = _json_object(body)
    tags = dict(_CHILD_XML_TAG.findall(body)) if not parsed_json else {}
    target_role = (
        tags.get("role")
        or tags.get("target_role")
        or (parsed_json.get("target_role") if parsed_json else "")
        or (parsed_json.get("role") if parsed_json else "")
    )
    subtask = (
        tags.get("subtask")
        or tags.get("objective")
        or (parsed_json.get("subtask") if parsed_json else "")
        or (parsed_json.get("objective") if parsed_json else "")
    )
    args: dict[str, Any] = {}
    if target_role:
        args["target_role"] = str(target_role).strip()
    if subtask:
        args["subtask"] = str(subtask).strip()
    return _call("delegate", args)


def _from_qwen(match: re.Match[str]) -> NativeToolCall | None:
    name = match.group(1).strip()
    raw_args = match.group(2).strip()
    args = _json_object(raw_args) if raw_args else {}
    return _call(name, args if args is not None else {})


# Grammar to decoder, in the order they are tried. Sits next to the decoders so
# a new encoding is one entry here and one function below.
_ENCODINGS = (
    (_BRACKET_CALL, _from_bracket),
    (_FUNCTION_CALL, _from_function),
    (_INVOKE_CALL, _from_invoke),
    (_TOOL_TAG_CALL, _from_tool_tag),
    (_TOOL_CALL_JSON, _from_tool_call_json),
    (_DELEGATE_CALL, _from_delegate),
    (_QWEN_SPECIAL_CALL, _from_qwen),
)


def _call(name: str, arguments: dict[str, Any] | None) -> NativeToolCall | None:
    name = (name or "").strip()
    if arguments is None or not _TOOL_NAME.match(name):
        return None
    if any(
        isinstance(value, str) and _TRUNCATED_VALUE.search(value) for value in arguments.values()
    ):
        return None
    return NativeToolCall(
        call_id=new_id("call"),
        name=name,
        arguments={str(key): value for key, value in arguments.items()},
    )


def _unfence(body: str) -> str:
    body = body.strip()
    fence = re.match(r"^```[\w+-]*\s*\n(.*)\n?```$", body, re.DOTALL)
    return fence.group(1) if fence else body


def _json_object(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads((raw or "").strip())
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _scalar(value: str) -> Any:
    """Keep structured parameter values typed; everything else stays text."""
    text = (value or "").strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    return text if isinstance(parsed, str) else parsed


def _outside_fences(text: str) -> str:
    """Blank out fenced code spans, preserving offsets."""
    return _FENCE.sub(lambda m: " " * len(m.group(0)), text)


def _first_marker(text: str) -> int:
    hits = [text.index(m) for m in _MARKERS if m in text]
    return min(hits) if hits else -1


__all__ = ["TextChannel", "parse_text_channel"]
