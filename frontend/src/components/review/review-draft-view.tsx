"use client";

import type { DraftResponse } from "@/types/wiki";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiDraftDiff } from "@/components/wiki/wiki-draft-diff";
import type { BranchDetail, MiddleTab } from "./review-utils";

type ReviewDraftViewProps = {
  branch: BranchDetail | null;
  draft: DraftResponse | null;
  queueLoading: boolean;
  /** 1-based position of the branch in the filtered queue (0 when not found) */
  position: number;
  count: number;
  onSelectFile: (draftId: string) => void;
  tab: MiddleTab;
  onTabChange: (tab: MiddleTab) => void;
  /** Whether the "Compare with" picker may be shown at all (more than one branch loaded) */
  canCompare: boolean;
  compareOptions: { value: string; label: string }[];
  compareValue: string;
  onCompareChange: (value: string) => void;
  /** Text the diff is computed against */
  baseText: string;
  currentPage: string;
  loadingBase: boolean;
};

export function ReviewDraftView({
  branch,
  draft,
  queueLoading,
  position,
  count,
  onSelectFile,
  tab,
  onTabChange,
  canCompare,
  compareOptions,
  compareValue,
  onCompareChange,
  baseText,
  currentPage,
  loadingBase,
}: ReviewDraftViewProps) {
  const { t } = useI18n();

  if (!branch || !draft) {
    return (
      <section className="flex min-h-0 min-w-0 flex-1 items-center justify-center bg-background p-6">
        <p className="text-sm text-muted-foreground italic">
          {queueLoading ? "Loading…" : t("review.selectDraftPrompt", "Select a draft from the queue.")}
        </p>
      </section>
    );
  }

  const isCreate = draft.draft_kind === "create";
  const tabs: { id: MiddleTab; label: string }[] = isCreate
    ? [{ id: "proposed", label: t("wiki.banner.tabProposed", "Proposed") }]
    : [
        { id: "diff", label: t("wiki.banner.tabDiff", "Diff") },
        { id: "proposed", label: t("wiki.banner.tabProposed", "Proposed") },
        { id: "current", label: t("wiki.banner.tabCurrent", "Current page") },
      ];
  const effectiveTab: MiddleTab = isCreate ? "proposed" : tab;

  let body: React.ReactNode;
  if (effectiveTab === "diff") {
    body = loadingBase ? (
      <p className="text-sm text-muted-foreground italic">Loading current page…</p>
    ) : (
      <WikiDraftDiff oldText={baseText} newText={draft.content_md ?? ""} mode="unified" contextLines={3} />
    );
  } else if (effectiveTab === "proposed") {
    body = (draft.content_md ?? "").trim() ? (
      <WikiContent markdown={draft.content_md} />
    ) : (
      <p className="text-sm italic">{t("wiki.banner.emptyContent", "Empty content.")}</p>
    );
  } else {
    body = <WikiContent markdown={currentPage || "_(empty page)_"} />;
  }

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
      <header className="sticky top-0 z-10 flex flex-col gap-3 border-b bg-background px-6 pt-4 pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-amber-700 uppercase dark:text-amber-400">
                Nhánh đóng góp
              </span>
              <h1 className="truncate text-base font-semibold">{branch.name}</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{branch.description || "Không có mô tả nhánh."}</p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
            {position} / {count}
          </span>
        </div>

        {branch.has_conflict && <ConflictNotice />}

        {branch.drafts.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
              Tập tin thay đổi ({branch.drafts.length}):
            </span>
            <div className="flex flex-wrap gap-1.5">
              {branch.drafts.map((d) => {
                const active = d.id === draft.id;
                return (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => onSelectFile(d.id)}
                    className={cn(
                      "flex max-w-full items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors",
                      active ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted",
                    )}
                  >
                    <span className="material-symbols-outlined shrink-0" style={{ fontSize: 15 }}>
                      {d.draft_kind === "create" ? "add_box" : "edit"}
                    </span>
                    <span className="truncate">{d.page_title || d.page_slug}</span>
                    {d.has_conflict && <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-destructive" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1">
            {tabs.map((tb) => (
              <button
                key={tb.id}
                type="button"
                onClick={() => onTabChange(tb.id)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                  effectiveTab === tb.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                )}
              >
                {tb.label}
              </button>
            ))}
          </div>
          {effectiveTab === "diff" && !isCreate && canCompare && (
            <ComparePicker
              label={t("wiki.banner.compareWith", "Compare with:")}
              currentLabel={t("wiki.banner.tabCurrent", "Current page")}
              options={compareOptions}
              value={compareValue}
              onChange={onCompareChange}
            />
          )}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">{body}</div>
    </section>
  );
}

/** Banner shown when the branch cannot be merged cleanly into the main wiki. */
function ConflictNotice() {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-700 dark:text-rose-300">
      <span style={{ fontSize: 18 }} className="material-symbols-outlined shrink-0">
        warning
      </span>
      <p>
        <strong className="font-semibold">Xung đột phát hiện:</strong> Nhánh này có thay đổi bị xung đột với Wiki
        chính. Tác giả cần thực hiện rebase nhánh trước khi hợp nhất.
      </p>
    </div>
  );
}

type ComparePickerProps = {
  label: string;
  /** Label of the empty option, which compares against the live page. */
  currentLabel: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
};

/** Small select choosing which text the diff is computed against. */
function ComparePicker({ label, currentLabel, options, value, onChange }: ComparePickerProps) {
  const choices = [{ value: "", label: currentLabel }, ...options];
  return (
    <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-6 rounded-md border border-input bg-background px-1.5 text-xs text-foreground outline-none dark:bg-input/30"
      >
        {choices.map((choice) => (
          <option value={choice.value} key={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </label>
  );
}
