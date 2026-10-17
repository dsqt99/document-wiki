"""Quét đặc tả clean-room: báo khối code và dòng giống code."""
import pathlib
import re
import sys

CODE_HINT = re.compile(
    r"^\s*(def |class |async def |import |from \S+ import |return |SELECT |INSERT |CREATE |"
    r"const |let |function |export |<[A-Z][A-Za-z]+[ />])"
)


def scan(root: pathlib.Path) -> int:
    issues = 0
    for p in sorted(root.glob("*.md")):
        if p.name == "QUY_TAC_DAC_TA.md":
            continue
        in_fence = False
        for no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("```"):
                in_fence = not in_fence
                if in_fence:
                    print(f"{p.name}:{no}: mở khối code")
                    issues += 1
                continue
            if not in_fence and CODE_HINT.match(line):
                print(f"{p.name}:{no}: dòng giống code: {line.strip()[:80]}")
                issues += 1
    return issues


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "docs/c2/dac_ta")
    n = scan(root)
    print(f"Tổng: {n} vấn đề")
    sys.exit(1 if n else 0)
