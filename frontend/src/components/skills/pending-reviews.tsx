"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { BlockTitle, blockCls } from "./my-contributions";
import { scrollCls } from "./skill-markdown";
import { fmtViDateTime } from "./skill-utils";
import type { PendingContribution } from "./types";

/**
 * "Chờ tôi duyệt": proposals the caller may review. Loads once (when allowed) and reports the
 * rows through `onLoaded`; when the page passes `items` that list is shown instead.
 */
export function PendingReviews({
  skillId,
  items: controlled,
  onLoaded,
  onOpen,
}: {
  skillId?: string;
  items?: PendingContribution[];
  onLoaded?: (items: PendingContribution[]) => void;
  onOpen: (item: PendingContribution) => void;
}) {
  const { canAccess, hasPermission } = useAuth();
  const allowed = canAccess("skill", "review") || hasPermission("skill:contribution:review");
  const [own, setOwn] = useState<PendingContribution[]>([]);

  useEffect(() => {
    if (!allowed) return;
    let alive = true;
    const qs = skillId ? `?skill_id=${encodeURIComponent(skillId)}` : "";
    api<PendingContribution[]>(`/api/admin/skill-contributions${qs}`)
      .then((rows) => {
        if (!alive) return;
        const list = Array.isArray(rows) ? rows : [];
        setOwn(list);
        onLoaded?.(list);
      })
      .catch((err) => console.error("Load pending reviews failed", err));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one load per mount/skill
  }, [allowed, skillId]);

  const items = controlled ?? own;
  if (!allowed || items.length === 0) return null;

  return (
    <div className={blockCls}>
      <BlockTitle icon="rate_review" title="Chờ tôi duyệt" count={items.length} />
      <ul className={cn("max-h-48 divide-y divide-border/50 overflow-y-auto", scrollCls.thin)}>
        {items.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => onOpen(c)}
              className="group flex w-full items-center gap-2 py-1.5 text-left text-xs"
            >
              <span className="min-w-0 flex-1 truncate text-sm font-medium group-hover:text-primary">
                {c.skill_id ? c.title : `Kỹ năng mới: ${c.title || "Chưa đặt tên"}`}
              </span>
              <span className="hidden max-w-32 truncate text-muted-foreground sm:inline">{c.contributor_name}</span>
              <span className="hidden text-muted-foreground tabular-nums md:inline">{fmtViDateTime(c.created_at)}</span>
              <span
                className="material-symbols-outlined text-muted-foreground/50 group-hover:text-primary"
                style={{ fontSize: 16 }}
              >
                arrow_forward
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
