"""Reciprocal Rank Fusion (RRF) for hybrid search.

Combines several independently-ranked candidate lists (e.g. vector similarity and
full-text `ts_rank`) into a single ranking. RRF scores by *position* rather than
raw score, which is what lets us fuse rankings whose scores live on different,
incomparable scales — a cosine similarity (0..1) and a `ts_rank` (unbounded) can't
be added directly, but their ranks can.

Score for a candidate = sum over each list it appears in of 1 / (k + rank),
where rank is 1-based. `k` (default 60, the value from the original RRF paper)
damps the contribution of top ranks so no single list dominates.

Pure Python, no DB — unit-testable in isolation.
"""

from typing import Hashable, Sequence


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[Hashable]],
    k: int = 60,
) -> dict[Hashable, float]:
    """Fuse ranked candidate lists into {key: rrf_score}, higher is better.

    Args:
        ranked_lists: each inner sequence is a list of keys ordered best-first.
            The same key may appear in multiple lists (its scores add up).
        k: RRF damping constant. Larger k flattens the weight of top ranks.

    Returns:
        Mapping of key -> fused score. Keys absent from every list are absent
        from the result. Order is not guaranteed — sort by value descending.
    """
    scores: dict[Hashable, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


def fuse_and_sort(
    ranked_lists: Sequence[Sequence[Hashable]],
    k: int = 60,
) -> list[tuple[Hashable, float]]:
    """RRF-fuse then return (key, score) pairs sorted by score descending."""
    scores = reciprocal_rank_fusion(ranked_lists, k=k)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
