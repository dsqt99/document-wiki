"use client";

import type { ReactNode } from "react";
import type { AiCheckResults, DraftResponse } from "@/types/wiki";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { WikiAiCheckPanel } from "@/components/wiki/wiki-ai-check-panel";
import { relativeTime, type NoteMode } from "./review-utils";

export const MIN_NOTE_CHARS = 20;

type ReviewSidePanelProps = {
  draft: DraftResponse | null;
  /** Freshest AI check data for the draft (from polling when available) */
  aiStatus: string;
  aiResults: AiCheckResults | null;
  isMine: boolean;
  branchConflict: boolean;
  noteMode: NoteMode | null;
  note: string;
  error: string | null;
  busy: boolean;
  onNoteChange: (value: string) => void;
  onOpenNote: (mode: NoteMode) => void;
  onCancelNote: () => void;
  onSubmitNote: () => void;
  onMerge: () => void;
  onWithdraw: () => void;
};

function Block({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">{label}</span>
      {children}
    </div>
  );
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-current/20 bg-background/20 px-1 font-mono text-[10px] leading-4 opacity-80">
      {children}
    </kbd>
  );
}

export function ReviewSidePanel({
  draft,
  aiStatus,
  aiResults,
  isMine,
  branchConflict,
  noteMode,
  note,
  error,
  busy,
  onNoteChange,
  onOpenNote,
  onCancelNote,
  onSubmitNote,
  onMerge,
  onWithdraw,
}: ReviewSidePanelProps) {
  const { t } = useI18n();

  if (!draft) {
    return (
      <aside className="w-[340px] shrink-0 overflow-y-auto border-l bg-card/50 p-4">
        <p className="text-xs text-muted-foreground italic">{t("review.noDraftSelected", "No draft selected.")}</p>
      </aside>
    );
  }

  const stats = draft.author_stats;
  const round = (draft.revision_round ?? 0) + 1;
  const meta = draft.draft_kind === "create" ? draft.suggested_metadata : null;
  const reviewers = draft.suggested_reviewers ?? [];
  const trimmedLen = note.trim().length;

  let actions: ReactNode;
  if (noteMode) {
    const reject = noteMode === "reject";
    actions = (
      <div className="flex flex-col gap-2">
        <label htmlFor="review-note" className="text-xs font-medium">
          {reject ? "Rejection reason" : "What needs to change?"}
        </label>
        <textarea
          key={noteMode}
          id="review-note"
          rows={4}
          autoFocus
          value={note}
          onChange={(e) => onNoteChange(e.target.value)}
          placeholder={
            reject ? "Tell the contributor why this was rejected…" : "Explain what to fix before resubmission…"
          }
          className="w-full resize-none rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
        <span className="text-[11px] text-muted-foreground tabular-nums">
          {trimmedLen}/{MIN_NOTE_CHARS} {t("wiki.banner.minChars", "characters minimum")}
        </span>
        <div className="flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancelNote}>
            Cancel <Kbd>Esc</Kbd>
          </Button>
          <Button
            variant={reject ? "destructive" : "default"}
            size="sm"
            disabled={busy || trimmedLen < MIN_NOTE_CHARS}
            onClick={onSubmitNote}
          >
            <span className={busy ? "material-symbols-outlined animate-spin" : "material-symbols-outlined"} style={{ fontSize: 16 }}>
              {busy ? "progress_activity" : reject ? "cancel" : "edit_note"}
            </span>
            {reject ? t("wiki.banner.confirmReject", "Confirm reject") : t("wiki.banner.sendBack", "Send back")}
          </Button>
        </div>
      </div>
    );
  } else if (isMine) {
    actions = (
      <div className="flex flex-col gap-2">
        <p className="text-xs text-muted-foreground italic">This is your draft.</p>
        {(draft.status === "pending" || draft.status === "needs_revision") && (
          <Button variant="outline" className="w-full" disabled={busy} onClick={onWithdraw}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
              remove_circle
            </span>
            {t("wiki.banner.withdraw", "Withdraw")}
          </Button>
        )}
      </div>
    );
  } else if (draft.status !== "pending") {
    actions = (
      <p className="text-xs text-muted-foreground italic">
        {draft.status === "needs_revision"
          ? t("wiki.banner.waitingResubmit", "Waiting for the author to resubmit.")
          : `Draft is ${draft.status}.`}
      </p>
    );
  } else {
    const rows: {
      label: string;
      icon: string;
      kbd: string;
      variant: "default" | "outline";
      onClick: () => void;
      disabled: boolean;
    }[] = [
      { label: "Approve & Merge", icon: "check_circle", kbd: "A", variant: "default", onClick: onMerge, disabled: busy || branchConflict },
      {
        label: t("wiki.banner.requestChangesBtn", "Request changes"),
        icon: "edit_note",
        kbd: "C",
        variant: "outline",
        onClick: () => onOpenNote("changes"),
        disabled: busy,
      },
      {
        label: t("wiki.banner.rejectBtn", "Reject"),
        icon: "cancel",
        kbd: "R",
        variant: "outline",
        onClick: () => onOpenNote("reject"),
        disabled: busy,
      },
    ];
    actions = (
      <div className="flex flex-col gap-2">
        {rows.map((r) => (
          <Button key={r.kbd} variant={r.variant} className="w-full justify-between" disabled={r.disabled} onClick={r.onClick}>
            <span className="flex items-center gap-1.5">
              <span
                className={busy && r.kbd === "A" ? "material-symbols-outlined animate-spin" : "material-symbols-outlined"}
                style={{ fontSize: 16 }}
              >
                {busy && r.kbd === "A" ? "progress_activity" : r.icon}
              </span>
              {r.label}
            </span>
            <Kbd>{r.kbd}</Kbd>
          </Button>
        ))}
      </div>
    );
  }

  const statsTitle = stats
    ? `${stats.approved} approved · ${stats.rejected} rejected${
        stats.needs_revision > 0 ? ` · ${stats.needs_revision} returned` : ""
      }`
    : undefined;

  return (
    <aside className="flex w-[340px] shrink-0 flex-col gap-5 overflow-y-auto border-l bg-card/50 p-4 text-sm">
      <Block label="Author">
        <span className="font-medium">{draft.author_name || "Unknown"}</span>
        {stats && stats.total_reviewed > 0 ? (
          <span className="text-xs text-muted-foreground tabular-nums" title={statsTitle}>
            {stats.approved}✓ · {Math.round((stats.accuracy ?? 0) * 100)}% accuracy
          </span>
        ) : (
          <span className="text-xs text-muted-foreground italic">first contribution</span>
        )}
      </Block>

      <Block label="Submitted">
        <span>{relativeTime(draft.created_at)}</span>
        <span className="text-[11px] text-muted-foreground">round {round}</span>
        {draft.note && <p className="text-xs text-muted-foreground italic">“{draft.note}”</p>}
        {draft.status === "needs_revision" && draft.last_returned_note && (
          <p className="text-xs">
            <span className="font-medium">{t("wiki.banner.reviewerAsked", "Reviewer asked:")}</span>{" "}
            {draft.last_returned_note}
          </p>
        )}
      </Block>

      {meta && (
        <Block label="Suggested page">
          {meta.slug && <span className="font-mono text-xs break-all">{meta.slug}</span>}
          <span className="text-xs text-muted-foreground">
            {[meta.page_type, meta.scope_type].filter(Boolean).join(" · ")}
          </span>
          {meta.knowledge_type_slugs && meta.knowledge_type_slugs.length > 0 && (
            <span className="text-xs text-muted-foreground">Tags: {meta.knowledge_type_slugs.join(", ")}</span>
          )}
        </Block>
      )}

      {reviewers.length > 0 && (
        <Block label="Suggested reviewers">
          <ul className="flex flex-col gap-1">
            {reviewers.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate">{r.name || r.email || "?"}</span>
                <span className="text-muted-foreground tabular-nums">{r.score}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}

      <Block label="AI pre-review">
        <WikiAiCheckPanel status={aiStatus} results={aiResults} />
      </Block>

      <div className="flex flex-col gap-2 border-t pt-4">
        {error && <p className="text-xs text-destructive">{error}</p>}
        {actions}
      </div>
    </aside>
  );
}
