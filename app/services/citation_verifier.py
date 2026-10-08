"""Citation Verifier and Lightweight [^sN] Footnote Management."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from app.core.text_normalizer import normalize_text


@dataclass
class CitationVerificationResult:
    claim: str
    is_verified: bool
    confidence: float
    matched_excerpt: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "is_verified": self.is_verified,
            "confidence": self.confidence,
            "matched_excerpt": self.matched_excerpt,
            "reason": self.reason,
        }


@dataclass
class PageCitationReport:
    page_slug: str
    total_claims: int
    verified_claims: int
    unverified_claims: List[CitationVerificationResult] = field(default_factory=list)
    footnotes: List[Dict[str, Any]] = field(default_factory=list)
    score: float = 1.0
    has_hallucinations: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_slug": self.page_slug,
            "total_claims": self.total_claims,
            "verified_claims": self.verified_claims,
            "unverified_claims": [c.to_dict() for c in self.unverified_claims],
            "footnotes": self.footnotes,
            "score": self.score,
            "has_hallucinations": self.has_hallucinations,
        }


# Footnote regex patterns: [^s1] or [^s2] (support indentation)
_FOOTNOTE_MARKER_RE = re.compile(r"\[\^([a-zA-Z0-9_-]+)\]")
_FOOTNOTE_DEF_RE = re.compile(r"^\s*\[\^([a-zA-Z0-9_-]+)\]:\s*(.*)$", re.MULTILINE)
_LEGAL_ARTICLE_RE = re.compile(r"\bĐiều\s+(\d+[a-z]?)\b", re.IGNORECASE)
_LEGAL_DOC_NUMBER_RE = re.compile(r"\b(\d+(?:\/\d{4})?\/[A-Za-z0-9\/\-\_ĐđÀ-ỹ]+)\b")


def extract_footnotes(markdown_text: str) -> List[Dict[str, str]]:
    """Extract footnote definitions [^id]: text from markdown content."""
    matches = _FOOTNOTE_DEF_RE.findall(markdown_text or "")
    return [{"id": m[0], "text": m[1].strip()} for m in matches]


def format_footnote_citations(content_md: str, footnotes: List[Dict[str, str]]) -> str:
    """Append or format lightweight footnote definitions at the end of markdown content."""
    if not footnotes:
        return content_md

    existing_defs = {f["id"] for f in extract_footnotes(content_md)}
    new_blocks = []

    for fn in footnotes:
        fn_id = fn.get("id") or "s1"
        citation = fn.get("citation") or fn.get("text") or ""
        if fn_id not in existing_defs and citation:
            new_blocks.append(f"[^{fn_id}]: {citation.strip()}")

    if not new_blocks:
        return content_md

    body = (content_md or "").rstrip()
    return f"{body}\n\n" + "\n".join(new_blocks) + "\n"


def apply_citation_callout(content_md: str, report: PageCitationReport) -> str:
    """Prepend an Obsidian callout warning if unverified claims or hallucinations are found."""
    if not report.has_hallucinations or not report.unverified_claims:
        return content_md

    # Check if a citation warning callout already exists
    if "> [!warning] **Cảnh báo trích dẫn" in content_md:
        return content_md

    items = []
    for c in report.unverified_claims[:5]:
        snippet = c.claim.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:117] + "…"
        items.append(f"> - {snippet}")

    callout = (
        f"> [!warning] **Cảnh báo trích dẫn: Phát hiện nội dung chưa xác minh ({len(report.unverified_claims)} khẳng định)**\n"
        f"> Các nội dung sau chưa tìm thấy căn cứ trực tiếp trong tài liệu nguồn:\n"
        + "\n".join(items)
        + "\n\n"
    )

    return callout + content_md


class CitationVerifier:
    """Verifies factual claims and lightweight [^sN] citations against source text."""

    def __init__(self, confidence_threshold: float = 0.65):
        self.confidence_threshold = confidence_threshold

    def verify_claim(self, claim: str, source_text: str) -> CitationVerificationResult:
        """Verify an individual claim against the source document."""
        c_clean = normalize_text(claim)
        s_clean = normalize_text(source_text)

        if not c_clean:
            return CitationVerificationResult(
                claim=claim, is_verified=True, confidence=1.0, reason="Empty claim"
            )

        if not s_clean:
            return CitationVerificationResult(
                claim=claim, is_verified=False, confidence=0.0, reason="Chưa tìm thấy căn cứ: Tài liệu nguồn rỗng"
            )

        # 1. Legal Entity & Article check:
        claim_articles = set(_LEGAL_ARTICLE_RE.findall(claim))
        source_articles = set(_LEGAL_ARTICLE_RE.findall(source_text))
        missing_articles = claim_articles - source_articles
        if missing_articles:
            missing_str = ", ".join(f"Điều {a}" for a in missing_articles)
            return CitationVerificationResult(
                claim=claim,
                is_verified=False,
                confidence=0.2,
                reason=f"Chưa tìm thấy căn cứ: {missing_str} không có trong tài liệu nguồn",
            )

        claim_docs = set(_LEGAL_DOC_NUMBER_RE.findall(claim))
        source_docs = set(_LEGAL_DOC_NUMBER_RE.findall(source_text))
        missing_docs = {d for d in claim_docs if "/" in d and d not in source_docs}
        if missing_docs:
            missing_dstr = ", ".join(missing_docs)
            return CitationVerificationResult(
                claim=claim,
                is_verified=False,
                confidence=0.25,
                reason=f"Chưa tìm thấy căn cứ: Số hiệu văn bản {missing_dstr} không có trong tài liệu nguồn",
            )

        # 2. Direct verbatim / containment check
        if c_clean in s_clean:
            idx = s_clean.find(c_clean)
            start = max(0, idx - 40)
            end = min(len(source_text), idx + len(c_clean) + 40)
            return CitationVerificationResult(
                claim=claim,
                is_verified=True,
                confidence=1.0,
                matched_excerpt=source_text[start:end].strip(),
                reason="Khớp nguyên văn",
            )

        # 3. Token-based overlap with paragraph & sliding multi-sentence windows
        claim_tokens = [t for t in c_clean.split() if len(t) > 1]
        if not claim_tokens:
            return CitationVerificationResult(
                claim=claim, is_verified=True, confidence=1.0, reason="Trivial tokens"
            )

        claim_token_set = set(claim_tokens)

        # Break into paragraphs and overlapping 2-sentence windows
        raw_paras = [p.strip() for p in source_text.split("\n\n") if len(p.strip()) > 20]
        raw_sents = [s.strip() for s in re.split(r"[.\n;]+", source_text) if len(s.strip()) > 15]

        candidate_windows = list(raw_paras)
        for i in range(len(raw_sents) - 1):
            candidate_windows.append(raw_sents[i] + ". " + raw_sents[i + 1])
        if not candidate_windows:
            candidate_windows = raw_sents

        best_score = 0.0
        best_excerpt = None

        for window in candidate_windows:
            w_clean = normalize_text(window)
            w_tokens = set(w_clean.split())
            if not w_tokens:
                continue

            intersection = claim_token_set & w_tokens
            if not intersection:
                continue

            # Containment: proportion of claim words present in this window
            containment = len(intersection) / len(claim_token_set)
            jaccard = len(intersection) / len(claim_token_set | w_tokens)
            score = 0.75 * containment + 0.25 * jaccard

            if score > best_score:
                best_score = score
                best_excerpt = window

        is_verified = best_score >= self.confidence_threshold
        reason = (
            f"Độ trùng khớp thông tin: {best_score:.2f}"
            if is_verified
            else "Chưa tìm thấy căn cứ trực tiếp trong tài liệu nguồn"
        )

        return CitationVerificationResult(
            claim=claim,
            is_verified=is_verified,
            confidence=round(best_score, 2),
            matched_excerpt=best_excerpt if is_verified else None,
            reason=reason,
        )

    def verify_page(
        self,
        page_slug: str,
        content_md: str,
        source_text: str,
        claims: Optional[List[str]] = None,
    ) -> PageCitationReport:
        """Verify all assertions and lightweight footnotes across a markdown page."""
        target_claims: List[str] = []

        if claims:
            target_claims.extend(claims)

        # Extract sentences that have footnote markers [^sN]
        lines = (content_md or "").split("\n")
        for line in lines:
            line_str = line.strip()
            # Skip code blocks, headers, blockquotes, markdown tables, footnote definitions
            if (
                not line_str
                or line_str.startswith("#")
                or line_str.startswith(">")
                or line_str.startswith("|")
                or line_str.startswith("```")
                or _FOOTNOTE_DEF_RE.match(line_str)
            ):
                continue

            # Sentences containing footnote markers
            if _FOOTNOTE_MARKER_RE.search(line_str):
                for sub_sent in re.split(r"[.!?]+", line_str):
                    if _FOOTNOTE_MARKER_RE.search(sub_sent):
                        clean_sub = _FOOTNOTE_MARKER_RE.sub("", sub_sent).strip()
                        if len(clean_sub) > 15:
                            target_claims.append(clean_sub)

        # If no footnote-marked claims, sample authoritative sentences
        if not target_claims:
            for line in lines:
                line_str = line.strip()
                if not line_str or line_str.startswith("#") or line_str.startswith(">") or line_str.startswith("|"):
                    continue
                for sent in re.split(r"[.!?]+", line_str):
                    s_trimmed = sent.strip()
                    if len(s_trimmed) > 30 and any(
                        kw in s_trimmed.lower()
                        for kw in ("quy định", "phải", "nghiêm cấm", "thời hạn", "mức phạt", "điều", "khoản")
                    ):
                        target_claims.append(s_trimmed)

        # Deduplicate
        unique_claims = []
        seen = set()
        for c in target_claims:
            c_norm = c.lower().strip()
            if c_norm not in seen:
                seen.add(c_norm)
                unique_claims.append(c)

        if not unique_claims:
            return PageCitationReport(
                page_slug=page_slug,
                total_claims=0,
                verified_claims=0,
                score=1.0,
                has_hallucinations=False,
            )

        verified_count = 0
        unverified_list = []

        for c in unique_claims:
            res = self.verify_claim(c, source_text)
            if res.is_verified:
                verified_count += 1
            else:
                unverified_list.append(res)

        total = len(unique_claims)
        score = round(verified_count / total, 2) if total > 0 else 1.0
        has_hallucinations = len(unverified_list) > 0 and score < 0.85

        footnotes = extract_footnotes(content_md)

        return PageCitationReport(
            page_slug=page_slug,
            total_claims=total,
            verified_claims=verified_count,
            unverified_claims=unverified_list,
            footnotes=footnotes,
            score=score,
            has_hallucinations=has_hallucinations,
        )
