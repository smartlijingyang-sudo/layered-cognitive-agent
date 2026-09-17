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

_BRACKET_CALL = re.compile(r"\[Tool call:\s*([A-Za-z_][\w]*)\]\s*(\{.*\})\s*\Z", re.DOTALL)
_FUNCTION_CALL = re.compile(r"<function=\s*([A-Za-z_][\w]*)\s*>(.*?)</function\s*>", re.DOTALL)
_INVOKE_CALL = re.compile(r"<invoke\s+name=\"([^\"]+)\"\s*>(.*?)</invoke\s*>", re.DOTALL)
_PARAMETER = re.compile(r"<parameter\s+name=\"([^\"]+)\"\s*>(.*?)</parameter\s*>", re.DOTALL)
_CALLS_WRAPPER = re.compile(r"</?tool_calls\s*>")

# Every delimiter of the grammars above, opening and closing. A fragment that
# contains one of these is a tool call we could not read, never prose. The
# closing tags matter on their own: the degenerate completion that fired this
# was a bare trailing close with no opening tag anywhere in it.
_MARKERS = (
    "[Tool call:",
    "<tool_calls",
    "</tool_calls>",
    "<invoke",
    "</invoke>",
    "<parameter",
    "</parameter>",
    "<function=",
    "</function>",
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


# Grammar to decoder, in the order they are tried. Sits next to the decoders so
# a new encoding is one entry here and one function below.
_ENCODINGS = (
    (_BRACKET_CALL, _from_bracket),
    (_FUNCTION_CALL, _from_function),
    (_INVOKE_CALL, _from_invoke),
)


def _call(name: str, arguments: dict[str, Any] | None) -> NativeToolCall | None:
    name = (name or "").strip()
    if arguments is None or not _TOOL_NAME.match(name):
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
