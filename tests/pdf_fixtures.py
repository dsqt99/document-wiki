"""Tạo PDF nhỏ cho test mà không cần thư viện ngoài.

- ``make_text_pdf``: PDF có lớp chữ (font Helvetica, mã WinAnsi nên chỉ dùng ASCII/Latin-1).
  Mỗi dòng là chuỗi hoặc ``(chuỗi, cỡ chữ)``; trang 1 có thể vẽ thêm một bảng kẻ ô.
- ``make_image_pdf``: PDF "scan": mỗi trang là một ảnh JPEG phủ kín trang, không có lớp chữ.
"""

from __future__ import annotations

import io
from typing import List, Optional, Sequence, Tuple, Union

Line = Union[str, Tuple[str, int]]
Table = Tuple[int, int, Sequence[int], Sequence[Sequence[str]]]  # (x, y_top, col_widths, rows)

PAGE_W, PAGE_H = 595, 842
_FONT = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(lines: Sequence[Line], table: Optional[Table]) -> bytes:
    ops: List[str] = []
    y = PAGE_H - 60
    for line in lines:
        text, size = (line, 12) if isinstance(line, str) else line
        ops.append(f"BT /F1 {size} Tf 50 {y} Td ({_esc(text)}) Tj ET")
        y -= int(size * 1.4)
    if table:
        x, top, cols, rows = table
        rh = 20
        width = sum(cols)
        height = rh * len(rows)
        ops.append("0.5 w")
        for r in range(len(rows) + 1):
            ops.append(f"{x} {top - r * rh} m {x + width} {top - r * rh} l S")
        cx = x
        for c in range(len(cols) + 1):
            ops.append(f"{cx} {top} m {cx} {top - height} l S")
            if c < len(cols):
                cx += cols[c]
        for r, row in enumerate(rows):
            cx = x
            for c, cell in enumerate(row):
                ops.append(f"BT /F1 10 Tf {cx + 3} {top - r * rh - 14} Td ({_esc(cell)}) Tj ET")
                cx += cols[c]
    return "\n".join(ops).encode("latin-1")


def make_text_pdf(pages: Sequence[Sequence[Line]], table: Optional[Table] = None) -> bytes:
    """PDF có lớp chữ; ``pages`` là danh sách trang, mỗi trang là danh sách dòng."""
    objects: List[Tuple[int, bytes]] = []
    page_ids: List[int] = []
    next_id = 4
    for index, lines in enumerate(pages):
        stream = _page_stream(lines, table if index == 0 else None)
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        page_ids.append(page_id)
        objects.append(
            (
                page_id,
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
                ).encode("latin-1"),
            )
        )
        objects.append(
            (content_id, f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
        )

    kids = " ".join(f"{p} 0 R" for p in page_ids)
    head: List[Tuple[int, bytes]] = [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")),
        (3, _FONT.encode("latin-1")),
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num, body in head + objects:
        offsets[num] = out.tell()
        out.write(f"{num} 0 obj\n".encode("latin-1") + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {next_id}\n".encode("latin-1"))
    out.write(b"0000000000 65535 f \n")
    for num in range(1, next_id):
        out.write(f"{offsets[num]:010d} 00000 n \n".encode("latin-1"))
    out.write(
        f"trailer\n<< /Size {next_id} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    )
    return out.getvalue()


def make_image_pdf(n_pages: int = 1, size: Tuple[int, int] = (600, 800)) -> bytes:
    """PDF scan: mỗi trang là một ảnh JPEG (Pillow ghi bằng DCTDecode) phủ kín trang."""
    from PIL import Image, ImageDraw

    images = []
    for i in range(n_pages):
        im = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(im)
        draw.rectangle([40, 40, size[0] - 40, size[1] - 40], outline="black", width=3)
        draw.text((60, 60), f"SCAN PAGE {i + 1}", fill="black")
        images.append(im)
    buf = io.BytesIO()
    images[0].save(buf, "PDF", save_all=True, append_images=images[1:], resolution=72.0)
    return buf.getvalue()
