"""Normalize user-visible text at the prompt boundary (ADR-0121).

Maps Unicode lookalikes (curly quotes, em dashes, zero-width chars) to their
ASCII equivalents so downstream code generation never receives syntax-breaking
characters. Original bytes in FileStore are never mutated.

ADR reference: zero-delivery root-cause #1 (Unicode injection).

The historical ``TextNormalizationService`` class wrapper was removed in
ADR-0121 PR-D: only the pure :func:`normalize_for_injection` entry point is
needed by callers, so the class indirection is gone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TextNormalizationRules:
    """Immutable normalization rules. Field names describe the category."""

    quote_map: dict[str, str] = field(
        default_factory=lambda: {
            "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
            "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
            "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
            "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
            "\u201a": "'",  # SINGLE LOW-9 QUOTATION MARK
            "\u201b": "'",  # SINGLE HIGH-REVERSED-9
            "\u201f": '"',  # DOUBLE HIGH-REVERSED-9
            "\u00ab": '"',  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK («)
            "\u00bb": '"',  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK (»)
            "\u300c": '"',  # LEFT CORNER BRACKET (CJK)
            "\u300d": '"',  # RIGHT CORNER BRACKET (CJK)
            "\u300e": '"',  # LEFT WHITE CORNER BRACKET
            "\u300f": '"',  # RIGHT WHITE CORNER BRACKET
            "\uff02": '"',  # FULLWIDTH QUOTATION MARK
            "\uff07": "'",  # FULLWIDTH APOSTROPHE
        }
    )

    dash_map: dict[str, str] = field(
        default_factory=lambda: {
            "\u2014": "--",  # EM DASH
            "\u2013": "-",  # EN DASH
            "\u2012": "-",  # FIGURE DASH
            "\u2015": "--",  # HORIZONTAL BAR
            "\uff0d": "-",  # FULLWIDTH HYPHEN-MINUS
            "\u2212": "-",  # MINUS SIGN
        }
    )

    punctuation_map: dict[str, str] = field(
        default_factory=lambda: {
            "\u2026": "...",  # HORIZONTAL ELLIPSIS
            "\u2025": "..",  # TWO DOT LEADER
            "\u00a0": " ",  # NON-BREAKING SPACE
            "\u2000": " ",  # EN QUAD
            "\u2001": " ",  # EM QUAD
            "\u2002": " ",  # EN SPACE
            "\u2003": " ",  # EM SPACE
            "\u2004": " ",  # THREE-PER-EM SPACE
            "\u2005": " ",  # FOUR-PER-EM SPACE
            "\u2006": " ",  # SIX-PER-EM SPACE
            "\u2007": " ",  # FIGURE SPACE
            "\u2008": " ",  # PUNCTUATION SPACE
            "\u2009": " ",  # THIN SPACE
            "\u202f": " ",  # NARROW NO-BREAK SPACE
            "\u205f": " ",  # MEDIUM MATHEMATICAL SPACE
            "\u3000": " ",  # IDEOGRAPHIC SPACE
        }
    )

    strip_chars: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "\u200b",  # ZERO WIDTH SPACE
                "\u200c",  # ZERO WIDTH NON-JOINER
                "\u200d",  # ZERO WIDTH JOINER
                "\ufeff",  # BOM / ZERO WIDTH NO-BREAK SPACE
                "\u00ad",  # SOFT HYPHEN
                "\u061c",  # ARABIC LETTER MARK
            }
        )
    )


_DEFAULT_RULES = TextNormalizationRules()
_WHITESPACE_RE = re.compile(r"[ \t]+")


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text)


def normalize_for_injection(text: str, *, rules: TextNormalizationRules | None = None) -> str:
    """Pure normalization: invisible chars → ASCII equivalents + collapse spaces."""
    if not text:
        return text
    active = rules or _DEFAULT_RULES
    for ch in active.strip_chars:
        text = text.replace(ch, "")
    for mapping in (active.quote_map, active.dash_map, active.punctuation_map):
        for src, dst in mapping.items():
            if src in text:
                text = text.replace(src, dst)
    return _collapse_whitespace(text)


__all__ = ["TextNormalizationRules", "normalize_for_injection"]
