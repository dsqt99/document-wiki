"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { NotificationItem } from "@/types/notification";

const POLL_MS = 30_000;

/** Icon + colour for a notification type (substring match, first hit wins). */
function typeVisual(type: string): { icon: string; className: string } {
  if (type.includes("approved")) return { icon: "check_circle", className: "text-emerald-600 dark:text-emerald-400" };
  if (type.includes("rejected")) return { icon: "cancel", className: "text-destructive" };
  if (type.includes("changes_requested")) return { icon: "edit_note", className: "text-blue-600 dark:text-blue-400" };
  if (type.includes("resubmitted")) return { icon: "refresh", className: "text-amber-600 dark:text-amber-400" };
  if (type.includes("withdrawn")) return { icon: "remove_circle", className: "text-muted-foreground" };
  return { icon: "inbox", className: "text-amber-600 dark:text-amber-400" };
}

function relativeTime(iso: string): string {
  const then = new Date(iso);
  const diff = (Date.now() - then.getTime()) / 1000;
  if (Number.isNaN(diff)) return "";
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)}d ago`;
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function NotificationBell({ className }: { className?: string }) {
  const { t, lang } = useI18n();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadCount = useCallback(async () => {
    try {
      const res = await api<{ count: number }>("/api/notifications/unread-count");
      setUnread(typeof res.count === "number" ? res.count : 0);
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(() => void loadCount(), 0);
    const timer = setInterval(() => void loadCount(), POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [loadCount]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const openDrawer = async () => {
    setOpen(true);
    setLoading(true);
    try {
      const list = await api<NotificationItem[]>("/api/notifications?limit=50");
      setItems(Array.isArray(list) ? list : []);
    } catch {
      /* keep previous list */
    } finally {
      setLoading(false);
    }
  };

  const markAllRead = async () => {
    try {
      await api("/api/notifications/read-all", { method: "POST" });
      const now = new Date().toISOString();
      setItems((prev) => prev.map((n) => (n.read_at ? n : { ...n, read_at: now })));
      setUnread(0);
    } catch {
      /* silent */
    }
  };

  const clickItem = async (item: NotificationItem) => {
    if (!item.read_at) {
      try {
        await api(`/api/notifications/${encodeURIComponent(item.id)}/read`, { method: "POST" });
        const now = new Date().toISOString();
        setItems((prev) => prev.map((n) => (n.id === item.id ? { ...n, read_at: now } : n)));
        setUnread((c) => Math.max(0, c - 1));
      } catch {
        /* silent */
      }
    }
    // No deep link target yet: just close.
    setOpen(false);
  };

  const hasUnread = items.some((n) => !n.read_at);
  // Dedicated labels (the shared i18n keys `common.clear` / `audit.noLogs` read wrongly here).
  const markAllLabel = t("notifications.markAllRead", lang === "vi" ? "Đánh dấu đã đọc tất cả" : "Mark all read");
  const emptyLabel = t("notifications.empty", lang === "vi" ? "Chưa có thông báo nào." : "No notifications yet.");

  return (
    <>
      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              aria-label="Notifications"
              onClick={openDrawer}
              className={cn(
                "relative flex size-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
                className,
              )}
            />
          }
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
            notifications
          </span>
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[9px] leading-none font-bold text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </TooltipTrigger>
        <TooltipContent side="bottom">Notifications</TooltipContent>
      </Tooltip>

      {open && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} aria-hidden />
          <div
            role="dialog"
            aria-label={t("common.notifications")}
            className="absolute top-0 right-0 flex h-full w-full max-w-md flex-col border-l bg-background shadow-2xl animate-in slide-in-from-right duration-200"
          >
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 20 }}>
                notifications
              </span>
              <h2 className="flex-1 text-sm font-semibold">{t("common.notifications")}</h2>
              {hasUnread && (
                <button
                  type="button"
                  onClick={markAllRead}
                  className="rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary/10"
                >
                  {markAllLabel}
                </button>
              )}
              <button
                type="button"
                aria-label={t("common.close")}
                onClick={() => setOpen(false)}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
              >
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                  close
                </span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {loading && items.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
              ) : items.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">{emptyLabel}</p>
              ) : (
                <ul className="divide-y">
                  {items.map((item) => {
                    const visual = typeVisual(item.type || "");
                    const isUnread = !item.read_at;
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => clickItem(item)}
                          className={cn(
                            "flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60",
                            isUnread && "bg-primary/5",
                          )}
                        >
                          <span className={cn("material-symbols-outlined mt-0.5", visual.className)} style={{ fontSize: 20 }}>
                            {visual.icon}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span
                              className={cn(
                                "block truncate text-sm",
                                isUnread ? "font-semibold text-foreground" : "text-muted-foreground",
                              )}
                            >
                              {item.subject}
                            </span>
                            {item.body && (
                              <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{item.body}</span>
                            )}
                            <span className="mt-1 block text-[11px] text-muted-foreground">{relativeTime(item.created_at)}</span>
                          </span>
                          {isUnread && <span className="mt-2 size-2 shrink-0 rounded-full bg-primary" />}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
