"""Unit tests for app/services/search_fusion.py (Reciprocal Rank Fusion).

Pure ranking logic — no DB, no Redis.
"""

from app.services.search_fusion import fuse_and_sort, reciprocal_rank_fusion


def test_empty_lists():
    assert reciprocal_rank_fusion([]) == {}
    assert reciprocal_rank_fusion([[], []]) == {}


def test_single_list_preserves_order():
    scores = reciprocal_rank_fusion([["a", "b", "c"]])
    # Rank 1 scores highest, rank 3 lowest.
    assert scores["a"] > scores["b"] > scores["c"]


def test_rank_1_score_value():
    # Default k=60, rank 1 → 1/(60+1).
    scores = reciprocal_rank_fusion([["a"]])
    assert scores["a"] == 1.0 / 61


def test_key_in_two_lists_sums():
    # "a" appears rank 1 in both lists → its score is the sum of both contributions.
    scores = reciprocal_rank_fusion([["a", "b"], ["a", "c"]])
    assert scores["a"] == (1.0 / 61) * 2
    # A key in only one list scores less than the shared top key.
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["c"]


def test_fusion_beats_single_high_rank():
    # "x" is rank 1 in list A only. "y" is rank 2 in BOTH lists.
    # Two rank-2 appearances (2 * 1/62) should outrank one rank-1 (1/61).
    scores = reciprocal_rank_fusion([["x", "y"], ["z", "y"]])
    assert scores["y"] > scores["x"]


def test_fuse_and_sort_descending():
    ranked = fuse_and_sort([["a", "b", "c"], ["b", "a"]])
    keys = [k for k, _ in ranked]
    # "a" (ranks 1,2) and "b" (ranks 2,1) tie; both beat "c" (rank 3, one list).
    assert keys[-1] == "c"
    assert set(keys[:2]) == {"a", "b"}
    # Sorted by score descending.
    values = [v for _, v in ranked]
    assert values == sorted(values, reverse=True)


def test_custom_k_flattens():
    # Larger k compresses the gap between rank 1 and rank 2.
    small_k = reciprocal_rank_fusion([["a", "b"]], k=1)
    large_k = reciprocal_rank_fusion([["a", "b"]], k=1000)
    gap_small = small_k["a"] - small_k["b"]
    gap_large = large_k["a"] - large_k["b"]
    assert gap_small > gap_large


def test_tuple_keys_supported():
    # Chunk keys in the hybrid search are (page_id, chunk_index) tuples.
    k1, k2 = ("page1", 0), ("page1", 1)
    scores = reciprocal_rank_fusion([[k1, k2]])
    assert scores[k1] > scores[k2]
