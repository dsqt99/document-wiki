"""DOCX pictures keep their position: parser placeholder → image:// marker."""

import io
import struct
import zlib

import pytest

docx = pytest.importorskip("docx")

from app.services.image_service import ImageInfo, docx_image_blobs
from app.services.kb_service import _inline_image_markers
from app.services.parsers.docx_parser import DocxParser


def _png(w: int = 64, h: int = 64) -> bytes:
    """Noisy RGB PNG (> 2KB so it is not filtered as an icon)."""
    import os

    raw = b"".join(b"\x00" + os.urandom(w * 3) for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _guide_docx() -> bytes:
    d = docx.Document()
    d.add_paragraph("Bước 1: Truy cập trang web dịch vụ công.")
    d.add_picture(io.BytesIO(_png()))
    d.add_paragraph("Hình 1")
    d.add_paragraph("Bước 2: Ấn Đăng nhập.")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_docx_picture_lands_between_its_paragraphs():
    data = _guide_docx()
    pages = await DocxParser().parse(data, "guide.docx")
    text = pages[0]["content"]
    assert "<!--img:" in text

    blobs = docx_image_blobs(data)
    assert len(blobs) == 1
    rid = next(iter(blobs))
    img = ImageInfo("k", None, 0, "image/png", 3000, image_id="11111111-1111-1111-1111-111111111111", ref=rid)

    _inline_image_markers(pages, [img])
    out = pages[0]["content"]
    marker = "](image://11111111-1111-1111-1111-111111111111)"
    assert out.count(marker) == 1
    assert out.index("Bước 1") < out.index(marker) < out.index("Hình 1") < out.index("Bước 2")
    assert "<!--img:" not in out


@pytest.mark.asyncio
async def test_unkept_picture_placeholders_are_stripped():
    pages = await DocxParser().parse(_guide_docx(), "guide.docx")
    _inline_image_markers(pages, [])  # e.g. image under the size threshold
    assert "<!--img:" not in pages[0]["content"]
    assert "Bước 1" in pages[0]["content"]


def test_preview_inlines_data_uri_and_respects_budget():
    from app.routers.admin_settings import _preview_images

    blobs = {"rId9": ("image/png", b"x" * 4096)}
    out = _preview_images("A <!--img:rId9--> B <!--img:rIdX-->", blobs, [10_000])
    assert "data:image/png;base64," in out and "<!--img:" not in out
    over = _preview_images("<!--img:rId9-->", blobs, [100])
    assert "data:" not in over and "quá dung lượng" in over
