"use client";

import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { QUEUE_STATUSES, relativeTime, type BranchListItem, type QueueStatus } from "./review-utils";

type ReviewQueueProps = {
  status: QueueStatus;
  mine: boolean;
  scope: string;
  scopeOptions: { value: string; label: string }[];
  /** All loaded branches (before the scope filter) */
  total: number;
  items: BranchListItem[];
  loading: boolean;
  selectedId: string | null;
  onStatusChange: (status: QueueStatus) => void;
  onMineChange: (mine: boolean) => void;
  onScopeChange: (scope: string) => void;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  onToggleHelp: () => void;
};

const nativeSelect =
  "h-8 w-full rounded-lg border border-input bg-background px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

export function ReviewQueue({
  status,
  mine,
  scope,
  scopeOptions,
  total,
  items,
  loading,
  selectedId,
  onStatusChange,
  onMineChange,
  onScopeChange,
  onSelect,
  onRefresh,
  onToggleHelp,
}: ReviewQueueProps) {
  const { t } = useI18n();
  const filtering = scope !== "";
  const countLabel = (n: number) => `${n} ${n === 1 ? "draft" : "drafts"}`;
  const statusLabel = (() => {
    const s = QUEUE_STATUSES.find((x) => x.value === status) ?? QUEUE_STATUSES[0];
    return t(s.key, s.fallback);
  })();

  return (
    <aside className="flex min-h-0 w-[320px] shrink-0 flex-col border-r bg-card/50">
      <div className="flex flex-col gap-3 border-b p-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{t("review.title", "Hàng đợi duyệt bản thảo")}</h2>
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  onClick={onToggleHelp}
                  className="rounded-md px-1 py-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Keyboard shortcuts"
                >
                  <kbd className="rounded border bg-muted px-1.5 font-mono text-[11px]">?</kbd>
                </button>
              }
            />
            <TooltipContent>Keyboard shortcuts</TooltipContent>
          </Tooltip>
        </div>

        <div className="grid grid-cols-2 overflow-hidden rounded-lg border text-xs font-medium">
          {[
            { value: false, icon: "fact_check", label: t("review.toReview", "Cần duyệt") },
            { value: true, icon: "edit_note", label: t("review.mine", "Của tôi") },
          ].map((opt) => (
            <button
              key={String(opt.value)}
              type="button"
              onClick={() => onMineChange(opt.value)}
              className={cn(
                "flex items-center justify-center gap-1.5 px-2 py-1.5 transition-colors",
                mine === opt.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
              )}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                {opt.icon}
              </span>
              {opt.label}
            </button>
          ))}
        </div>

        <select
          className={nativeSelect}
          value={status}
          onChange={(e) => onStatusChange(e.target.value as QueueStatus)}
          aria-label="Status"
        >
          {QUEUE_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {t(s.key, s.fallback)}
            </option>
          ))}
        </select>

        {scopeOptions.length > 1 && (
          <select
            className={nativeSelect}
            value={scope}
            onChange={(e) => onScopeChange(e.target.value)}
            title="Filter by scope"
            aria-label="Filter by scope"
          >
            <option value="">All scopes ({total})</option>
            {scopeOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        )}

        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>
            {loading
              ? "Loading…"
              : filtering
                ? `${items.length} of ${countLabel(total)}`
                : countLabel(total)}
          </span>
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  onClick={onRefresh}
                  className="flex size-6 items-center justify-center rounded-md hover:bg-muted hover:text-foreground"
                  aria-label="Refresh"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                    refresh
                  </span>
                </button>
              }
            />
            <TooltipContent>Refresh</TooltipContent>
          </Tooltip>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? null : items.length === 0 ? (
          <EmptyState
            icon="inbox"
            title={t("review.emptyQueue", "Hàng đợi trống")}
            description={
              filtering && total > 0
                ? "No drafts in this scope. Switch to 'All scopes' to see others."
                : t("review.noDraftsInStatus", `No drafts in ${statusLabel} state.`)
            }
          />
        ) : (
          <ul className="divide-y">
            {items.map((b) => {
              const active = b.id === selectedId;
              return (
                <li key={b.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(b.id)}
                    className={cn(
                      "flex w-full flex-col gap-0.5 border-l-2 px-3 py-2.5 text-left transition-colors",
                      active ? "border-l-primary bg-primary/10" : "border-l-transparent hover:bg-muted/50",
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      {b.has_conflict && (
                        <span className="shrink-0 rounded bg-destructive/10 px-1 text-[10px] font-semibold tracking-wide text-destructive uppercase">
                          conflict
                        </span>
                      )}
                      <span className="truncate text-sm font-medium">{b.name}</span>
                    </span>
                    <span className="truncate font-mono text-[11px] text-muted-foreground">
                      {b.scope_type || "global"} · {b.draft_count} files changed
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      {b.author_name || "?"} · {relativeTime(b.created_at)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
