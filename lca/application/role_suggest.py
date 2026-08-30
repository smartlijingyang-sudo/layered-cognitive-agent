"""角色路径模糊匹配 —— 移植自 agency-orchestrator ``agents/loader.ts::suggestFromPaths``。

当 LLM 输出不在白名单内的 role_id 时，从角色库索引里找最接近的真实路径，
用于确定性自动修复与重试提示（compose / casting 共用思路）。
"""

from __future__ import annotations

_SUGGEST_DEFAULT_LIMIT = 3


def edit_distance(a: str, b: str) -> int:
    """Levenshtein 编辑距离（与 AO loader.ts 一致）。"""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    cur = [0] * (n + 1)
    for i in range(1, m + 1):
        cur[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev, cur = cur, prev
    return prev[n]


def suggest_from_paths(
    bad_path: str,
    all_paths: list[str],
    *,
    limit: int = _SUGGEST_DEFAULT_LIMIT,
) -> list[str]:
    """在给定候选路径集合里，找出最接近 bad_path 的若干个（纯函数，不读盘）。

    优先子串包含（按 leaf 名匹配），再按编辑距离兜底；只返回足够接近的。
    """
    if not all_paths:
        return []

    leaf = (bad_path.split("/")[-1] or bad_path).lower()
    target = bad_path.lower()

    scored: list[tuple[str, int, bool]] = []
    for path in all_paths:
        path_lower = path.lower()
        path_leaf = (path.split("/")[-1] or path).lower()
        substr = path_lower in leaf or path_leaf in leaf or leaf in path_leaf or leaf in path_lower
        dist = min(edit_distance(target, path_lower), edit_distance(leaf, path_leaf))
        scored.append((path, dist, substr))

    scored.sort(key=lambda item: (0 if item[2] else 1, item[1]))

    threshold = (len(leaf) + 1) // 2 + 4
    return [path for path, dist, substr in scored if substr or dist <= threshold][:limit]


def suggest_for_auto_repair(bad_path: str, all_paths: list[str]) -> str | None:
    """高置信度自动修复：仅在同部门或子串命中时才替换（避免跨部门误匹配）。"""
    suggestions = suggest_from_paths(bad_path, all_paths, limit=5)
    if not suggestions:
        return None

    leaf = (bad_path.split("/")[-1] or bad_path).lower()
    target = bad_path.lower()
    bad_dept = bad_path.split("/")[0].lower() if "/" in bad_path else None

    for suggestion in suggestions:
        suggestion_lower = suggestion.lower()
        suggestion_leaf = (suggestion.split("/")[-1] or suggestion).lower()
        substr = (
            suggestion_lower in target
            or suggestion_leaf in leaf
            or leaf in suggestion_leaf
            or leaf in suggestion_lower
        )
        if substr:
            return suggestion
        if (
            bad_dept is not None
            and suggestion_lower.startswith(f"{bad_dept}/")
            and edit_distance(leaf, suggestion_leaf) <= max(4, len(leaf) // 3)
        ):
            return suggestion
        if bad_dept is None:
            threshold = (len(leaf) + 1) // 2 + 4
            if edit_distance(leaf, suggestion_leaf) <= threshold:
                return suggestion
    return None
