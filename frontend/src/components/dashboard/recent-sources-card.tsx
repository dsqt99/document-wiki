"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";

type RecentSource = {
  id: string;
  title: string;
  status: string;
  knowledge_type_name?: string | null;
  knowledge_type_color?: string | null;
  created_at: string;
};

const STATUS_CLASS: Record<string, string> = {
  ready: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  processing: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  error: "bg-destructive/10 text-destructive",
};

export function RecentSourcesCard() {
  const { t } = useI18n();
  const [items, setItems] = useState<RecentSource[] | null>(null);

  useEffect(() => {
    let active = true;
    api<RecentSource[]>("/api/sources?limit=5")
      .then((res) => {
        if (active) setItems(Array.isArray(res) ? res : []);
      })
      .catch(() => {
        if (active) setItems([]);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="rounded-xl border bg-card p-6 shadow-lift">
      <h3 className="border-b pb-3 text-xl font-semibold">{t("dash.recentDocs", "Tài liệu gần đây")}</h3>
      {items === null ? (
        <div className="flex justify-center py-10">
          <span className="material-symbols-outlined animate-spin text-muted-foreground" style={{ fontSize: 28 }}>
            progress_activity
          </span>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon="description"
          title={t("dash.noRecentDocs", "Chưa có tài liệu nào")}
          description={t("dash.uploadFirstDoc")}
        />
      ) : (
        <ul className="mt-2 flex flex-col">
          {items.map((s) => (
            <li key={s.id} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-muted/50">
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 20 }}>
                description
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{s.title}</p>
                <p className="text-xs text-muted-foreground">{new Date(s.created_at).toLocaleDateString()}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {s.knowledge_type_name && (
                  <span
                    className="rounded-full border px-2 py-0.5 text-[11px]"
                    style={
                      s.knowledge_type_color
                        ? { borderColor: s.knowledge_type_color, color: s.knowledge_type_color }
                        : undefined
                    }
                  >
                    {s.knowledge_type_name}
                  </span>
                )}
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium",
                    STATUS_CLASS[s.status] ?? "bg-muted text-muted-foreground",
                  )}
                >
                  {s.status}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
