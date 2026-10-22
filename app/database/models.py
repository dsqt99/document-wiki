"""ORM models for every table in the knowledge base.

Do not import ``app.models`` at module level: ``app.models.concept_relation``
imports ``Base`` from here.
"""

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import HALFVEC, Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    case,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScopeType(str, enum.Enum):
    GLOBAL = "global"
    DEPARTMENT = "department"
    PERSONAL = "personal"


class SkillContributionStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING = "pending"
    NEEDS_REVISION = "needs_revision"
    WITHDRAWN = "withdrawn"
    APPROVED = "approved"
    REJECTED = "rejected"


WIKI_DRAFT_STATUSES = ("pending", "needs_revision", "withdrawn", "approved", "rejected")


class LegalUnitType(str, enum.Enum):
    PART = "part"
    CHAPTER = "chapter"
    SECTION = "section"
    ARTICLE = "article"
    CLAUSE = "clause"
    POINT = "point"


class LegalRelationType(str, enum.Enum):
    SUA_DOI = "sua_doi"
    BO_SUNG = "bo_sung"
    THAY_THE = "thay_the"
    BAI_BO = "bai_bo"
    HUONG_DAN = "huong_dan"
    CAN_CU = "can_cu"
    DAN_CHIEU = "dan_chieu"


class SkillStatus(str, enum.Enum):
    ACTIVE = "active"
    PROCESSING = "processing"
    DELETING = "deleting"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


SKILL_STATUS_VALUES = tuple(s.value for s in SkillStatus)
SECURITY_LEVELS = ("PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL")


# ---------------------------------------------------------------------------
# Column helpers
# ---------------------------------------------------------------------------


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def _updated() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _fk(target: str, ondelete: str, nullable: bool = True, index: bool = False) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index
    )


def _opt(type_: Any, **extra: Any) -> Any:
    """Nullable column of ``type_``."""
    return mapped_column(type_, nullable=True, **extra)


def _req(type_: Any, **extra: Any) -> Any:
    """NOT NULL column of ``type_``."""
    return mapped_column(type_, nullable=False, **extra)


def _dflt(type_: Any, value: Any, server: Optional[str] = None, **extra: Any) -> Any:
    """Column whose Python-side and server-side defaults agree."""
    server_value = server if server is not None else str(value)
    return mapped_column(type_, server_default=server_value, default=value, **extra)


def _opt_ts() -> Any:
    """Nullable timezone-aware timestamp."""
    return _opt(DateTime(timezone=True))


# Reserved wiki slugs that map to a dedicated page type; insertion order is
# the evaluation order of the SQL CASE expression.
_SPECIAL_PAGE_SLUGS: dict[str, str] = {"_index": "index", "_log": "log", "_hot": "hot"}
_SOURCE_SLUG_PREFIX = "source/"


def _clip_message(value: Optional[str]) -> Optional[str]:
    if value is not None and len(value) > 500:
        return value[:499] + "…"
    return value


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = _fk("departments.id", "SET NULL", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    employee_departments: Mapped[list["EmployeeDepartment"]] = relationship(
        back_populates="department", cascade="all, delete-orphan", passive_deletes=True
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="employee", server_default="employee")
    global_role: Mapped[str] = mapped_column(String(30), nullable=False, default="viewer", server_default="viewer")
    global_role_source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="manual", server_default="manual"
    )
    mcp_token: Mapped[Optional[str]] = mapped_column(String(500), unique=True, nullable=True)
    mcp_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mcp_token_prefix: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    mcp_token_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auth_provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    clearance_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    last_connected: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    employee_departments: Mapped[list["EmployeeDepartment"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", passive_deletes=True
    )
    departments: Mapped[list["Department"]] = relationship(
        secondary="employee_departments", viewonly=True
    )

    __table_args__ = (
        Index(
            "ix_employees_mcp_token_hash",
            "mcp_token_hash",
            unique=True,
            postgresql_where=text("mcp_token_hash IS NOT NULL"),
        ),
        Index(
            "ix_employees_external_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    @property
    def department_ids(self) -> list[uuid.UUID]:
        return [ed.department_id for ed in (self.employee_departments or [])]


class EmployeeDepartment(Base):
    __tablename__ = "employee_departments"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = _created()

    employee: Mapped["Employee"] = relationship(back_populates="employee_departments")
    department: Mapped["Department"] = relationship(back_populates="employee_departments")


class AppConfig(Base):
    """Key/value runtime settings editable from the admin UI."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = _opt(Text)
    updated_at: Mapped[datetime] = _updated()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


class KnowledgeType(Base):
    __tablename__ = "knowledge_types"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), default="#6366f1", server_default="#6366f1")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = _created()


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="global", server_default="global")
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    security_label: Mapped[str] = mapped_column(
        String(20), nullable=False, default="INTERNAL", server_default="INTERNAL"
    )
    knowledge_type_id: Mapped[Optional[uuid.UUID]] = _fk("knowledge_types.id", "SET NULL")
    managing_department_id: Mapped[Optional[uuid.UUID]] = _fk("departments.id", "SET NULL", index=True)
    contributed_by_employee_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    minio_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)

    status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    progress_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    chunk_status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    chunk_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    chunk_progress_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    chunk_attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    chunk_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    wiki_status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    wiki_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wiki_progress_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    wiki_attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    wiki_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    extracted_token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_recover_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    pipeline_strategy: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pipeline_phase: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    preserve_verbatim: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    outline_json: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    page_offsets: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    knowledge_type: Mapped[Optional["KnowledgeType"]] = relationship(lazy="selectin")
    managing_department: Mapped[Optional["Department"]] = relationship(foreign_keys=[managing_department_id], lazy="selectin")
    contributor: Mapped[Optional["Employee"]] = relationship(foreign_keys=[contributed_by_employee_id])
    departments: Mapped[list["SourceDepartment"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )
    images: Mapped[list["SourceImage"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )

    @validates("progress_message", "chunk_progress_message", "wiki_progress_message")
    def _validate_progress_message(self, key: str, value: Optional[str]) -> Optional[str]:
        return _clip_message(value)


class SourceDepartment(Base):
    __tablename__ = "source_departments"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True
    )

    source: Mapped["Source"] = relationship(back_populates="departments")
    department: Mapped["Department"] = relationship()


class SourceImage(Base):
    __tablename__ = "source_images"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", "CASCADE", nullable=False, index=True)
    minio_key: Mapped[str] = _req(Text)
    page_number: Mapped[Optional[int]] = _opt(Integer)
    image_index: Mapped[int] = _req(Integer)
    caption: Mapped[Optional[str]] = _opt(Text)
    content_type: Mapped[str] = _req(String(64))
    size_bytes: Mapped[int] = _req(Integer)
    created_at: Mapped[datetime] = _created()

    source: Mapped["Source"] = relationship(back_populates="images")

    __table_args__ = (UniqueConstraint("source_id", "image_index", name="uq_source_images_source_index"),)


class SourceCompilationPlan(Base):
    __tablename__ = "source_compilation_plans"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(
        String(30), default="pending_review", server_default="pending_review", index=True
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


# ---------------------------------------------------------------------------
# Wiki
# ---------------------------------------------------------------------------


class WikiPage(Base):
    __tablename__ = "wiki_pages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="seed", server_default="seed")
    content_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin_tag: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="global", server_default="global")
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    knowledge_type_slugs: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String), default=list, server_default=text("'{}'")
    )
    source_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, server_default=text("'{}'")
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    orphaned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    __table_args__ = (
        Index("ix_wiki_pages_status", "status"),
        Index("ix_wiki_pages_origin_scope", "origin_tag", "scope_type", "scope_id"),
        CheckConstraint("origin_tag IN ('extracted', 'generated')", name="ck_wiki_pages_origin_tag"),
    )

    @hybrid_property
    def page_type(self) -> str:
        slug = self.slug or ""
        special = _SPECIAL_PAGE_SLUGS.get(slug)
        if special is not None:
            return special
        return "source" if self.origin_tag == "extracted" or slug.startswith(_SOURCE_SLUG_PREFIX) else "concept"

    @page_type.inplace.expression
    @classmethod
    def _page_type_expression(cls):
        whens = [(cls.slug == slug, kind) for slug, kind in _SPECIAL_PAGE_SLUGS.items()]
        whens.append((cls.origin_tag == "extracted", "source"))
        whens.append((cls.slug.like(_SOURCE_SLUG_PREFIX + "%"), "source"))
        return case(*whens, else_="concept")


class WikiLink(Base):
    __tablename__ = "wiki_links"

    from_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="CASCADE"), primary_key=True
    )
    to_slug: Mapped[str] = mapped_column(String(300), primary_key=True)


class WikiPageRevision(Base):
    __tablename__ = "wiki_page_revisions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    page_id: Mapped[uuid.UUID] = _fk("wiki_pages.id", "CASCADE", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    changed_by_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    change_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (UniqueConstraint("page_id", "version", name="uq_wiki_page_revisions_page_version"),)


class WikiBranch(Base):
    __tablename__ = "wiki_branches"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = _req(String(100))
    description: Mapped[Optional[str]] = _opt(Text)
    scope_type: Mapped[str] = _dflt(String(20), "global")
    scope_id: Mapped[Optional[uuid.UUID]] = _opt(UUID(as_uuid=True))
    author_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    status: Mapped[str] = _dflt(String(20), "draft")
    has_conflict: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    reviewer_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    reviewed_at: Mapped[Optional[datetime]] = _opt_ts()
    reviewer_note: Mapped[Optional[str]] = _opt(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class WikiPageDraft(Base):
    __tablename__ = "wiki_page_drafts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    page_id: Mapped[Optional[uuid.UUID]] = _fk("wiki_pages.id", "CASCADE", index=True)
    draft_kind: Mapped[str] = _dflt(String(20), "edit")
    suggested_metadata: Mapped[Optional[dict]] = _opt(JSONB)
    author_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL", index=True)
    content_md: Mapped[Optional[str]] = _opt(Text)
    note: Mapped[Optional[str]] = _opt(Text)
    base_version: Mapped[Optional[int]] = _opt(Integer)
    revision_round: Mapped[int] = _dflt(Integer, 0)
    last_returned_note: Mapped[Optional[str]] = _opt(Text)
    ai_check_status: Mapped[str] = _dflt(String(20), "pending")
    ai_check_results: Mapped[Optional[Any]] = _opt(JSONB)
    ai_checked_at: Mapped[Optional[datetime]] = _opt_ts()
    status: Mapped[str] = _dflt(String(20), "pending", index=True)
    source: Mapped[str] = _dflt(String(40), "web_ui")
    source_metadata: Mapped[Optional[dict]] = _opt(JSONB)
    branch_id: Mapped[Optional[uuid.UUID]] = _fk("wiki_branches.id", "SET NULL")
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    reviewed_at: Mapped[Optional[datetime]] = _opt_ts()
    reviewer_note: Mapped[Optional[str]] = _opt(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    page: Mapped[Optional["WikiPage"]] = relationship(lazy="selectin")
    author: Mapped[Optional["Employee"]] = relationship(foreign_keys=[author_id], lazy="selectin")
    reviewer: Mapped[Optional["Employee"]] = relationship(foreign_keys=[reviewed_by_id], lazy="selectin")


class WikiDraftRound(Base):
    __tablename__ = "wiki_draft_rounds"

    id: Mapped[uuid.UUID] = _uuid_pk()
    draft_id: Mapped[uuid.UUID] = _fk("wiki_page_drafts.id", "CASCADE", nullable=False, index=True)
    round_no: Mapped[int] = _req(Integer, default=0)
    content_md: Mapped[Optional[str]] = _opt(Text)
    author_note: Mapped[Optional[str]] = _opt(Text)
    reviewer_return_note: Mapped[Optional[str]] = _opt(Text)
    ai_check_results: Mapped[Optional[Any]] = _opt(JSONB)
    submitted_at: Mapped[datetime] = _created()


class SourceChunkExtract(Base):
    __tablename__ = "source_chunk_extracts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", "CASCADE", nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_char: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extract_json: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_index", name="uq_source_chunk_extracts_source_chunk"),
        Index("ix_source_chunk_extracts_source_status", "source_id", "status"),
    )


# ---------------------------------------------------------------------------
# Legal graph
# ---------------------------------------------------------------------------


class LegalUnit(Base):
    __tablename__ = "legal_units"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = _fk("sources.id", "CASCADE", nullable=False, index=True)
    wiki_page_id: Mapped[Optional[uuid.UUID]] = _fk("wiki_pages.id", "SET NULL", index=True)
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    unit_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    full_path: Mapped[str] = mapped_column(String(500), default="", server_default="")
    content: Mapped[str] = mapped_column(Text, default="", server_default="")
    parent_unit_id: Mapped[Optional[uuid.UUID]] = _fk("legal_units.id", "CASCADE", index=True)
    doc_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    source: Mapped["Source"] = relationship()
    wiki_page: Mapped[Optional["WikiPage"]] = relationship()
    parent: Mapped[Optional["LegalUnit"]] = relationship(
        remote_side="LegalUnit.id", back_populates="children"
    )
    children: Mapped[list["LegalUnit"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )
    outgoing_relations: Mapped[list["LegalRelation"]] = relationship(
        foreign_keys="LegalRelation.source_unit_id",
        back_populates="source_unit",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incoming_relations: Mapped[list["LegalRelation"]] = relationship(
        foreign_keys="LegalRelation.target_unit_id",
        back_populates="target_unit",
    )

    __table_args__ = (
        Index("ix_legal_units_doc_type_number", "doc_number", "unit_type", "unit_number"),
    )


class LegalRelation(Base):
    __tablename__ = "legal_relations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_unit_id: Mapped[uuid.UUID] = _fk("legal_units.id", "CASCADE", nullable=False, index=True)
    target_unit_id: Mapped[Optional[uuid.UUID]] = _fk("legal_units.id", "SET NULL", index=True)
    target_doc_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    target_article_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    target_clause_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    quote_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_effective: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), index=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    source_unit: Mapped["LegalUnit"] = relationship(
        foreign_keys=[source_unit_id], back_populates="outgoing_relations"
    )
    target_unit: Mapped[Optional["LegalUnit"]] = relationship(
        foreign_keys=[target_unit_id], back_populates="incoming_relations"
    )

    __table_args__ = (
        Index("ix_legal_relations_target_doc_article", "target_doc_number", "target_article_number"),
    )


# ---------------------------------------------------------------------------
# Embedding tables, one set per supported dimension
# ---------------------------------------------------------------------------

EMBEDDING_TABLE_DIMENSIONS = (768, 1024, 1536, 3072)


def _vector_type(dim: int):
    return HALFVEC(dim) if dim == 3072 else Vector(dim)


_PAGE_EMBEDDING_MODELS: dict[int, type] = {}
_SOURCE_CHUNK_EMBEDDING_MODELS: dict[int, type] = {}
_WIKI_CHUNK_EMBEDDING_MODELS: dict[int, type] = {}


def _make_page_embedding(dim: int) -> type:
    attrs = {
        "__tablename__": f"wiki_page_embeddings_{dim}",
        "__annotations__": {},
        "page_id": mapped_column(
            UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="CASCADE"), primary_key=True
        ),
        "model_spec_id": mapped_column(String(128), primary_key=True),
        "content_hash": mapped_column(String(64), nullable=False),
        "embedded_at": mapped_column(DateTime(timezone=True), server_default=func.now()),
        "embedding": mapped_column(_vector_type(dim), nullable=True),
        "dimension": dim,
    }
    return type(f"WikiPageEmbedding{dim}", (Base,), attrs)


def _make_source_chunk_embedding(dim: int) -> type:
    attrs = {
        "__tablename__": f"source_chunk_embeddings_{dim}",
        "__annotations__": {},
        "source_id": mapped_column(
            UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
        ),
        "chunk_index": mapped_column(Integer, primary_key=True),
        "model_spec_id": mapped_column(String(128), primary_key=True),
        "start_char": mapped_column(Integer, nullable=True),
        "end_char": mapped_column(Integer, nullable=True),
        "page_number": mapped_column(Integer, default=1, server_default="1"),
        "text": mapped_column(Text, nullable=True),
        "content_hash": mapped_column(String(64), nullable=True),
        "embedded_at": mapped_column(DateTime(timezone=True), server_default=func.now()),
        "embedding": mapped_column(_vector_type(dim), nullable=True),
        "dimension": dim,
    }
    return type(f"SourceChunkEmbedding{dim}", (Base,), attrs)


def _make_wiki_chunk_embedding(dim: int) -> type:
    attrs = {
        "__tablename__": f"wiki_page_chunk_embeddings_{dim}",
        "__annotations__": {},
        "page_id": mapped_column(
            UUID(as_uuid=True), ForeignKey("wiki_pages.id", ondelete="CASCADE"), primary_key=True
        ),
        "chunk_index": mapped_column(Integer, primary_key=True),
        "model_spec_id": mapped_column(String(128), primary_key=True),
        "heading_path": mapped_column(Text, default="", server_default=""),
        "text": mapped_column(Text, nullable=True),
        "content_hash": mapped_column(String(64), nullable=True),
        "embedded_at": mapped_column(DateTime(timezone=True), server_default=func.now()),
        "embedding": mapped_column(_vector_type(dim), nullable=True),
        "dimension": dim,
    }
    return type(f"WikiPageChunkEmbedding{dim}", (Base,), attrs)


for _dim in EMBEDDING_TABLE_DIMENSIONS:
    _PAGE_EMBEDDING_MODELS[_dim] = _make_page_embedding(_dim)
    _SOURCE_CHUNK_EMBEDDING_MODELS[_dim] = _make_source_chunk_embedding(_dim)
    _WIKI_CHUNK_EMBEDDING_MODELS[_dim] = _make_wiki_chunk_embedding(_dim)
    globals()[_PAGE_EMBEDDING_MODELS[_dim].__name__] = _PAGE_EMBEDDING_MODELS[_dim]
    globals()[_SOURCE_CHUNK_EMBEDDING_MODELS[_dim].__name__] = _SOURCE_CHUNK_EMBEDDING_MODELS[_dim]
    globals()[_WIKI_CHUNK_EMBEDDING_MODELS[_dim].__name__] = _WIKI_CHUNK_EMBEDDING_MODELS[_dim]
del _dim


def _lookup(table: dict[int, type], dim: int) -> type:
    try:
        return table[int(dim)]
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Unsupported embedding dimension: {dim}") from None


def get_embedding_model_for_dim(dim: int) -> type:
    return _lookup(_PAGE_EMBEDDING_MODELS, dim)


def get_source_chunk_embedding_model_for_dim(dim: int) -> type:
    return _lookup(_SOURCE_CHUNK_EMBEDDING_MODELS, dim)


def get_wiki_page_chunk_embedding_model_for_dim(dim: int) -> type:
    return _lookup(_WIKI_CHUNK_EMBEDDING_MODELS, dim)


class EmbeddingJob(Base):
    __tablename__ = "embedding_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    model_spec_id: Mapped[str] = _req(String(128))
    status: Mapped[str] = _dflt(String(20), "pending")
    total_pages: Mapped[Optional[int]] = _opt(Integer)
    done_pages: Mapped[int] = _dflt(Integer, 0)
    error_message: Mapped[Optional[str]] = _opt(Text)
    started_at: Mapped[Optional[datetime]] = _opt_ts()
    finished_at: Mapped[Optional[datetime]] = _opt_ts()
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_embedding_jobs_status_created", "status", "created_at"),)


# ---------------------------------------------------------------------------
# Skills and prompts
# ---------------------------------------------------------------------------

skill_status_enum = SAEnum(
    *SKILL_STATUS_VALUES, name="skill_status", create_type=True, validate_strings=False
)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), default="global", server_default="global")
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    version_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(skill_status_enum, default="active", server_default="active")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", passive_deletes=True
    )
    skill_departments: Mapped[list["SkillDepartment"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def department_ids(self) -> list[uuid.UUID]:
        return [sd.department_id for sd in (self.skill_departments or [])]


class SkillDepartment(Base):
    __tablename__ = "skill_departments"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True
    )

    skill: Mapped["Skill"] = relationship(back_populates="skill_departments")
    department: Mapped["Department"] = relationship()


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    skill_id: Mapped[uuid.UUID] = _fk("skills.id", "CASCADE", nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    created_at: Mapped[datetime] = _created()

    skill: Mapped["Skill"] = relationship(back_populates="versions")


class SkillContribution(Base):
    __tablename__ = "skill_contributions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    skill_id: Mapped[Optional[uuid.UUID]] = _fk("skills.id", "CASCADE")
    contributor_id: Mapped[uuid.UUID] = _fk("employees.id", "CASCADE", nullable=False)
    base_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)
    revision_round: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_returned_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="global", server_default="global")
    scope_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    skill: Mapped[Optional["Skill"]] = relationship()
    contributor: Mapped["Employee"] = relationship()


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    command: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default=text("'{}'"))
    scope_type: Mapped[str] = mapped_column(String(20), default="personal", server_default="personal")
    department_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list, server_default=text("'{}'")
    )
    owner_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL", index=True)
    source: Mapped[str] = mapped_column(String(20), default="wiki", server_default="wiki")
    external_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    owner: Mapped[Optional["Employee"]] = relationship()


# ---------------------------------------------------------------------------
# Notifications, MCP log, stats, audit
# ---------------------------------------------------------------------------


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    recipient_id: Mapped[uuid.UUID] = _fk("employees.id", "CASCADE", nullable=False)
    type: Mapped[str] = _req(String(80))
    subject: Mapped[str] = _req(String(200))
    body: Mapped[str] = _dflt(Text, "")
    target_type: Mapped[Optional[str]] = _opt(String(40))
    target_id: Mapped[Optional[str]] = _opt(String(100))
    actor_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL")
    read_at: Mapped[Optional[datetime]] = _opt_ts()
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        Index("ix_notifications_recipient_read", "recipient_id", "read_at"),
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_target", "target_type", "target_id"),
    )


class MCPQueryLog(Base):
    __tablename__ = "mcp_query_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    employee_id: Mapped[Optional[uuid.UUID]] = _fk("employees.id", "SET NULL", index=True)
    tool_name: Mapped[str] = _req(String(80), index=True)
    query_text: Mapped[Optional[str]] = _opt(Text)
    result_count: Mapped[Optional[int]] = _opt(Integer)
    latency_ms: Mapped[Optional[int]] = _opt(Integer)
    scope_metadata: Mapped[Optional[dict]] = _opt(JSONB)
    result_ids: Mapped[Optional[list]] = _opt(JSONB)
    status: Mapped[str] = _dflt(String(20), "ok")
    error_message: Mapped[Optional[str]] = _opt(Text)

    __table_args__ = (Index("ix_mcp_query_log_created_result", "created_at", "result_count"),)


class StatsDailyRollup(Base):
    __tablename__ = "stats_daily_rollup"

    id: Mapped[uuid.UUID] = _uuid_pk()
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dimensions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    dimensions_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_json: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("date", "metric_key", "dimensions_hash", name="uq_stats_rollup_keys"),
        Index("ix_stats_daily_rollup_date", "date"),
        Index("ix_stats_daily_rollup_metric_date", "metric_key", "date"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    seq: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    principal_type: Mapped[str] = mapped_column(String(20), default="human", server_default="human")
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_audit_log_timestamp", "timestamp"),
        Index("ix_audit_log_principal", "principal_id"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
        Index("ix_audit_log_trace_id", "trace_id"),
    )


class AuditChainHead(Base):
    __tablename__ = "audit_chain_head"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_seq: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    last_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    key_fingerprint: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    signature: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

