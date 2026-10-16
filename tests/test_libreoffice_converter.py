import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.parsers.libreoffice_converter import LibreOfficeConverter


@pytest.mark.asyncio
async def test_libreoffice_converter_is_available():
    """Verify is_available checks standard binary paths."""
    with patch("shutil.which", return_value="/usr/bin/soffice"):
        conv = LibreOfficeConverter()
        assert conv.is_available() is True

    with patch("shutil.which", return_value=None), \
         patch("os.path.exists", return_value=False):
        conv = LibreOfficeConverter()
        assert conv.is_available() is False


@pytest.mark.asyncio
async def test_libreoffice_convert_to_pdf_success(tmp_path):
    """Verify convert_to_pdf invokes headless subprocess and returns pdf bytes."""
    fake_doc_bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 sample doc"
    fake_pdf_bytes = b"%PDF-1.5 converted content"

    conv = LibreOfficeConverter()

    # Mock subprocess creation
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"")
    mock_proc.returncode = 0

    async def _mock_subprocess(*args, **kwargs):
        # Write dummy output pdf file to the outdir specified in args
        outdir = args[args.index("--outdir") + 1]
        import os
        with open(os.path.join(outdir, "input.pdf"), "wb") as f:
            f.write(fake_pdf_bytes)
        return mock_proc

    with patch.object(conv, "is_available", return_value=True), \
         patch.object(conv, "_get_binary", return_value="soffice"), \
         patch("asyncio.create_subprocess_exec", side_effect=_mock_subprocess):

        res_pdf = await conv.convert_to_pdf(fake_doc_bytes, "doc")
        assert res_pdf == fake_pdf_bytes


@pytest.mark.asyncio
async def test_libreoffice_convert_timeout():
    """Verify convert_to_pdf raises TimeoutError if subprocess exceeds timeout."""
    conv = LibreOfficeConverter()

    mock_proc = AsyncMock()
    mock_proc.communicate.side_effect = asyncio.TimeoutError()
    mock_proc.kill = MagicMock()

    with patch.object(conv, "is_available", return_value=True), \
         patch.object(conv, "_get_binary", return_value="soffice"), \
         patch("asyncio.create_subprocess_exec", return_value=mock_proc):

        with pytest.raises(TimeoutError):
            await conv.convert_to_pdf(b"dummy", "doc", timeout=1)


@pytest.mark.asyncio
async def test_extract_text_from_doc_calls_converter_and_pdf_parser():
    """Verify _extract_text_from_file automatically converts .doc to PDF and parses it."""
    from app.services.kb_service import _extract_text_from_file

    fake_doc_data = b"fake doc data"
    fake_pdf_data = b"%PDF-1.5 converted"

    mock_conv = MagicMock()
    mock_conv.is_available.return_value = True
    mock_conv.convert_to_pdf = AsyncMock(return_value=fake_pdf_data)

    mock_pdf_parser = AsyncMock()
    mock_pdf_parser.parse.return_value = [{"content": "Extracted doc content", "page_number": 1}]

    with patch("app.services.parsers.libreoffice_converter.libreoffice_converter", mock_conv), \
         patch("app.services.parsers.pdf_parser.PDFParser", return_value=mock_pdf_parser):

        result = await _extract_text_from_file(fake_doc_data, "sample.doc")
        assert len(result) == 1
        assert result[0]["content"] == "Extracted doc content"
        mock_conv.convert_to_pdf.assert_called_once_with(fake_doc_data, "doc")
