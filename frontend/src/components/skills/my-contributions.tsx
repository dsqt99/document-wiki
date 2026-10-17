"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fmtShortDateTime, TONE } from "./skill-utils";
import type { Department, MyContribution } from "./types";

const STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: "Bản nháp", cls: TONE.amber },
  pending: { label: "Chờ duyệt", cls: TONE.blue },
  rejected: { label: "Bị từ chối", cls: TONE.red },
  approved: { label: "Đã duyệt", cls: TONE.green },
};

export const blockCls = "rounded-xl border border-border/60 bg-background/40 p-3";

export function BlockTitle({ icon, title, count }: { icon: string; title: string; count: number }) {
  return (
    <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
      <span className="material-symbols-outlined text-primary/60" style={{ fontSize: 18 }}>{icon}</span>
      {title}
      <span className="rounded-full bg-primary/10 px-1.5 text-[11px] font-bold text-primary tabular-nums">{count}</span>
    </div>
  );
}

/**
 * "Đề xuất của tôi": the caller's unapproved proposals. Loaded once per mount; the page
 * remounts it (via `key`) whenever the proposal editor opens or closes.
 */
export function MyContributions({
  departments,
  onOpen,
  onChanged,
}: {
  departments: Department[];
  onOpen: (id: string) => void;
  onChanged?: () => void;
}) {
  const [items, setItems] = useState<MyContribution[]>([]);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    api<MyContribution[]>("/api/skill-contributions")
      .then((rows) => alive && setItems((Array.isArray(rows) ? rows : []).filter((r) => r.status !== "approved")))
      .catch((err) => console.error("Load contributions failed", err));
    return () => {
      alive = false;
    };
  }, [version]);

  if (items.length === 0) return null;

  const deptName = new Map(departments.map((d) => [d.id, d.name]));
  const scopeText = (c: MyContribution) => {
    if (c.scope_type === "department" && c.scope_ids?.length) {
      const names = c.scope_ids.map((id) => deptName.get(id)).filter(Boolean);
      if (names.length) return names.join(", ");
    }
    return "Toàn hệ thống";
  };

  const open = (c: MyContribution) => {
    if (c.status === "approved") {
      setItems((list) => list.filter((x) => x.id !== c.id));
      return;
    }
    onOpen(c.id);
  };

  const remove = async (c: MyContribution) => {
    if (!confirm("Xóa đề xuất này? Không thể hoàn tác.")) return;
    try {
      await api(`/api/skill-contributions/${c.id}`, { method: "DELETE" });
      setVersion((v) => v + 1);
      onChanged?.();
    } catch {
      alert("Delete failed");
    }
  };

  const iconBtn =
    "inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted";

  return (
    <div className={blockCls}>
      <BlockTitle icon="pending_actions" title="Đề xuất của tôi" count={items.length} />
      <ul className="divide-y divide-border/50">
        {items.map((c) => {
          const st = STATUS[c.status] ?? { label: c.status, cls: TONE.muted };
          const scope = scopeText(c);
          return (
            <li key={c.id} className="flex items-center gap-2 py-1.5 text-xs">
              <button
                type="button"
                title={c.title}
                onClick={() => open(c)}
                className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:text-primary"
              >
                {c.title}
              </button>
              <span className={cn("shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium", st.cls)}>{st.label}</span>
              <span className="hidden max-w-40 truncate text-muted-foreground sm:inline" title={scope}>{scope}</span>
              <span className="hidden text-muted-foreground tabular-nums md:inline">{fmtShortDateTime(c.updated_at)}</span>
              <button
                type="button"
                title="Tiếp tục soạn"
                aria-label="Tiếp tục soạn"
                onClick={() => open(c)}
                className={cn(iconBtn, "hover:text-foreground")}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>edit</span>
              </button>
              <button
                type="button"
                title="Xóa bản nháp"
                aria-label="Xóa bản nháp"
                onClick={() => void remove(c)}
                className={cn(iconBtn, "hover:text-destructive")}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
