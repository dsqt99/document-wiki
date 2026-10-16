"""Bộ xếp hạng lại báo cáo chế độ thực tế (remote/local/off) và không chờ lại máy chủ vừa lỗi."""

import asyncio

from app.services import reranker_service as rs

DOCS = [
    {"id": "a", "text": "Quy định về thời tiết mùa hè."},
    {"id": "b", "text": "Điều kiện an toàn phòng cháy chữa cháy đối với cơ sở."},
]
QUERY = "điều kiện an toàn phòng cháy"


def run(service, **kw):
    info: dict = {}
    out = asyncio.run(service.rerank(QUERY, [dict(d) for d in DOCS], top_n=2, info=info, **kw))
    return out, info["mode"]


def test_modes_off_local_and_remote():
    assert run(rs.RerankerService(base_url="", enabled=False))[1] == "off"
    out, mode = run(rs.RerankerService(base_url="", enabled=True))
    assert mode == "local" and out[0]["id"] == "b"

    service = rs.RerankerService(base_url="http://reranker.internal:8080", enabled=True)

    async def remote(query, documents, text_key="text"):
        return [dict(documents[1], rerank_score=0.9, _rr_idx=1), dict(documents[0], rerank_score=0.1, _rr_idx=0)]

    service._call_remote_reranker = remote
    out, mode = run(service)
    assert mode == "remote" and out[0]["id"] == "b"


def test_failed_remote_falls_back_and_is_not_retried_during_cooldown():
    service = rs.RerankerService(base_url="http://down.internal:8080", enabled=True)
    calls = {"n": 0}

    async def broken(query, documents, text_key="text"):
        calls["n"] += 1
        raise ConnectionError("unreachable")

    service._call_remote_reranker = broken
    assert run(service)[1] == "local" and calls["n"] == 1
    assert run(service)[1] == "local" and calls["n"] == 1  # trong thời gian nghỉ: không gọi lại

    service._remote_down_until = 0.0  # hết thời gian nghỉ
    assert run(service)[1] == "local" and calls["n"] == 2
