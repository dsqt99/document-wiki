"use client";

import { Fragment, useMemo, useState } from "react";
import { diffLines, diffWordsWithSpace } from "diff";
import { cn } from "@/lib/utils";

type LineKind = "same" | "add" | "del";
type LineOp = { kind: LineKind; text: string };
type Row = LineOp | { kind: "gap"; count: number };

const HEADING_RE = /^#{1,6}\s+\S/;

function toLineOps(oldText: string, newText: string): LineOp[] {
  const ops: LineOp[] = [];
  for (const part of diffLines(oldText, newText)) {
    const lines = part.value.split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
    const kind: LineKind = part.added ? "add" : part.removed ? "del" : "same";
    for (const text of lines) ops.push({ kind, text });
  }
  return ops;
}

/**
 * Trim unchanged runs to `n` lines of context. A run touching the start keeps its last n
 * lines, a run touching the end keeps its first n, and an inner run longer than 2n keeps n
 * on each side. Dropped lines become a single "gap" row.
 */
function collapse(ops: LineOp[], n: number): Row[] {
  const out: Row[] = [];
  let i = 0;
  while (i < ops.length) {
    if (ops[i].kind !== "same") {
      out.push(ops[i]);
      i++;
      continue;
    }
    let j = i;
    while (j < ops.length && ops[j].kind === "same") j++;
    const run = ops.slice(i, j);
    const atStart = i === 0;
    const atEnd = j === ops.length;
    if (atStart && atEnd) {
      out.push(...run);
    } else if (atStart) {
      if (run.length > n) out.push({ kind: "gap", count: run.length - n });
      out.push(...run.slice(Math.max(0, run.length - n)));
    } else if (atEnd) {
      out.push(...run.slice(0, n));
      if (run.length > n) out.push({ kind: "gap", count: run.length - n });
    } else if (run.length > 2 * n) {
      out.push(...run.slice(0, n));
      out.push({ kind: "gap", count: run.length - 2 * n });
      out.push(...run.slice(run.length - n));
    } else {
      out.push(...run);
    }
    i = j;
  }
  return out;
}

function GapRow({ count, colSpan }: { count: number; colSpan?: boolean }) {
  return (
    <div
      className={cn(
        "bg-muted/40 py-1 text-center text-[11px] text-muted-foreground/80 select-none",
        colSpan && "col-span-2",
      )}
    >
      ··· {count} unchanged line{count === 1 ? "" : "s"} ···
    </div>
  );
}

function UnifiedRows({ rows }: { rows: Row[] }) {
  return (
    <div>
      {rows.map((r, idx) => {
        if (r.kind === "gap") return <GapRow key={idx} count={r.count} />;
        return (
          <div
            key={idx}
            className={cn(
              "flex border-l-2 border-transparent",
              r.kind === "add" && "border-emerald-500 bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300",
              r.kind === "del" && "border-rose-500 bg-rose-50 text-rose-800 dark:bg-rose-500/10 dark:text-rose-300",
              r.kind === "same" && "text-muted-foreground",
            )}
          >
            <span className="w-6 shrink-0 text-center select-none opacity-70">
              {r.kind === "add" ? "+" : r.kind === "del" ? "−" : "·"}
            </span>
            <span className="min-w-0 flex-1 pr-3 break-words whitespace-pre-wrap">{r.text || " "}</span>
          </div>
        );
      })}
    </div>
  );
}

type Group = { heading: string | null; ops: LineOp[]; changed: boolean };

function groupByHeadings(ops: LineOp[]): Group[] {
  const groups: Group[] = [];
  let cur: Group = { heading: null, ops: [], changed: false };
  for (const op of ops) {
    if (op.kind === "same" && HEADING_RE.test(op.text)) {
      if (cur.heading !== null || cur.ops.length > 0) groups.push(cur);
      cur = { heading: op.text, ops: [], changed: false };
      continue;
    }
    cur.ops.push(op);
    if (op.kind !== "same") cur.changed = true;
  }
  if (cur.heading !== null || cur.ops.length > 0) groups.push(cur);
  return groups;
}

function GroupedUnified({ groups, contextLines }: { groups: Group[]; contextLines: number }) {
  const [overrides, setOverrides] = useState<Record<string, boolean>>({});
  return (
    <div className="divide-y">
      {groups.map((g, idx) => {
        const key = `${idx}:${g.heading ?? ""}`;
        const defaultOpen = g.changed || g.heading === null;
        const open = overrides[key] ?? defaultOpen;
        const rows: Row[] = g.changed ? collapse(g.ops, contextLines) : g.ops;
        return (
          <div key={key}>
            <button
              type="button"
              onClick={() => setOverrides((o) => ({ ...o, [key]: !open }))}
              className="flex w-full items-center gap-1.5 bg-muted/30 px-2 py-1.5 text-left hover:bg-muted/60"
            >
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>
                {open ? "expand_more" : "chevron_right"}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono text-xs font-medium text-foreground">
                {g.heading ?? "(no heading)"}
              </span>
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium",
                  g.changed
                    ? "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
                    : "text-muted-foreground",
                )}
              >
                {g.changed ? "changed" : "unchanged"}
              </span>
            </button>
            {open && rows.length > 0 && <UnifiedRows rows={rows} />}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Split view
// ---------------------------------------------------------------------------

type SplitRow =
  | { kind: "gap"; count: number }
  | { kind: "pair"; left: LineOp | null; right: LineOp | null };

function buildSplitRows(rows: Row[]): SplitRow[] {
  const out: SplitRow[] = [];
  let i = 0;
  while (i < rows.length) {
    const r = rows[i];
    if (r.kind === "gap") {
      out.push(r);
      i++;
      continue;
    }
    if (r.kind === "same") {
      out.push({ kind: "pair", left: r, right: r });
      i++;
      continue;
    }
    // a block of consecutive changes: pair removed with added lines in order
    const dels: LineOp[] = [];
    const adds: LineOp[] = [];
    while (i < rows.length && (rows[i].kind === "add" || rows[i].kind === "del")) {
      const op = rows[i] as LineOp;
      (op.kind === "del" ? dels : adds).push(op);
      i++;
    }
    const len = Math.max(dels.length, adds.length);
    for (let k = 0; k < len; k++) out.push({ kind: "pair", left: dels[k] ?? null, right: adds[k] ?? null });
  }
  return out;
}

function WordDiff({ oldLine, newLine, side }: { oldLine: string; newLine: string; side: "left" | "right" }) {
  const parts = diffWordsWithSpace(oldLine, newLine);
  return (
    <>
      {parts.map((p, i) => {
        if (side === "left" && p.added) return null;
        if (side === "right" && p.removed) return null;
        if (p.added)
          return (
            <span key={i} className="rounded-sm bg-emerald-200/80 dark:bg-emerald-500/30">
              {p.value}
            </span>
          );
        if (p.removed)
          return (
            <span key={i} className="rounded-sm bg-rose-200/80 line-through dark:bg-rose-500/30">
              {p.value}
            </span>
          );
        return <Fragment key={i}>{p.value}</Fragment>;
      })}
    </>
  );
}

function SplitCell({ op, other, side }: { op: LineOp | null; other: LineOp | null; side: "left" | "right" }) {
  if (!op) return <div className="bg-muted/30" />;
  const changed = op.kind !== "same";
  const paired = changed && other && other.kind !== "same";
  return (
    <div
      className={cn(
        "flex min-w-0 border-l-2 border-transparent",
        op.kind === "add" && "border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-200",
        op.kind === "del" && "border-rose-500 bg-rose-50 text-rose-900 dark:bg-rose-500/10 dark:text-rose-200",
        op.kind === "same" && "text-muted-foreground",
      )}
    >
      <span className="w-5 shrink-0 text-center select-none opacity-70">
        {op.kind === "add" ? "+" : op.kind === "del" ? "−" : "·"}
      </span>
      <span className="min-w-0 flex-1 pr-2 break-words whitespace-pre-wrap">
        {paired ? (
          <WordDiff
            oldLine={side === "left" ? op.text : other!.text}
            newLine={side === "left" ? other!.text : op.text}
            side={side}
          />
        ) : (
          op.text || " "
        )}
      </span>
    </div>
  );
}

function SplitView({ rows }: { rows: Row[] }) {
  const splitRows = useMemo(() => buildSplitRows(rows), [rows]);
  return (
    <div className="grid grid-cols-2">
      <div className="border-r border-b bg-muted/40 px-3 py-1.5 font-sans text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
        Current
      </div>
      <div className="border-b bg-muted/40 px-3 py-1.5 font-sans text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
        Proposed
      </div>
      {splitRows.map((r, idx) =>
        r.kind === "gap" ? (
          <GapRow key={idx} count={r.count} colSpan />
        ) : (
          <Fragment key={idx}>
            <div className="min-w-0 border-r">
              <SplitCell op={r.left} other={r.right} side="left" />
            </div>
            <div className="min-w-0">
              <SplitCell op={r.right} other={r.left} side="right" />
            </div>
          </Fragment>
        ),
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

type WikiDraftDiffProps = {
  oldText: string;
  newText: string;
  mode?: "unified" | "split";
  contextLines?: number;
  groupByHeading?: boolean;
};

export function WikiDraftDiff({
  oldText,
  newText,
  mode = "unified",
  contextLines = 3,
  groupByHeading = true,
}: WikiDraftDiffProps) {
  const oldStr = oldText ?? "";
  const newStr = newText ?? "";
  const ops = useMemo(() => toLineOps(oldStr, newStr), [oldStr, newStr]);
  const n = Math.max(0, contextLines);
  const rows = useMemo(() => collapse(ops, n), [ops, n]);
  const groups = useMemo(() => (groupByHeading ? groupByHeadings(ops) : []), [ops, groupByHeading]);

  if (oldStr === newStr) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        No changes between the current page and the proposed content.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border font-mono text-xs leading-5">
      {mode === "split" ? (
        <SplitView rows={rows} />
      ) : groupByHeading && groups.length > 1 ? (
        <GroupedUnified groups={groups} contextLines={n} />
      ) : (
        <UnifiedRows rows={rows} />
      )}
    </div>
  );
}
