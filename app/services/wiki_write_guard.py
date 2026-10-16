"""
Wiki write guard — refuse machine rewrites that silently destroy page content.

Ported from Tencent WeKnora commit abc365f91 ("table row identity guard") and
extended for this codebase's MRP compile pipeline.

When an LLM is asked to re-emit a whole page, markdown tables are where it most
often goes wrong: a 100-row ledger comes back with 30 rows, finish_reason=stop,
no error. We therefore compare *row identities* between the stored page and the
rewrite:

  identity = normalized first non-empty cell of each table DATA row
             (emphasis/code markers stripped, whitespace collapsed, lower-cased)

Header rows (the row directly above a ``| --- |`` delimiter) are skipped — a
model renaming a column header is not a lost row. Re-ordering rows, editing
other columns or merging duplicate rows does not count as loss; only an entity
disappearing entirely does.

Two policies:
  * ``check_machine_rewrite`` — compile/ingest path. Refuses when > 20% of the
    distinct row identities vanish, when the new content is the writer failure
    stub, or when the page shrinks drastically (< 50% of a substantial page).
  * ``check_agent_write`` — an agent's (MCP tool) full-page write. Refuses if
    ANY stored row identity vanishes; the agent can re-emit the rows or use an
    exact-text replacement instead.

Human edits (REST editor / draft approval / rollback) never go through these
checks — deliberate deletions by a person are allowed.

All functions here are pure (no I/O) so they can be unit-tested directly.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Marker text the MRP writer emits when page generation fails
#: (see app/ai/mrp/writer.py run_refine_phase). Kept here so writer and guard
#: agree on one spelling.
FAILURE_STUB_MARKER = "(Page generation failed"

#: Ingest/compile may drop at most this share of distinct row identities
#: (strictly greater refuses — losing exactly 1 in 5 still passes).
DEFAULT_MAX_ROW_LOSS = 0.2

#: A machine rewrite shorter than this fraction of the stored page is refused.
#: Writer passes use 0.9/0.95 (incremental passes) and the merger 0.7 (merge
#: of two inputs); a full-page UPDATE may legitimately restructure, so the
#: last-line-of-defence guard is looser but still catches truncation.
DEFAULT_MIN_LENGTH_RATIO = 0.5

#: The shrink check only applies when the stored page is at least this long —
#: tiny seed pages may be rewritten freely.
MIN_OLD_CHARS_FOR_SHRINK_CHECK = 500

#: How many example identities a refusal message names.
EXAMPLE_LIMIT = 5

_EMPHASIS_RE = re.compile(r"[*_`]")
_DELIM_CELL_RE = re.compile(r"^\s*:?-{1,}:?\s*$")


# ---------------------------------------------------------------------------
# Table row identities
# ---------------------------------------------------------------------------

def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2


def _split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return s.split("|")


def _is_delimiter_row(line: str) -> bool:
    cells = [c for c in _split_cells(line)]
    if not cells:
        return False
    return all(_DELIM_CELL_RE.match(c) for c in cells)


def _normalize_cell(cell: str) -> str:
    cell = cell.replace("　", " ").replace(" ", " ")
    cell = _EMPHASIS_RE.sub("", cell)
    return " ".join(cell.split()).lower()


def _row_identity(line: str) -> str:
    for cell in _split_cells(line):
        ident = _normalize_cell(cell)
        if ident:
            return ident
    return ""


def _row_identity_list(md: str) -> list[str]:
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    for i, line in enumerate(lines):
        if not _is_table_row(line) or _is_delimiter_row(line):
            continue
        # Header row: the line directly above a delimiter row.
        if i + 1 < len(lines) and _is_table_row(lines[i + 1]) and _is_delimiter_row(lines[i + 1]):
            continue
        ident = _row_identity(line)
        if ident:
            out.append(ident)
    return out


def table_row_identities(md: str) -> set[str]:
    """Distinct normalized identities (first non-empty cell) of all table data rows."""
    return set(_row_identity_list(md))


def missing_row_identities(old_md: str, new_md: str) -> set[str]:
    """Row identities present in ``old_md`` but absent from ``new_md``."""
    old_ids = table_row_identities(old_md)
    if not old_ids:
        return set()
    return old_ids - table_row_identities(new_md)


def _examples(missing: set[str]) -> str:
    return ", ".join(sorted(missing)[:EXAMPLE_LIMIT])


# ---------------------------------------------------------------------------
# Failure stub
# ---------------------------------------------------------------------------

def make_failure_stub(title: str, err_msg: str) -> str:
    """Content the writer records when page generation fails (never published over a page)."""
    return f"# {title}\n\n{FAILURE_STUB_MARKER}: {err_msg[:200]})"


def is_failure_stub(md: Optional[str]) -> bool:
    """True if ``md`` is (or contains) the MRP writer failure stub.

    Substring match: the verifier may prepend a callout to the stub.
    """
    return bool(md) and FAILURE_STUB_MARKER in md


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

def check_machine_rewrite(
    old_md: Optional[str],
    new_md: Optional[str],
    *,
    max_row_loss: float = DEFAULT_MAX_ROW_LOSS,
    min_length_ratio: float = DEFAULT_MIN_LENGTH_RATIO,
    min_old_chars: int = MIN_OLD_CHARS_FOR_SHRINK_CHECK,
) -> Optional[str]:
    """Check a compiler/ingest rewrite of a page. Returns a refusal reason, or None if OK."""
    new_md = new_md or ""
    old_md = old_md or ""

    if is_failure_stub(new_md) and not is_failure_stub(old_md):
        return "new content is the writer failure stub"

    old_s, new_s = old_md.strip(), new_md.strip()
    if not old_s:
        return None

    if not new_s:
        return "new content is empty"

    old_ids = table_row_identities(old_md)
    if old_ids:
        missing = old_ids - table_row_identities(new_md)
        if missing:
            ratio = len(missing) / len(old_ids)
            if ratio > max_row_loss:
                return (
                    f"rewrite dropped {len(missing)} of {len(old_ids)} table row identities "
                    f"(ratio {ratio:.2f} > {max_row_loss:.2f}), e.g. {_examples(missing)}"
                )

    if len(old_s) >= min_old_chars and len(new_s) < len(old_s) * min_length_ratio:
        return (
            f"rewrite shrank page {len(old_s)} -> {len(new_s)} chars "
            f"(< {min_length_ratio:.0%} of existing)"
        )

    return None


def check_agent_write(old_md: Optional[str], new_md: Optional[str]) -> Optional[str]:
    """Check an agent's full-page write (MCP edit tool).

    Refuses if ANY table row identity of the stored page disappears. Returns a
    Vietnamese refusal message (listing up to 5 missing identities), or None.
    """
    missing = missing_row_identities(old_md or "", new_md or "")
    if not missing:
        return None
    more = len(missing) - EXAMPLE_LIMIT
    suffix = f" (và {more} dòng khác)" if more > 0 else ""
    return (
        f"Bản sửa làm mất {len(missing)} dòng bảng: {_examples(missing)}{suffix}. "
        "Trang hiện tại được giữ nguyên. Hãy giữ lại đầy đủ các dòng bảng hiện có "
        "(chỉ sửa phần cần thay đổi) rồi gửi lại."
    )
