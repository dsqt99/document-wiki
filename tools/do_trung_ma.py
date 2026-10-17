"""Đo tỷ lệ dòng có nghĩa của c2 trùng với một snapshot mã tham chiếu.

Dùng: python tools/do_trung_ma.py <nguong> <thu_muc_tham_chieu> [thu_muc_tham_chieu ...]
Dòng có nghĩa: sau khi bỏ khoảng trắng, dài từ 25 ký tự, không phải import hay chú thích.
"""
import pathlib
import sys

EXTS = {".py", ".ts", ".tsx", ".js", ".css"}
SKIP_DIRS = {".git", ".venv", "node_modules", ".next", "__pycache__"}


def sig_lines(text: str) -> set[str]:
    out = set()
    for raw in text.splitlines():
        s = raw.strip()
        if len(s) < 25:
            continue
        if s.startswith(("import ", "from ", "#", "//", "*", "/*")):
            continue
        out.add(s)
    return out


def walk(root: pathlib.Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in EXTS and not (SKIP_DIRS & set(p.parts)):
            yield p


def main() -> int:
    threshold = float(sys.argv[1])
    ref_lines: set[str] = set()
    for ref in sys.argv[2:]:
        for p in walk(pathlib.Path(ref)):
            ref_lines |= sig_lines(p.read_text(encoding="utf-8", errors="ignore"))
    here = pathlib.Path(".")
    bad = 0
    rows = []
    for p in walk(here):
        if p.parts[0] == "tools":
            continue
        lines = sig_lines(p.read_text(encoding="utf-8", errors="ignore"))
        if not lines:
            continue
        ratio = len(lines & ref_lines) / len(lines)
        rows.append((ratio, p.as_posix(), len(lines)))
    for ratio, path, n in sorted(rows, reverse=True):
        flag = "VUOT" if ratio >= threshold else ""
        if ratio >= 0.05:
            print(f"{ratio:6.1%}  {n:5d}  {path} {flag}")
        bad += ratio >= threshold
    print(f"{len(rows)} file, {bad} file vượt ngưỡng {threshold:.0%}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
