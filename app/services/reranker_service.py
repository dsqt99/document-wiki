"""Reranker Service — Cross-encoder re-ranking & MMR diversification.

Supports:
- Remote HTTP Rerankers (Text-Embeddings-Inference, Infinity, Cohere, BAAI/bge-reranker-v2-m3)
- Local fallback scoring (token overlap & n-gram Jaccard) for environments without a live GPU reranker
- Maximal Marginal Relevance (MMR) diversification to eliminate repetitive redundant chunks
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, List, Optional

import httpx
from loguru import logger

from app.config import settings


@dataclass
class RerankResult:
    index: int
    score: float
    document: dict[str, Any]


# Sau một lần lỗi, bỏ qua bộ xếp hạng từ xa trong khoảng này để mỗi câu hỏi không phải chờ hết thời gian chờ kết nối.
REMOTE_RETRY_AFTER_SECONDS = 60.0


class RerankerService:
    """Manages document re-ranking and diversification."""

    _instance: Optional[RerankerService] = None

    @classmethod
    def get_instance(cls) -> RerankerService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        enabled: Optional[bool] = None,
        top_n: Optional[int] = None,
        threshold: Optional[float] = None,
        scorer: Optional[Any] = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.reranker_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.reranker_api_key
        self.model = model or settings.reranker_model
        self.enabled = enabled if enabled is not None else settings.reranker_enabled
        self.top_n = top_n or settings.reranker_top_n
        self.threshold = threshold if threshold is not None else getattr(settings, "reranker_threshold", 0.0)
        self.scorer = scorer
        self._remote_down_until = 0.0

    def is_configured(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> bool:
        """Check if Reranker endpoint or custom model is configured."""
        effective_url = base_url or self.base_url or getattr(settings, "reranker_base_url", "")
        return bool(effective_url or self.scorer is not None)

    @classmethod
    async def from_db(cls, db: Optional[Any] = None) -> RerankerService:
        """Dynamically build RerankerService using Database config with .env fallback,
        matching the exact same mechanism as OCR and other model services.
        """
        if db is None:
            return cls.get_instance()

        try:
            from app.services.config_service import ConfigService

            svc = ConfigService(db)

            # 1. UI Switch enabled check (wiki_rerank_enabled in app_config, fallback to settings)
            enabled_val = await svc.get("wiki_rerank_enabled")
            if enabled_val is not None:
                enabled = str(enabled_val).lower() == "true"
            else:
                enabled = settings.reranker_enabled

            # 2. UI Threshold (wiki_rerank_threshold in app_config, fallback to settings / 0.2)
            thresh_val = await svc.get("wiki_rerank_threshold")
            threshold = None
            if thresh_val is not None:
                try:
                    threshold = float(thresh_val)
                except (ValueError, TypeError):
                    threshold = None

            # 3. Build active scorer via wiki_reranker (respects active_reranker_model_spec_id, custom models, catalog, legacy)
            scorer = None
            base_url = None
            model = None
            api_key = None
            try:
                from app.services.wiki_reranker import build_scorer, HTTPReranker
                scorer = await build_scorer(db)
                if isinstance(scorer, HTTPReranker):
                    base_url = scorer.base_url
                    model = scorer.model
                    api_key = scorer.api_key
            except Exception as exc:
                logger.debug(f"build_scorer from active spec failed: {exc}")

            # 4. Fallback flat keys if not set from scorer (ConfigService.get checks DB then .env)
            if not base_url:
                base_url = await svc.get("reranker_base_url")
            if not model:
                model = await svc.get("reranker_model")
            if not api_key:
                api_key = await svc.get("reranker_api_key")

            return cls(
                base_url=base_url,
                api_key=api_key,
                model=model,
                enabled=enabled,
                top_n=settings.reranker_top_n,
                threshold=threshold,
                scorer=scorer,
            )
        except Exception as e:
            logger.warning(f"Could not load reranker config from DB, falling back to defaults: {e}")
            return cls.get_instance()


    async def rerank(
        self,
        query: str,
        documents: List[dict[str, Any]],
        text_key: str = "text",
        top_n: Optional[int] = None,
        threshold: Optional[float] = None,
        degrade_floor: float = 0.15,
        apply_mmr: bool = False,
        mmr_lambda: float = 0.7,
        prior_key: Optional[str] = None,
        pin_key: Optional[str] = None,
        info: Optional[dict[str, Any]] = None,
    ) -> List[dict[str, Any]]:
        """Rerank candidates using remote cross-encoder or local fallback,

        with confidence filtering, auto-degradation floor, and MMR diversification.

        `documents` are expected best-first (e.g. RRF order). `prior_key` names a
        retrieval score blended into the weak local fallback (0.6 local + 0.4
        normalized prior). Documents with a truthy `pin_key` are kept on top,
        outside threshold filtering and MMR. When nothing passes the threshold
        the input order is kept.

        `info`, when given, receives {"mode": "remote" | "local" | "off"} so callers can tell whether the
        cross-encoder really scored the candidates or the weak lexical fallback did.
        """
        if info is None:
            info = {}
        info["mode"] = "off"
        if not documents:
            return []

        limit = top_n or self.top_n
        if not self.enabled:
            return documents[:limit]

        pinned = [dict(d) for d in documents if pin_key and d.get(pin_key)]
        rest = [d for d in documents if not (pin_key and d.get(pin_key))]
        if not rest:
            return pinned[:limit]

        scored_docs: List[dict[str, Any]] = []

        try:
            # Step A: If scorer is configured (from DB/UI active model spec), try it first
            if self.scorer is not None and time.monotonic() >= self._remote_down_until:
                try:
                    raw_docs = [{"text": str(d.get(text_key, "") or "")} for d in rest]
                    scores = await asyncio.wait_for(self.scorer.score(query, raw_docs), timeout=30.0)
                    for idx, (doc, score) in enumerate(zip(rest, scores)):
                        doc_copy = dict(doc)
                        doc_copy["rerank_score"] = float(score)
                        doc_copy["_rr_idx"] = idx
                        scored_docs.append(doc_copy)
                    scored_docs.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)
                    info["mode"] = "remote"
                except Exception as e:
                    self._remote_down_until = time.monotonic() + REMOTE_RETRY_AFTER_SECONDS
                    logger.warning(
                        f"Reranker scorer call failed: {e}. "
                        f"Falling back to local scoring for {REMOTE_RETRY_AFTER_SECONDS:.0f}s."
                    )

            # Step B: If remote reranker URL is configured, try calling it
            if not scored_docs and self.base_url and time.monotonic() >= self._remote_down_until:
                try:
                    scored_docs = await self._call_remote_reranker(query, rest, text_key=text_key)
                    info["mode"] = "remote"
                except Exception as e:
                    self._remote_down_until = time.monotonic() + REMOTE_RETRY_AFTER_SECONDS
                    logger.warning(
                        f"Remote reranker call to {self.base_url} failed: {e}. "
                        f"Falling back to local scoring for {REMOTE_RETRY_AFTER_SECONDS:.0f}s."
                    )

            # Step C: Fallback to local scoring if remote call failed or returned empty
            if not scored_docs:
                info["mode"] = "local"
                scored_docs = self._local_rerank(query, rest, text_key=text_key)
                if prior_key:
                    self._blend_prior(scored_docs, prior_key)

            # Step D: Apply threshold filtering with auto-degradation
            min_thresh = threshold if threshold is not None else (self.threshold if self.threshold is not None else getattr(settings, "reranker_threshold", 0.0))
            if min_thresh and min_thresh > 0:
                filtered = [d for d in scored_docs if d.get("rerank_score", 0.0) >= min_thresh]
                if not filtered and degrade_floor is not None and degrade_floor < min_thresh:
                    # Auto-degrade to degrade_floor to avoid dropping all hits
                    filtered = [d for d in scored_docs if d.get("rerank_score", 0.0) >= degrade_floor]
                if filtered:
                    scored_docs = filtered
                else:
                    # Reranker is not confident about anything: trust retrieval order.
                    order = {id(d): i for i, d in enumerate(rest)}
                    score_of = {d.get("_rr_idx"): d.get("rerank_score", 0.0) for d in scored_docs}
                    scored_docs = [dict(d, rerank_score=score_of.get(order[id(d)], 0.0)) for d in rest]
                    apply_mmr = False

            # MMR Diversification: prevent identical repetitive chunks from saturating context
            room = max(limit - len(pinned), 0)
            if apply_mmr and len(scored_docs) > 1 and room > 0:
                scored_docs = self.diversify_mmr(
                    scored_docs,
                    text_key=text_key,
                    score_key="rerank_score",
                    lambda_param=mmr_lambda,
                    top_n=room,
                )

            for d in scored_docs:
                d.pop("_rr_idx", None)
            return (pinned + scored_docs[:room])[:limit]
        finally:
            if self.scorer is not None:
                try:
                    from app.services.wiki_reranker import close_scorer
                    await close_scorer(self.scorer)
                except Exception as exc:
                    logger.debug(f"close_scorer failed: {exc}")


    @staticmethod
    def _blend_prior(scored_docs: List[dict[str, Any]], prior_key: str) -> None:
        """Mix a normalized retrieval prior into local scores, then re-sort."""
        priors = [float(d.get(prior_key) or 0.0) for d in scored_docs]
        top = max(priors) if priors else 0.0
        for d, p in zip(scored_docs, priors):
            norm = p / top if top > 0 else 0.0
            d["rerank_score"] = round(0.6 * float(d.get("rerank_score", 0.0)) + 0.4 * norm, 4)
        scored_docs.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)

    async def _call_remote_reranker(
        self,
        query: str,
        documents: List[dict[str, Any]],
        text_key: str = "text",
    ) -> List[dict[str, Any]]:
        """Call remote vLLM / Jina / Cohere-style or TEI rerank API."""
        # Accept either a base URL ('https://host/v1') or the full endpoint ('https://host/v1/rerank').
        endpoint = self.base_url if self.base_url.endswith("/rerank") else f"{self.base_url}/rerank"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        texts = [str(doc.get(text_key, "") or "") for doc in documents]
        payload = {
            "model": self.model,
            "query": query,
            "documents": texts,
            "top_n": len(texts),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code != 200:
                # TEI format: 'texts' instead of 'documents', no model param
                logger.debug(f"Reranker {endpoint} returned {resp.status_code}; retrying with TEI payload")
                resp = await client.post(
                    endpoint,
                    json={"query": query, "texts": texts},
                    headers=headers,
                )
            resp.raise_for_status()
            data = resp.json()

        # Parse results: format {"results": [{"index": 0, "relevance_score": 0.9}, ...]}
        # or list of objects
        results = data.get("results", data) if isinstance(data, dict) else data
        scored_docs: List[dict[str, Any]] = []

        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score", item.get("score", 0.0))
            if idx is not None and 0 <= idx < len(documents):
                doc_copy = dict(documents[idx])
                doc_copy["rerank_score"] = float(score)
                doc_copy["_rr_idx"] = idx
                scored_docs.append(doc_copy)

        scored_docs.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)
        return scored_docs

    def _local_rerank(
        self,
        query: str,
        documents: List[dict[str, Any]],
        text_key: str = "text",
    ) -> List[dict[str, Any]]:
        """Compute heuristic relevance score based on token and phrase overlap."""
        q_tokens = set(self._tokenize(query.lower()))
        scored_docs: List[dict[str, Any]] = []

        for idx, doc in enumerate(documents):
            text = str(doc.get(text_key, "") or "").lower()
            d_tokens = set(self._tokenize(text))

            if not d_tokens or not q_tokens:
                score = 0.0
            else:
                intersection = q_tokens.intersection(d_tokens)
                jaccard = len(intersection) / len(q_tokens.union(d_tokens))
                coverage = len(intersection) / len(q_tokens)
                # Exact query substring boost
                exact_boost = 0.3 if " ".join(self._tokenize(query)) in " ".join(self._tokenize(text)) else 0.0
                score = (coverage * 0.5) + (jaccard * 0.2) + exact_boost

            doc_copy = dict(doc)
            doc_copy["rerank_score"] = round(float(score), 4)
            doc_copy["_rr_idx"] = idx
            scored_docs.append(doc_copy)

        scored_docs.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)
        return scored_docs

    def diversify_mmr(
        self,
        candidates: List[dict[str, Any]],
        text_key: str = "text",
        score_key: str = "rerank_score",
        lambda_param: float = 0.7,
        top_n: int = 10,
    ) -> List[dict[str, Any]]:
        """Maximal Marginal Relevance (MMR) to balance high relevance with diversity.

        MMR = argmax [ lambda * Rel(d) - (1 - lambda) * max_{d_j in Selected} Sim(d, d_j) ]
        """
        if not candidates or len(candidates) <= 1 or top_n <= 1:
            return candidates[:top_n]

        selected: List[dict[str, Any]] = []
        unselected = list(candidates)

        # Precompute token sets for similarity
        token_sets = {
            id(c): set(self._tokenize(str(c.get(text_key, "") or "").lower()))
            for c in candidates
        }

        # 1. Pick the highest scoring element first
        unselected.sort(key=lambda x: x.get(score_key, 0.0), reverse=True)
        first = unselected.pop(0)
        selected.append(first)

        # 2. Iteratively pick next candidates maximizing MMR
        while unselected and len(selected) < top_n:
            best_score = -float("inf")
            best_idx = 0

            for idx, cand in enumerate(unselected):
                rel = float(cand.get(score_key, 0.0))
                cand_tok = token_sets[id(cand)]

                # Max similarity to already selected candidates
                max_sim = 0.0
                for sel in selected:
                    sel_tok = token_sets[id(sel)]
                    if cand_tok and sel_tok:
                        sim = len(cand_tok.intersection(sel_tok)) / len(cand_tok.union(sel_tok))
                        if sim > max_sim:
                            max_sim = sim

                mmr_score = (lambda_param * rel) - ((1.0 - lambda_param) * max_sim)
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            selected.append(unselected.pop(best_idx))

        return selected

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Accent-folded lower-case alphanumeric tokens ("Phòng" == "phong")."""
        from app.core.vi_tokenizer import strip_accents

        return re.findall(r"\w+", strip_accents(text or "").lower())
