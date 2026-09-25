"""LibreOffice headless converter for legacy office formats (.doc, .ppt, .xls, .rtf)."""

import asyncio
import os
import shutil
import tempfile
from typing import Optional
from loguru import logger

# Common installation paths across Windows and Linux
KNOWN_BINARY_PATHS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/libreoffice",
    "/usr/bin/soffice",
    "/usr/local/bin/libreoffice",
    "/usr/local/bin/soffice",
]


class LibreOfficeConverter:
    """Headless LibreOffice subprocess converter to PDF."""

    def __init__(self):
        self._binary_path: Optional[str] = None

    def _get_binary(self) -> Optional[str]:
        """Locate the LibreOffice / soffice executable."""
        if self._binary_path and os.path.exists(self._binary_path):
            return self._binary_path

        # Check PATH first
        for name in ("soffice", "libreoffice"):
            found = shutil.which(name)
            if found:
                self._binary_path = found
                return found

        # Check known installation paths
        for path in KNOWN_BINARY_PATHS:
            if os.path.exists(path):
                self._binary_path = path
                return path

        return None

    def is_available(self) -> bool:
        """Check if LibreOffice is installed and executable."""
        return self._get_binary() is not None

    async def convert_to_pdf(
        self,
        input_bytes: bytes,
        src_extension: str,
        timeout: int = 45,
    ) -> bytes:
        """Convert input binary file bytes to PDF bytes via headless LibreOffice.

        Args:
            input_bytes: Raw bytes of the source file.
            src_extension: Extension without dot (e.g. 'doc', 'ppt', 'rtf').
            timeout: Subprocess timeout in seconds (default 45s).

        Returns:
            Converted PDF bytes.

        Raises:
            RuntimeError: If LibreOffice is not available or conversion fails.
            TimeoutError: If subprocess exceeds timeout.
        """
        binary = self._get_binary()
        if not binary:
            raise RuntimeError(
                "LibreOffice không có trên hệ thống. Vui lòng cài đặt LibreOffice hoặc chuyển đổi file sang định dạng .docx / .pdf trước khi tải lên."
            )

        clean_ext = src_extension.lstrip(".").lower()

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_filename = f"input.{clean_ext}"
            input_path = os.path.join(tmp_dir, input_filename)
            expected_pdf_path = os.path.join(tmp_dir, "input.pdf")

            with open(input_path, "wb") as f:
                f.write(input_bytes)

            cmd = [
                binary,
                "--headless",
                "--convert-to",
                "pdf",
                input_path,
                "--outdir",
                tmp_dir,
            ]

            logger.info(f"LibreOfficeConverter: converting {clean_ext} to PDF via {binary}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except (asyncio.TimeoutError, TimeoutError):
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                raise TimeoutError(
                    f"Quá trình chuyển đổi định dạng .{clean_ext} sang PDF vượt quá thời gian cho phép ({timeout}s)"
                )

            if proc.returncode != 0:
                err_text = (stderr or stdout or b"").decode("utf-8", errors="ignore")
                raise RuntimeError(
                    f"LibreOffice chuyển đổi thất bại (exit code {proc.returncode}): {err_text[:200]}"
                )

            if not os.path.exists(expected_pdf_path):
                raise RuntimeError(
                    f"Không tìm thấy file PDF đầu ra sau khi LibreOffice chuyển đổi '{input_filename}'"
                )

            with open(expected_pdf_path, "rb") as pf:
                return pf.read()


# Singleton instance
libreoffice_converter = LibreOfficeConverter()
