"""Kiểm tra tệp tải lên: định dạng cho phép, chữ ký nội dung, macro, bom nén, giới hạn dung lượng ở tầng ASGI."""

import asyncio
import io
import json
import zipfile

import pytest

from app.services import upload_guard as g
from app.services.upload_limit import MULTIPART_OVERHEAD, UploadSizeLimitMiddleware

ALLOWED = g.DEFAULT_EXTENSIONS


def make_zip(parts: dict[str, bytes], compression=zipfile.ZIP_DEFLATED) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in parts.items():
            z.writestr(name, data)
    buf.seek(0)
    return buf


def docx(extra=None) -> io.BytesIO:
    return make_zip({"[Content_Types].xml": b"<x/>", "word/document.xml": b"<w/>", **(extra or {})})


def reject(name, fileobj, allowed=ALLOWED):
    with pytest.raises(g.UploadRejected) as err:
        g.validate(name, fileobj, allowed)
    return err.value


def test_valid_files_pass_and_stream_is_rewound():
    pdf = io.BytesIO(b"%PDF-1.7\n...")
    assert g.validate("bao cao.pdf", pdf, ALLOWED) == ("bao cao.pdf", "pdf") and pdf.tell() == 0
    assert g.validate("a.docx", docx(), ALLOWED)[1] == "docx"
    xlsx = make_zip({"[Content_Types].xml": b"<x/>", "xl/workbook.xml": b"<w/>"})
    assert g.validate("b.XLSX", xlsx, ALLOWED)[1] == "xlsx"
    pptx = make_zip({"[Content_Types].xml": b"<x/>", "ppt/presentation.xml": b"<w/>"})
    assert g.validate("c.pptx", pptx, ALLOWED)[1] == "pptx"
    assert g.validate("d.txt", io.BytesIO("Công an tỉnh Hưng Yên".encode()), ALLOWED)[1] == "txt"
    assert g.validate("e.csv", io.BytesIO(b"\xff\xfea\x00,\x00b\x00"), ALLOWED)[1] == "csv"


@pytest.mark.parametrize("name", ["virus.exe", "script.js", "noext", "archive.zip", "page.html", "x.pdf.exe", "bad."])
def test_extension_outside_allowlist_is_415(name):
    err = reject(name, io.BytesIO(b"%PDF-1.7"))
    assert err.status == 415 and err.code == "extension_not_allowed"


def test_legacy_office_is_off_by_default_but_can_be_enabled():
    ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100
    assert reject("a.doc", io.BytesIO(ole)).code == "extension_not_allowed"
    assert g.validate("a.doc", io.BytesIO(ole), g.parse_extensions("pdf, .DOC"))[1] == "doc"
    assert reject("a.doc", io.BytesIO(b"%PDF-1.7"), ("doc",)).code == "content_mismatch"


@pytest.mark.parametrize(
    "name,content",
    [
        ("fake.pdf", b"MZ\x90\x00 this is an exe"),
        ("fake.pdf", b"<html>not a pdf</html>"),
        ("fake.docx", b"plain text pretending to be word"),
        ("fake.docx", b"PK\x03\x04 truncated zip"),
        ("fake.txt", b"MZ\x90\x00\x03"),
        ("fake.txt", b"\x7fELF\x02\x01"),
        ("fake.txt", b"%PDF-1.4 real pdf renamed"),
        ("fake.md", b"text\x00with nul"),
        ("fake.csv", b"PK\x03\x04zip renamed"),
    ],
)
def test_content_must_match_the_declared_extension(name, content):
    err = reject(name, io.BytesIO(content))
    assert err.status == 415 and err.code == "content_mismatch"


def test_zip_that_is_not_the_declared_office_type_is_rejected():
    assert reject("a.xlsx", docx()).code == "content_mismatch"
    assert reject("a.docx", make_zip({"hello.txt": b"x"})).code == "content_mismatch"


def test_office_macros_are_rejected():
    err = reject("a.docx", docx({"word/vbaProject.bin": b"\x00"}))
    assert err.code == "macro_present"


def test_path_traversal_inside_the_package_is_rejected():
    assert reject("a.docx", docx({"../evil.xml": b"x"})).code == "archive_path"
    assert reject("a.docx", docx({"/abs.xml": b"x"})).code == "archive_path"


def test_zip_bomb_by_ratio_and_by_entry_count(monkeypatch):
    bomb = docx({"word/big.bin": b"\0" * (80 * 1024 * 1024)})
    assert reject("a.docx", bomb).code == "archive_bomb"
    monkeypatch.setattr(g, "MAX_ZIP_ENTRIES", 3)
    many = docx({f"word/p{i}.xml": b"x" for i in range(5)})
    assert reject("a.docx", many).code == "archive_bomb"


@pytest.mark.parametrize("raw", ["", None, "..", ".", "a\x00b.pdf", "a\nb.pdf", "x" * 201 + ".pdf"])
def test_bad_filenames(raw):
    assert reject(raw, io.BytesIO(b"%PDF-1.7")).code == "bad_filename"


def test_filename_keeps_only_the_last_path_segment():
    assert g.safe_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert g.safe_filename("C:\\Users\\a\\b.pdf") == "b.pdf"


def test_parse_extensions_defaults_when_blank():
    assert g.parse_extensions("") == g.DEFAULT_EXTENSIONS and g.parse_extensions(None) == g.DEFAULT_EXTENSIONS
    assert g.parse_extensions(" PDF, .docx ,pdf") == ("pdf", "docx")


# ---------------------------------------------------------------- size limit middleware


def run_request(limit, chunks, content_length=None, method="POST", path="/up"):
    calls = {"app_ran": False, "bytes": 0}

    async def app(scope, receive, send):
        calls["app_ran"] = True
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            calls["bytes"] += len(message["body"])
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent = []
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    headers = [(b"content-length", str(content_length).encode())] if content_length is not None else []
    middleware = UploadSizeLimitMiddleware(app, lambda m, p: limit if (m, p) == ("POST", "/up") else None)
    asyncio.run(middleware({"type": "http", "method": method, "path": path, "headers": headers}, receive, send))
    status = sent[0]["status"]
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body, calls


def test_declared_oversize_is_rejected_without_running_the_app():
    status, body, calls = run_request(1000, [b"x"], content_length=1000 + MULTIPART_OVERHEAD + 1)
    assert status == 413 and not calls["app_ran"] and "vượt quá" in json.loads(body)["detail"]


def test_streamed_oversize_without_content_length_is_cut_off():
    chunk = b"x" * (600 * 1024)
    status, _, calls = run_request(1000, [chunk, chunk, chunk])
    assert status == 413 and calls["bytes"] < 3 * len(chunk)


def test_within_limit_and_other_paths_pass_through():
    assert run_request(1000, [b"x" * 500], content_length=500)[0] == 200
    assert run_request(1000, [b"x" * (2 * MULTIPART_OVERHEAD)], path="/other")[0] == 200
    assert run_request(1000, [b"x" * (2 * MULTIPART_OVERHEAD)], method="GET")[0] == 200
