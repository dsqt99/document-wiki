"use client";

import { useMemo } from "react";
import { diffLines } from "diff";
import { cn } from "@/lib/utils";
import { scrollCls } from "./skill-markdown";

type Row = { kind: "same" | "del" | "add"; oldNo: number | null; newNo: number | null; text: string };

function toRows(before: string, after: string): Row[] {
  const parts = diffLines(before.replace(/\r\n/g, "\n"), after.replace(/\r\n/g, "\n"));
  const rows: Row[] = [];
  let oldNo = 0;
  let newNo = 0;
  for (const part of parts) {
    const lines = part.value.split("\n");
    // A chunk ending with "\n" yields one empty trailing element that is not a real line.
    if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
    for (const text of lines) {
      if (part.added) rows.push({ kind: "add", oldNo: null, newNo: ++newNo, text });
      else if (part.removed) rows.push({ kind: "del", oldNo: ++oldNo, newNo: null, text });
      else rows.push({ kind: "same", oldNo: ++oldNo, newNo: ++newNo, text });
    }
  }
  return rows;
}

/** Line-by-line comparison of the original file and the proposed content. */
export function DiffViewer({ original, current }: { original: string; current: string }) {
  const rows = useMemo(() => toRows(original, current), [original, current]);

  return (
    <div className={cn("h-full overflow-y-auto font-mono text-[13px]", scrollCls.none)}>
      <div className="sticky top-0 z-10 flex border-b bg-muted/80 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase backdrop-blur">
        <div className="w-[100px] shrink-0 px-2 py-1.5 text-center">Line</div>
        <div className="px-3 py-1.5">Content</div>
      </div>
      {rows.map((r, i) => (
        <div
          key={i}
          className={cn(
            "flex",
            r.kind === "del" && "bg-destructive/10",
            r.kind === "add" && "bg-emerald-500/10",
            r.kind === "same" && "opacity-70 hover:opacity-100",
          )}
        >
          <div className="flex w-[100px] shrink-0 border-r text-[10px] text-muted-foreground select-none">
            <span className="w-1/2 px-1.5 py-0.5 text-right">{r.oldNo ?? "-"}</span>
            <span className="w-1/2 px-1.5 py-0.5 text-right">{r.newNo ?? "-"}</span>
          </div>
          <div className="min-w-0 flex-1 px-3 py-0.5 break-words whitespace-pre-wrap">
            {r.kind !== "same" && (
              <span className="mr-1 opacity-50 select-none">{r.kind === "add" ? "+" : "-"}</span>
            )}
            {r.text || " "}
          </div>
        </div>
      ))}
    </div>
  );
}
