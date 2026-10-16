"""Nhãn bảo mật tài liệu và mức tiếp cận của người dùng (PUBLIC < INTERNAL < RESTRICTED < CONFIDENTIAL).

Tài liệu (`sources.security_label`) chỉ hiện cho người có mức tiếp cận (`clearance`) ≥ nhãn.
Trang wiki không có nhãn riêng: nó kế thừa nhãn cao nhất trong các nguồn tạo ra nó
(`wiki_pages.source_ids`), nên bị ẩn nếu bất kỳ nguồn nào vượt mức tiếp cận. Bộ lọc nằm trong
chính câu truy vấn (SQL) chứ không lọc sau khi lấy kết quả.

Thiếu hoặc sai giá trị thì coi là INTERNAL (mặc định của Trợ lý ảo AI).
"""

from typing import Optional

from sqlalchemy import and_, any_, exists, select

LEVELS: tuple[str, ...] = ("PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL")
DEFAULT_LEVEL = "INTERNAL"


def normalize(level: Optional[str]) -> str:
    value = (level or "").strip().upper()
    return value if value in LEVELS else DEFAULT_LEVEL


def allowed_labels(clearance: Optional[str]) -> list[str]:
    """Các nhãn mà mức tiếp cận `clearance` được xem."""
    return list(LEVELS[: LEVELS.index(normalize(clearance)) + 1])


def describe(clearance: Optional[str]) -> str:
    """Điều kiện ACL đã áp dụng, để ghi vào dấu vết/kết quả truy xuất."""
    level = normalize(clearance)
    return f"security_label ∈ {{{', '.join(allowed_labels(level))}}} (clearance={level})"


def source_label_clause(clearance: Optional[str]):
    """Điều kiện trên bảng Source."""
    from app.database.models import Source

    return Source.security_label.in_(allowed_labels(clearance))


def page_label_clause(clearance: Optional[str]):
    """Điều kiện trên WikiPage: không có nguồn nào vượt mức tiếp cận."""
    from app.database.models import Source, WikiPage

    return ~exists(
        select(1).where(
            and_(
                Source.id == any_(WikiPage.source_ids),
                Source.security_label.notin_(allowed_labels(clearance)),
            )
        )
    )

