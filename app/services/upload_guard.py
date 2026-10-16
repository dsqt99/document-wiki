"""Kiểm tra tệp tải lên: tên tệp, danh sách định dạng cho phép, chữ ký nội dung (magic bytes), bom nén.

Đuôi tệp chỉ là lời khai của người gửi; nội dung phải khớp định dạng đã khai. Hàm trong module này thuần túy
(không đụng DB hay HTTP) và ném `UploadRejected` với mã lỗi ổn định để router ghi kiểm vết và trả về HTTP tương ứng.
"""

import os
import re
import zipfile
from typing import BinaryIO, Iterable, Optional

DEFAULT_EXTENSIONS = ("pdf", "docx", "xlsx", "pptx", "txt", "md", "csv")

# Phần bắt buộc của từng gói OOXML: thiếu thì không phải tệp Office hợp lệ dù có chữ ký ZIP.
OOXML_REQUIRED_PART = {
    "docx": "word/document.xml",
    "xlsx": "xl/workbook.xml",
    "pptx": "ppt/presentation.xml",
}
# Macro VBA nhúng sẵn là vectơ tấn công điển hình của tệp Office; hệ thống không cần macro để đọc dữ liệu.
MACRO_PARTS = ("vbaproject.bin", "vbadata.xml")

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06")
# Chữ ký tệp thực thi/nén không được lẫn vào tệp văn bản.
BINARY_MAGICS = (
    b"MZ", b"\x7fELF", b"PK\x03\x04", b"%PDF-", OLE_MAGIC, b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe",
    b"Rar!", b"7z\xbc\xaf", b"\x1f\x8b", b"#!",
)
TEXT_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")
TEXT_TYPES = ("txt", "md", "csv")

MAX_ZIP_ENTRIES = 5000
MAX_ZIP_RATIO = 200
SNIFF_BYTES = 8192

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class UploadRejected(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def parse_extensions(value: Optional[str]) -> tuple[str, ...]:
    """Danh sách đuôi tệp cho phép từ chuỗi cấu hình (phân tách bằng dấu phẩy); rỗng thì dùng mặc định."""
    items = tuple(dict.fromkeys(p.strip().lstrip(".").lower() for p in (value or "").split(",") if p.strip()))
    return items or DEFAULT_EXTENSIONS


def safe_filename(raw: Optional[str]) -> str:
    """Tên tệp chỉ gồm phần cuối đường dẫn, không ký tự điều khiển; không rỗng."""
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    if not name or name in (".", "..") or _CONTROL.search(name):
        raise UploadRejected(400, "bad_filename", "Tên tệp không hợp lệ.")
    if len(name) > 200:
        raise UploadRejected(400, "bad_filename", "Tên tệp quá dài (tối đa 200 ký tự).")
    return name


def extension_of(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_extension(name: str, allowed: Iterable[str]) -> str:
    ext = extension_of(name)
    allowed = tuple(allowed)
    if not ext or ext not in allowed:
        raise UploadRejected(
            415,
            "extension_not_allowed",
            f"Định dạng .{ext or '(không có)'} không được phép. Chỉ nhận: {', '.join('.' + a for a in allowed)}.",
        )
    return ext


def _check_text(head: bytes) -> None:
    if head.startswith(TEXT_BOMS):
        return  # UTF-8/UTF-16 có BOM: chứa byte 0 là bình thường
    if any(head.startswith(m) for m in BINARY_MAGICS) or b"\x00" in head:
        raise UploadRejected(415, "content_mismatch", "Nội dung không phải văn bản thuần như đuôi tệp đã khai.")


def _check_zip(ext: str, fileobj: BinaryIO) -> None:
    try:
        with zipfile.ZipFile(fileobj) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise UploadRejected(415, "archive_bomb", "Gói Office chứa quá nhiều thành phần.")
            names = {i.filename.lower() for i in infos}
            for info in infos:
                if info.filename.startswith(("/", "\\")) or ".." in info.filename.replace("\\", "/").split("/"):
                    raise UploadRejected(415, "archive_path", "Gói Office chứa đường dẫn không an toàn.")
            if any(n.rsplit("/", 1)[-1] in MACRO_PARTS for n in names):
                raise UploadRejected(415, "macro_present", "Tệp Office chứa macro; không được phép tải lên.")
            if OOXML_REQUIRED_PART[ext] not in names or "[content_types].xml" not in names:
                raise UploadRejected(415, "content_mismatch", f"Nội dung không phải tệp .{ext} hợp lệ.")
            packed = sum(i.compress_size for i in infos) or 1
            unpacked = sum(i.file_size for i in infos)
            if unpacked > MAX_ZIP_RATIO * packed and unpacked > 50 * 1024 * 1024:
                raise UploadRejected(415, "archive_bomb", "Tệp nén có tỷ lệ giải nén bất thường.")
    except zipfile.BadZipFile:
        raise UploadRejected(415, "content_mismatch", f"Nội dung không phải tệp .{ext} hợp lệ.")


def check_content(ext: str, fileobj: BinaryIO) -> None:
    """Đối chiếu nội dung với đuôi tệp đã khai. `fileobj` phải tìm kiếm được; vị trí đọc được trả về đầu tệp."""
    fileobj.seek(0)
    head = fileobj.read(SNIFF_BYTES)
    try:
        if ext == "pdf":
            if b"%PDF-" not in head[:1024]:
                raise UploadRejected(415, "content_mismatch", "Nội dung không phải PDF hợp lệ.")
        elif ext in OOXML_REQUIRED_PART:
            if not head.startswith(ZIP_MAGICS):
                raise UploadRejected(415, "content_mismatch", f"Nội dung không phải tệp .{ext} hợp lệ.")
            fileobj.seek(0)
            _check_zip(ext, fileobj)
        elif ext in ("doc", "xls", "ppt"):
            if not head.startswith(OLE_MAGIC):
                raise UploadRejected(415, "content_mismatch", f"Nội dung không phải tệp .{ext} hợp lệ.")
        elif ext == "rtf":
            if not head.lstrip().startswith(b"{\\rtf"):
                raise UploadRejected(415, "content_mismatch", "Nội dung không phải RTF hợp lệ.")
        elif ext in TEXT_TYPES:
            _check_text(head)
        else:
            raise UploadRejected(415, "extension_not_allowed", f"Định dạng .{ext} chưa được hỗ trợ kiểm tra nội dung.")
    finally:
        fileobj.seek(0)


def validate(raw_name: Optional[str], fileobj: BinaryIO, allowed: Iterable[str]) -> tuple[str, str]:
    """Tên tệp an toàn và đuôi tệp đã được xác nhận khớp nội dung."""
    name = safe_filename(raw_name)
    ext = check_extension(name, allowed)
    check_content(ext, fileobj)
    return name, ext
