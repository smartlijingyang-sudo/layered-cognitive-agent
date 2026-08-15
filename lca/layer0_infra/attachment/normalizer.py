"""TextNormalizationService — sanitize user-visible text before prompt injection.

This service maps Unicode lookalikes to their ASCII equivalents so that code
generation never receives characters that break Python syntax or confuse models.

Design principle: normalization is a *pure function* applied only at the prompt
boundary. Original file bytes in FileStore are never mutated.

ADR reference: zero-delivery root-cause #1 (Unicode injection).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TextNormalizationRules:
    """Immutable normalization rules. Field names describe the category."""

    # Quotation marks — common sources of SyntaxError in generated Python.
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

    # Dashes and hyphens.
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

    # Ellipsis and other punctuation that models may copy verbatim.
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

    # Characters to strip entirely (zero-width, BOM, soft-hyphen).
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


class TextNormalizationService:
    """Deterministic text normalization for prompt injection boundaries.

    Thread-safe (stateless after init). Rules are applied in fixed order:
    strip → replace maps → collapse whitespace.

    Usage::

        svc = TextNormalizationService()
        safe_text = svc.normalize(raw_text)
    """

    def __init__(self, rules: TextNormalizationRules | None = None) -> None:
        self._rules = rules if rules is not None else TextNormalizationRules()

    def normalize(self, text: str) -> str:
        """Apply all normalization rules to *text*. Pure function."""
        if not text:
            return text

        # Phase 1: strip invisible / zero-width characters.
        for ch in self._rules.strip_chars:
            text = text.replace(ch, "")

        # Phase 2: replace Unicode lookalikes with ASCII equivalents.
        for mapping in (
            self._rules.quote_map,
            self._rules.dash_map,
            self._rules.punctuation_map,
        ):
            for src, dst in mapping.items():
                if src in text:
                    text = text.replace(src, dst)

        # Phase 3: collapse runs of whitespace (including residual NBSP) into
        # single ASCII space. This prevents models from seeing invisible
        # formatting artifacts.
        return _collapse_whitespace(text)


def _collapse_whitespace(text: str) -> str:
    import re

    return re.sub(r"[ \t]+", " ", text)


def normalize_for_injection(text: str) -> str:
    """Module-level convenience — default rules, no object needed."""
    return _DEFAULT_SVC.normalize(text)


_DEFAULT_SVC = TextNormalizationService()
