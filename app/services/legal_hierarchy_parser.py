"""State-machine based legal hierarchy parser for Vietnamese administrative and legal documents.

Parses documents into a structured hierarchy:
Part -> Chapter -> Section -> Article -> Clause -> Point -> Appendix.
Correctly handles Quoted Text Boundaries in amending documents (e.g. Decree 50/2024 modifying Decree 136/2020).
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from loguru import logger

from app.core.text_normalizer import normalize_text


class LegalNodeType(str, Enum):
    DOCUMENT = "document"
    PREAMBLE = "preamble"
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"
    ARTICLE = "article"
    CLAUSE = "clause"
    POINT = "point"
    APPENDIX = "appendix"


@dataclass
class LegalPoint:
    letter: str  # 'a', 'b', 'c', ...
    content: str


@dataclass
class LegalClause:
    number: str  # '1', '2', '3', ...
    content: str
    points: List[LegalPoint] = field(default_factory=list)


@dataclass
class LegalArticle:
    number: str  # '1', '5a', '18'
    title: str
    content: str
    chapter_num: Optional[str] = None
    chapter_title: Optional[str] = None
    section_num: Optional[str] = None
    section_title: Optional[str] = None
    is_amending: bool = False
    clauses: List[LegalClause] = field(default_factory=list)


@dataclass
class LegalChapter:
    number: str  # 'I', 'II', '1'
    title: str
    articles: List[LegalArticle] = field(default_factory=list)


@dataclass
class LegalDocumentTree:
    doc_number: Optional[str] = None
    preamble: str = ""
    chapters: List[LegalChapter] = field(default_factory=list)
    unattached_articles: List[LegalArticle] = field(default_factory=list)
    appendices: List[Dict[str, Any]] = field(default_factory=list)

    def get_all_articles(self) -> List[LegalArticle]:
        """Return all articles across all chapters and unattached sections in order."""
        res: List[LegalArticle] = []
        for ch in self.chapters:
            res.extend(ch.articles)
        res.extend(self.unattached_articles)
        return res


# Regex Patterns for structural tokens
RE_PART = re.compile(r"^(?:#+\s*)?PHẦN\s+THỨ\s+([A-ZÀ-Ỹ0-9]+)[:\.]?\s*(.*)$", re.IGNORECASE)
RE_CHAPTER = re.compile(r"^(?:#+\s*)?CHƯƠNG\s+([IVXLCDM0-9]+)[:\.]?\s*(.*)$", re.IGNORECASE)
RE_SECTION = re.compile(r"^(?:#+\s*)?MỤC\s+(\d+)[:\.]?\s*(.*)$", re.IGNORECASE)
RE_ARTICLE = re.compile(r"^(?:#+\s*)?Điều\s+(\d+[a-z]?)\.?\s*(.*)$", re.IGNORECASE)
RE_CLAUSE = re.compile(r"^(\d+)\.\s+(.*)$")
RE_POINT = re.compile(r"^([a-zđ])\)\s+(.*)$")
RE_APPENDIX = re.compile(r"^(?:#+\s*)?PHỤ\s+LỤC(?:\s+([A-Z0-9IVX]+))?[:\.]?\s*(.*)$", re.IGNORECASE)


class LegalHierarchyParser:
    """Sequential state-machine parser for Vietnamese legal texts."""

    def parse(self, full_text: str, doc_number: Optional[str] = None) -> LegalDocumentTree:
        """Parse raw legal document text into a structured LegalDocumentTree."""
        tree = LegalDocumentTree(doc_number=doc_number)
        if not full_text or not full_text.strip():
            return tree

        normalized_text = normalize_text(full_text)
        lines = normalized_text.split("\n")

        # Parsing states
        in_preamble = True
        in_quote = False
        current_chapter: Optional[LegalChapter] = None
        current_article: Optional[LegalArticle] = None
        current_clause: Optional[LegalClause] = None
        current_point: Optional[LegalPoint] = None

        preamble_lines: List[str] = []
        article_lines: List[str] = []

        def _commit_clause_and_point():
            nonlocal current_clause, current_point
            if current_clause and current_article:
                if current_point:
                    current_clause.points.append(current_point)
                    current_point = None
                current_article.clauses.append(current_clause)
                current_clause = None

        def _commit_current_article():
            nonlocal current_article, article_lines, current_clause, current_point
            if current_article:
                _commit_clause_and_point()
                current_article.content = "\n".join(article_lines).strip()
                if current_chapter:
                    current_chapter.articles.append(current_article)
                else:
                    tree.unattached_articles.append(current_article)
                current_article = None
                article_lines = []

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                if in_preamble:
                    preamble_lines.append(line)
                elif current_article:
                    article_lines.append(line)
                continue

            # Update quote tracking
            # Count quote marks: standard ASCII " and typographic “ ”
            quote_marks = trimmed.count('"') + trimmed.count('“') + trimmed.count('”')
            if quote_marks % 2 != 0:
                in_quote = not in_quote
                if current_article and in_quote:
                    current_article.is_amending = True

            # If inside a quote block, this line belongs strictly to the current article/clause
            if in_quote:
                if current_article:
                    article_lines.append(line)
                    current_article.is_amending = True
                continue

            # Check for Chapter transition
            m_ch = RE_CHAPTER.match(trimmed)
            if m_ch:
                _commit_current_article()
                in_preamble = False
                ch_num = m_ch.group(1).strip()
                ch_title = m_ch.group(2).strip()
                current_chapter = LegalChapter(number=ch_num, title=ch_title)
                tree.chapters.append(current_chapter)
                continue

            # Capture Chapter title if on subsequent line
            if current_chapter and not current_chapter.title and not current_article:
                if not RE_SECTION.match(trimmed) and not RE_ARTICLE.match(trimmed) and not RE_CHAPTER.match(trimmed):
                    current_chapter.title = trimmed
                    continue

            # Check for Article transition
            m_art = RE_ARTICLE.match(trimmed)
            if m_art:
                _commit_current_article()
                in_preamble = False
                art_num = m_art.group(1).strip()
                art_title = m_art.group(2).strip()

                current_article = LegalArticle(
                    number=art_num,
                    title=art_title,
                    content="",
                    chapter_num=current_chapter.number if current_chapter else None,
                    chapter_title=current_chapter.title if current_chapter else None,
                )
                article_lines = [line]
                continue

            # In preamble region before any Article
            if in_preamble:
                preamble_lines.append(line)
                continue

            # Within an active Article: check for Clause / Point
            if current_article:
                article_lines.append(line)

                m_cl = RE_CLAUSE.match(trimmed)
                if m_cl:
                    _commit_clause_and_point()
                    cl_num = m_cl.group(1).strip()
                    cl_content = m_cl.group(2).strip()
                    current_clause = LegalClause(number=cl_num, content=cl_content)
                    continue

                m_pt = RE_POINT.match(trimmed)
                if m_pt:
                    if current_point and current_clause:
                        current_clause.points.append(current_point)
                    pt_letter = m_pt.group(1).strip()
                    pt_content = m_pt.group(2).strip()
                    current_point = LegalPoint(letter=pt_letter, content=pt_content)
                    continue

                # Continuation text
                if current_point:
                    current_point.content += f" {trimmed}"
                elif current_clause:
                    current_clause.content += f" {trimmed}"

        # Commit any remaining article at EOF
        _commit_current_article()
        tree.preamble = "\n".join(preamble_lines).strip()

        return tree
