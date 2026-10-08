from datetime import date

from app.services.doc_metadata_service import (
    VALIDITY_ACTIVE,
    VALIDITY_EXPIRED,
    VALIDITY_PENDING,
    VALIDITY_REPLACED,
    VALIDITY_UNKNOWN,
    compute_validity,
    count_articles,
    regex_effective_date,
    to_iso_date,
)

TODAY = date(2026, 10, 8)


def test_to_iso_date_formats():
    assert to_iso_date("2025-12-31") == "2025-12-31"
    assert to_iso_date("ngày 31 tháng 12 năm 2025") == "2025-12-31"
    assert to_iso_date("Hà Nội, ngày 5 tháng 3 năm 2024") == "2024-03-05"
    assert to_iso_date("05/03/2024") == "2024-03-05"
    assert to_iso_date("31/02/2024") is None
    assert to_iso_date(None) is None
    assert to_iso_date("không rõ") is None


def test_regex_effective_date():
    issued = "2025-12-31"
    assert regex_effective_date("Quyết định này có hiệu lực kể từ ngày ký.", issued) == issued
    assert regex_effective_date(
        "Thông tư này có hiệu lực thi hành từ ngày 01 tháng 02 năm 2026.", issued
    ) == "2026-02-01"
    assert regex_effective_date("Không đề cập.", issued) is None


def test_count_articles():
    text = "Điều 1. Phạm vi\nnội dung\nĐiều 2. Đối tượng\nĐiều 2a. Bổ sung\ntham chiếu Điều 1 khác"
    assert count_articles(text) == 3


def test_compute_validity():
    assert compute_validity({}, today=TODAY) == VALIDITY_UNKNOWN
    assert compute_validity({"issued_date": "2025-01-01"}, today=TODAY) == VALIDITY_ACTIVE
    assert compute_validity({"effective_date": "2027-01-01"}, today=TODAY) == VALIDITY_PENDING
    assert compute_validity(
        {"effective_date": "2020-01-01", "expiry_date": "2021-01-01"}, today=TODAY
    ) == VALIDITY_EXPIRED
    assert compute_validity(
        {"effective_date": "2020-01-01"}, {"replaced_by": ["1/QĐ-BTC"]}, today=TODAY
    ) == VALIDITY_REPLACED
    assert compute_validity(
        {"effective_date": "2020-01-01"}, {"repealed_by": ["1/QĐ-BTC"]}, today=TODAY
    ) == VALIDITY_EXPIRED
