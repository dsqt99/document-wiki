"""Đo trùng theo khối token liên tiếp (kiểu MOSS), bổ sung cho do_trung_ma.py.

do_trung_ma.py đếm từng dòng nên bắt cả những dòng bị giao diện ép buộc (tên route,
tên cột, chữ ký hàm, thông báo lỗi). Công cụ này chỉ tính một đoạn là trùng khi
K token liên tiếp (mặc định 40, thường trải qua nhiều dòng) giống hệt mã tham chiếu,
tức là có dấu hiệu chép cả cấu trúc chứ không chỉ trùng tên.

Dùng: python tools/do_trung_khoi.py <nguong> <thu_muc_tham_chieu> [thu_muc_tham_chieu ...]
Biến môi trường TRUNG_K đổi độ dài khối.
"""
import os
import pathlib
import re
import sys

EXTS = {".py", ".ts", ".tsx", ".js", ".css"}
SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__"}
# Thành phần shadcn/ui sinh từ CLI công khai (MIT), không tính là mã Arkon.
SKIP_PREFIXES = ("tools/", "frontend/src/components/ui/")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|\"[^\"\n]*\"|'[^'\n]*'|`[^`\n]*`|\S")
COMMENT_RE = re.compile(r"^\s*(#|//|\*|/\*)")
K = int(os.environ.get("TRUNG_K", "40"))


def tokens(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or COMMENT_RE.match(s) or s.startswith(("import ", "from ")):
            continue
        out.extend(TOKEN_RE.findall(s))
    return out


def shingles(toks: list[str]) -> list[int]:
    return [hash(" ".join(toks[i : i + K])) for i in range(len(toks) - K + 1)]


def walk(root: pathlib.Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in EXTS and not (SKIP_DIRS & set(p.parts)):
            yield p


def main() -> int:
    threshold = float(sys.argv[1])
    ref: set[int] = set()
    for r in sys.argv[2:]:
        for p in walk(pathlib.Path(r)):
            ref.update(shingles(tokens(p.read_text(encoding="utf-8", errors="ignore"))))
    rows = []
    for p in walk(pathlib.Path(".")):
        rel = p.as_posix()
        if rel.startswith(SKIP_PREFIXES):
            continue
        sh = shingles(tokens(p.read_text(encoding="utf-8", errors="ignore")))
        if not sh:
            continue
        hit = [h in ref for h in sh]
        # Phần token nằm trong ít nhất một khối trùng.
        covered = [False] * (len(sh) + K - 1)
        for i, h in enumerate(hit):
            if h:
                for j in range(i, i + K):
                    covered[j] = True
        rows.append((sum(covered) / len(covered), rel, len(covered)))
    bad = 0
    for ratio, rel, n in sorted(rows, reverse=True):
        flag = "VUOT" if ratio >= threshold else ""
        if ratio >= 0.02:
            print(f"{ratio:6.1%}  {n:6d}  {rel} {flag}")
        bad += ratio >= threshold
    print(f"{len(rows)} file, {bad} file vượt ngưỡng {threshold:.0%} (K={K} token)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
