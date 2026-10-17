"""pypdfium2 backend: số trang, lớp chữ, render trang, ảnh nhúng và xem trước trang ở Cài đặt."""

import io
from unittest.mock import patch

from PIL import Image

from pdf_fixtures import make_image_pdf, make_text_pdf
from app.routers.admin_settings import _render_pdf_page
from app.services import image_service
from app.services.parsers import pdf_backend

JPEG_MAGIC = b"\xff\xd8\xff"


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def test_page_count_and_text_layer():
    data = make_text_pdf([["Line A", "Line B"], ["Second page"]])
    assert pdf_backend.page_count(data) == 2
    doc = pdf_backend.open_document(data)
    try:
        assert _lines(pdf_backend.page_text(doc[0])) == ["Line A", "Line B"]
        assert _lines(pdf_backend.page_text(doc[1])) == ["Second page"]
        assert "\r" not in pdf_backend.page_text(doc[0])
        view = pdf_backend.PdfPageView(doc[0])
        assert (round(view.rect.width), round(view.rect.height)) == (595, 842)
        assert view.get_image_rects() == []
    finally:
        doc.close()


def test_render_page_jpeg_scales_page():
    doc = pdf_backend.open_document(make_text_pdf([["Render me"]]))
    try:
        jpeg = pdf_backend.render_page_jpeg(doc[0], scale=2.0)
    finally:
        doc.close()
    assert jpeg[:3] == JPEG_MAGIC
    assert Image.open(io.BytesIO(jpeg)).size == (1190, 1684)


def test_render_document_page_and_settings_preview():
    data = make_image_pdf(3)
    jpeg, total = pdf_backend.render_document_page_jpeg(data, 1)
    assert total == 3 and jpeg[:3] == JPEG_MAGIC

    jpeg, page_no, total, err = _render_pdf_page(data, 2)
    assert (page_no, total, err) == (2, 3, None)
    assert jpeg[:3] == JPEG_MAGIC
    assert _render_pdf_page(data, 99)[1:] == (3, 3, None)
    assert _render_pdf_page(data, 0)[1:] == (1, 3, None)

    jpeg, page_no, total, err = _render_pdf_page(b"not a pdf", 1)
    assert jpeg is None and total == 0
    assert err.startswith("Không thể render trang PDF")


def test_page_images_of_scanned_page():
    doc = pdf_backend.open_document(make_image_pdf(1))
    try:
        page = doc[0]
        rects = pdf_backend.page_image_rects(page)
        assert len(rects) == 1
        assert rects[0].area / pdf_backend.PdfPageView(page).rect.area > 0.9
        images = list(pdf_backend.iter_page_images(page))
    finally:
        doc.close()
    assert len(images) == 1
    ext, blob = images[0]
    assert ext == "jpg" and blob[:3] == JPEG_MAGIC
    assert pdf_backend.image_extension(b"\x89PNG\r\n\x1a\n\x00") == "png"
    assert pdf_backend.image_extension(b"GIF89a") == "gif"
    assert pdf_backend.image_extension(b"junk") == "png"


def test_extract_images_from_pdf_stores_each_page_image():
    stored = []
    with patch.object(image_service.storage_service, "upload_file", side_effect=lambda **kw: stored.append(kw)):
        infos = image_service.extract_images_from_pdf(make_image_pdf(2), "src-1")
        assert image_service.extract_images_from_pdf(make_text_pdf([["no images"]]), "src-2") == []
        assert image_service.extract_images_from_pdf(b"junk", "src-3") == []
    assert [i.minio_key for i in infos] == [
        "sources/src-1/images/page1_0.jpg",
        "sources/src-1/images/page2_1.jpg",
    ]
    assert [i.page_number for i in infos] == [1, 2]
    assert [i.image_index for i in infos] == [0, 1]
    assert all(i.content_type == "image/jpeg" for i in infos)
    assert [kw["object_name"] for kw in stored] == [i.minio_key for i in infos]
    assert all(kw["data"][:3] == JPEG_MAGIC and kw["content_type"] == "image/jpeg" for kw in stored)
    assert [i.size_bytes for i in infos] == [len(kw["data"]) for kw in stored]
