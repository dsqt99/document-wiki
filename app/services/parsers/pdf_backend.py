"""Lớp bọc mỏng quanh pypdfium2 (PDFium, giấy phép BSD-3-Clause / Apache-2.0) cho các thao tác PDF
dùng chung: mở tài liệu, đếm trang, lấy chữ thuần, kết xuất ảnh trang và duyệt ảnh nhúng.

Mọi chỗ trong ứng dụng cần đụng tới cấu trúc PDF đều đi qua module này; không import thư viện PDF
copyleft ở nơi khác.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

import pypdfium2 as pdfium
from PIL import Image
from pypdfium2.raw import FPDF_PAGEOBJ_IMAGE

# Tỷ lệ 2.0 tương đương 144 dpi: đủ nét cho OCR, dung lượng vừa phải.
DEFAULT_RENDER_SCALE = 2.0
DEFAULT_JPEG_QUALITY = 85


@dataclass(frozen=True)
class Rect:
    """Khung chữ nhật theo toạ độ trang (x0, y0, x1, y1)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height


class PdfPageView:
    """Hình chiếu nhẹ của một trang: kích thước và các khung ảnh.

    Đủ cho heuristic nhận diện trang scan mà không lộ đối tượng PDFium ra ngoài.
    """

    def __init__(self, page: pdfium.PdfPage):
        self._page = page
        width, height = page.get_size()
        self.rect = Rect(0.0, 0.0, float(width), float(height))
        self._image_rects: Optional[List[Rect]] = None

    def get_image_rects(self) -> List[Rect]:
        if self._image_rects is None:
            self._image_rects = page_image_rects(self._page)
        return self._image_rects


def open_document(data: bytes, password: Optional[str] = None) -> pdfium.PdfDocument:
    """Mở PDF từ bytes. Lỗi định dạng hay mật khẩu sẽ ném ``pypdfium2.PdfiumError``."""
    return pdfium.PdfDocument(data, password=password)


def page_count(data: bytes) -> int:
    doc = open_document(data)
    try:
        return len(doc)
    finally:
        doc.close()


def page_text(page: pdfium.PdfPage) -> str:
    """Chữ thuần của trang theo thứ tự PDFium xác định; xuống dòng chuẩn hoá thành ``\n``."""
    textpage = page.get_textpage()
    try:
        text = textpage.get_text_bounded() or ""
    finally:
        textpage.close()
    return text.replace("\r\n", "\n").replace("\r", "\n")


def page_image_rects(page: pdfium.PdfPage) -> List[Rect]:
    """Khung của mọi ảnh đặt trên trang (kể cả trong Form XObject), theo toạ độ trang."""
    rects: List[Rect] = []
    for obj in page.get_objects(filter=[FPDF_PAGEOBJ_IMAGE]):
        try:
            left, bottom, right, top = obj.get_bounds()
        except Exception:  # noqa: BLE001 - một ảnh hỏng không làm hỏng cả trang
            continue
        rects.append(Rect(float(left), float(bottom), float(right), float(top)))
    return rects


def render_page_jpeg(
    page: pdfium.PdfPage,
    scale: float = DEFAULT_RENDER_SCALE,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> bytes:
    """Kết xuất trang thành ảnh JPEG (RGB, không kênh alpha) để gửi OCR."""
    bitmap = page.render(scale=scale)
    try:
        image = bitmap.to_pil()
        if image.mode != "RGB":
            image = image.convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    finally:
        bitmap.close()


def _ink_bands(ink: Image.Image) -> int:
    """Số dải hàng có mực (quá 2% bề rộng) ngăn cách bởi hàng trắng; kẻ bảng 1-2px không tính."""
    width, data = ink.width, ink.tobytes()
    bands, prev = 0, False
    for y in range(ink.height):
        on = data[y * width:(y + 1) * width].count(255) > 0.02 * width
        bands += on and not prev
        prev = on
    return bands


def text_layout(jpeg: bytes) -> Tuple[int, bool]:
    """Ước lượng (số dòng chữ, trang xoay ngang) từ hồ sơ mực của ảnh trang.

    Chữ ngang cho nhiều dải hàng xen hàng trắng nhưng gần như không có cột trắng;
    trang scan khổ ngang đặt dọc thì ngược lại.
    """
    image = Image.open(io.BytesIO(jpeg)).convert("L")
    image = image.resize((800, max(1, round(800 * image.height / image.width))))
    ink = image.point(lambda p: 255 if p < 128 else 0)
    box = ink.getbbox()
    if not box:
        return 0, False
    ink = ink.crop(box)
    rows, cols = _ink_bands(ink), _ink_bands(ink.transpose(Image.Transpose.TRANSPOSE))
    # Vài dòng chữ ngắn cũng cho nhiều dải cột (khe giữa các chữ cái): chỉ tin khi mực trải cao trang.
    sideways = cols > rows and cols >= 8 and ink.height >= 0.25 * image.height
    return (cols if sideways else rows), sideways


def rotate_jpeg(jpeg: bytes, degrees: int, quality: int = DEFAULT_JPEG_QUALITY) -> bytes:
    """Xoay ảnh JPEG ngược chiều kim đồng hồ ``degrees`` độ."""
    buf = io.BytesIO()
    Image.open(io.BytesIO(jpeg)).rotate(degrees, expand=True).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def render_document_page_jpeg(data: bytes, page_index: int, **kwargs) -> Tuple[bytes, int]:
    """Kết xuất một trang (chỉ số từ 0) của PDF bytes. Trả về (jpeg, tổng số trang)."""
    doc = open_document(data)
    try:
        total = len(doc)
        page = doc[page_index]
        try:
            return render_page_jpeg(page, **kwargs), total
        finally:
            page.close()
    finally:
        doc.close()


_MAGIC_EXT = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "jp2"),
    (b"\xff\x4f\xff\x51", "jp2"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
    (b"GIF8", "gif"),
    (b"BM", "bmp"),
)


def image_extension(data: bytes) -> str:
    for magic, ext in _MAGIC_EXT:
        if data.startswith(magic):
            return ext
    return "png"


def iter_page_images(page: pdfium.PdfPage) -> Iterator[Tuple[str, bytes]]:
    """Duyệt ảnh nhúng của trang, mỗi ảnh một lần, dưới dạng (đuôi tệp, dữ liệu).

    JPEG / JPEG 2000 giữ nguyên dòng dữ liệu gốc; định dạng khác được mã hoá lại thành PNG.
    Ảnh lặp lại trên cùng trang (cùng nội dung) chỉ trả về một lần.
    """
    seen: set = set()
    for obj in page.get_objects(filter=[FPDF_PAGEOBJ_IMAGE]):
        try:
            buf = io.BytesIO()
            obj.extract(buf, fb_format="png")
            data = buf.getvalue()
        except Exception:  # noqa: BLE001 - bỏ qua ảnh không giải mã được
            continue
        if not data:
            continue
        digest = hashlib.sha1(data).digest()
        if digest in seen:
            continue
        seen.add(digest)
        yield image_extension(data), data
