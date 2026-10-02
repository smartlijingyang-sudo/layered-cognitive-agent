"""Memory-weighted presentation (ADR-0267).

muse principle: Memory is for USE, not just storage.
When presenting information to the user, automatically boost
items relevant to the user's known interests/profile.

The agent writes memory (that's LCA's strength). This mechanism
ensures it also READS memory when deciding what to emphasize.

This is not ML ranking. It's a deterministic keyword boost:
items matching user profile keywords get boosted in presentation
order, and the agent is nudged to comment on why they're relevant.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WeightedItem:
    """An item with a relevance score for presentation ordering."""

    content: str
    # Base score from retrieval/search ranking
    base_score: float = 1.0
    # Boost from user profile matching (0.0 = no boost)
    profile_boost: float = 0.0
    # Which profile keywords matched (for transparency)
    matched_keywords: list[str] = field(default_factory=list)

    @property
    def final_score(self) -> float:
        return self.base_score * (1.0 + self.profile_boost)


def extract_profile_keywords(profile: dict) -> list[str]:
    """Extract matchable keywords from a user profile.

    Profile is a dict of {key: value} from memory.
    We extract values and split into keywords.
    """
    keywords: list[str] = []
    for value in profile.values():
        if not isinstance(value, str):
            continue
        # Split on common separators, keep meaningful tokens
        for token in value.replace("，", " ").replace(",", " ").split():
            token = token.strip()
            if len(token) >= 2:  # Skip single chars (noise in Chinese)
                keywords.append(token)
    return keywords


def _keyword_matches(keyword: str, item: str) -> bool:
    """Check if a profile keyword matches an item.

    Exact substring match first. For Chinese, fall back to bigram
    matching: if any consecutive 2-char sequence from the keyword
    appears in the item, it's a match. This handles synonymous
    phrasings like "电商出海" vs "跨境电商" (both contain "电商").
    """
    if keyword in item:
        return True
    if len(keyword) >= 2:
        for i in range(len(keyword) - 1):
            if keyword[i : i + 2] in item:
                return True
    return False


def weight_items(
    items: list[str],
    user_profile: dict,
    boost_per_match: float = 0.5,
) -> list[WeightedItem]:
    """Weight presentation items by user profile relevance.

    Args:
        items: List of content strings to present (e.g., news headlines).
        user_profile: Dict of user attributes from memory.
        boost_per_match: Score boost per keyword match.

    Returns:
        Items sorted by final_score descending, with match metadata.

    muse principle: This is deterministic and auditable. The agent
    can see WHY an item was boosted (matched_keywords).
    """
    keywords = extract_profile_keywords(user_profile)
    weighted: list[WeightedItem] = []

    for item in items:
        matched: list[str] = []
        for kw in keywords:
            if _keyword_matches(kw, item):
                matched.append(kw)

        weighted.append(
            WeightedItem(
                content=item,
                base_score=1.0,
                profile_boost=len(matched) * boost_per_match,
                matched_keywords=matched,
            )
        )

    # Stable sort: highest score first, preserve original order on ties
    weighted.sort(key=lambda w: w.final_score, reverse=True)
    return weighted


def format_with_relevance(
    weighted: list[WeightedItem],
    highlight_threshold: float = 1.5,
) -> list[str]:
    """Format items for presentation, highlighting highly relevant ones.

    Items above the threshold get a relevance note. This nudges the
    agent to explain WHY an item matters to THIS user.
    """
    formatted: list[str] = []
    for w in weighted:
        if w.final_score >= highlight_threshold and w.matched_keywords:
            kw_str = "、".join(w.matched_keywords)
            formatted.append(f"{w.content}\n  → 与你相关（{kw_str}）")
        else:
            formatted.append(w.content)
    return formatted
