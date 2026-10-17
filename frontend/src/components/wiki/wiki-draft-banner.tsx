"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WikiAiCheckPanel } from "@/components/wiki/wiki-ai-check-panel";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiDraftDiff } from "@/components/wiki/wiki-draft-diff";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { AiCheckResults, DraftResponse } from "@/types/wiki";

const MIN_NOTE = 20;
const POLL_MS = 3000;

type Props = {
  drafts: DraftResponse[];
  currentContent?: string;
  currentUserId?: string | null;
  onApproved: (id: string) => void;
  onRejected: (id: string) => void;
  onChangesRequested?: (id: string) => void;
  onResubmitDraft?: (draft: DraftResponse) => void;
  onWithdrawn?: (id: string) => void;
};

type AiState = { status: string; results: AiCheckResults | null };
type NoteMode = "reject" | "request" | null;
type ViewTab = "diff" | "proposed" | "current";

function errMsg(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

export function WikiDraftBanner({
  drafts,
  currentContent = "",
  currentUserId = null,
  onApproved,
  onRejected,
  onChangesRequested,
  onResubmitDraft,
  onWithdrawn,
}: Props) {
  const { t, lang } = useI18n();
  const [index, setIndex] = useState(0);
  const [aiOverride, setAiOverride] = useState<Record<string, AiState>>({});
  const [viewState, setViewState] = useState<{ id: string; tab: ViewTab; compare: string }>({
    id: "",
    tab: "diff",
    compare: "current",
  });
  const [noteState, setNoteState] = useState<{ id: string; mode: NoteMode; text: string }>({
    id: "",
    mode: null,
    text: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ id: string; msg: string } | null>(null);

  const total = drafts.length;
  const idx = Math.min(index, Math.max(0, total - 1));
  const draft = drafts[idx] as DraftResponse | undefined;
  const draftId = draft?.id ?? "";

  const ai: AiState = draft
    ? (aiOverride[draft.id] ?? { status: draft.ai_check_status, results: draft.ai_check_results })
    : { status: "pending", results: null };
  const aiStatus = ai.status;

  // Poll the draft while its AI pre-review has not finished.
  useEffect(() => {
    if (!draftId || (aiStatus !== "pending" && aiStatus !== "running")) return;
    let cancelled = false;
    const timer = setInterval(() => {
      api<DraftResponse>(`/api/wiki/drafts/${encodeURIComponent(draftId)}`)
        .then((d) => {
          if (cancelled || !d) return;
          setAiOverride((prev) => ({
            ...prev,
            [draftId]: { status: d.ai_check_status, results: d.ai_check_results },
          }));
        })
        .catch(() => {
          /* keep polling; transient errors are ignored */
        });
    }, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [draftId, aiStatus]);

  if (!draft) return null;

  const isCreate = draft.draft_kind === "create";
  const tab: ViewTab = isCreate ? "proposed" : viewState.id === draft.id ? viewState.tab : "diff";
  const compare = viewState.id === draft.id ? viewState.compare : "current";
  const setTab = (v: ViewTab) => setViewState({ id: draft.id, tab: v, compare });
  const setCompare = (v: string) => setViewState({ id: draft.id, tab, compare: v });

  const noteMode: NoteMode = noteState.id === draft.id ? noteState.mode : null;
  const noteText = noteState.id === draft.id ? noteState.text : "";
  const openNote = (mode: NoteMode) => {
    setNoteState({ id: draft.id, mode, text: "" });
    setError(null);
  };

  const status = draft.status;
  const needsRevision = status === "needs_revision";
  const withdrawn = status === "withdrawn";
  const isMine = !!currentUserId && draft.author_id === currentUserId;
  const author = draft.author_name || "Unknown";

  const titleKey = needsRevision
    ? "wiki.banner.waitingAuthor"
    : withdrawn
      ? "wiki.banner.withdrawn"
      : "wiki.banner.pendingDraft";
  const titleFallback = needsRevision
    ? "Waiting for {name} to revise"
    : withdrawn
      ? "Withdrawn by {name}"
      : "Pending draft from {name}";
  const titleText = t(titleKey, titleFallback).replace(/\{name\}/g, author);

  let created = "";
  try {
    created = new Date(draft.created_at).toLocaleString(lang === "vi" ? "vi-VN" : "en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    created = draft.created_at;
  }

  const stats = draft.author_stats;
  const statsTier = stats
    ? stats.total_reviewed >= 10 && stats.accuracy >= 0.9
      ? "high"
      : stats.total_reviewed >= 3 && stats.accuracy >= 0.7
        ? "mid"
        : "low"
    : null;

  const otherEditDrafts = drafts.filter((d) => d.id !== draft.id && d.draft_kind !== "create");
  const compareDraft = compare === "current" ? null : otherEditDrafts.find((d) => d.id === compare);
  const compareText = compareDraft ? compareDraft.content_md : currentContent;

  const meta = draft.suggested_metadata ?? {};
  const tags = meta.knowledge_type_slugs ?? [];

  const leaveQueue = () => setIndex(Math.max(0, idx - 1));

  const run = async (fn: () => Promise<void>, fallback: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError({ id: draft.id, msg: errMsg(e, fallback) });
    } finally {
      setBusy(false);
    }
  };

  const approve = () =>
    run(async () => {
      await api(`/api/wiki/drafts/${encodeURIComponent(draft.id)}/approve`, {
        method: "POST",
        body: { allow_conflict: !!draft.has_conflict },
      });
      leaveQueue();
      onApproved(draft.id);
    }, "Approve failed");

  const submitNote = () => {
    if (noteText.trim().length < MIN_NOTE) {
      setError({ id: draft.id, msg: "Please write at least 20 characters explaining your decision." });
      return;
    }
    const mode = noteMode;
    return run(async () => {
      const path = mode === "reject" ? "reject" : "request-changes";
      await api(`/api/wiki/drafts/${encodeURIComponent(draft.id)}/${path}`, {
        method: "POST",
        body: { reviewer_note: noteText.trim() },
      });
      setNoteState({ id: "", mode: null, text: "" });
      if (mode === "reject") {
        leaveQueue();
        onRejected(draft.id);
      } else {
        onChangesRequested?.(draft.id);
      }
    }, "Action failed");
  };

  const withdraw = () => {
    if (!window.confirm("Withdraw this draft? It will be removed from the review queue.")) return;
    return run(async () => {
      await api(`/api/wiki/drafts/${encodeURIComponent(draft.id)}/withdraw`, { method: "POST" });
      leaveQueue();
      onWithdrawn?.(draft.id);
    }, "Withdraw failed");
  };

  const shownError = error && error.id === draft.id ? error.msg : null;

  return (
    <div
      className={cn(
        "rounded-xl border p-4",
        needsRevision
          ? "border-blue-200 bg-blue-50/70 dark:border-blue-500/30 dark:bg-blue-500/10"
          : "border-amber-200 bg-amber-50/70 dark:border-amber-500/30 dark:bg-amber-500/10",
      )}
    >
      {/* title row */}
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn("material-symbols-outlined", needsRevision ? "text-blue-600" : "text-amber-600")}
          style={{ fontSize: 20 }}
        >
          {needsRevision ? "edit_note" : "pending"}
        </span>
        <span className="text-sm font-semibold">{titleText}</span>
        <span className="text-xs text-muted-foreground">· {created}</span>
        {draft.revision_round > 0 && (
          <span className="rounded-full border bg-background/70 px-2 py-0.5 text-[11px]">round {draft.revision_round}</span>
        )}
        {draft.has_conflict && (
          <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[11px] text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
            conflict — page advanced past v{draft.base_version ?? "?"} to v{draft.page_version}
          </span>
        )}
        {stats && (
          <Tooltip>
            <TooltipTrigger
              render={
                <span
                  className={cn(
                    "cursor-default rounded-full border px-2 py-0.5 text-[11px] tabular-nums",
                    statsTier === "high" &&
                      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
                    statsTier === "mid" &&
                      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
                    statsTier === "low" && "bg-background/70 text-muted-foreground",
                  )}
                />
              }
            >
              {stats.approved}✓ · {Math.round(stats.accuracy * 100)}%
            </TooltipTrigger>
            <TooltipContent>
              {stats.approved} approved · {stats.rejected} rejected
              {stats.needs_revision > 0 ? ` · ${stats.needs_revision} returned` : ""}
            </TooltipContent>
          </Tooltip>
        )}
        {total > 1 && (
          <div className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Previous draft"
              disabled={idx === 0}
              onClick={() => setIndex(Math.max(0, idx - 1))}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                chevron_left
              </span>
            </Button>
            <span className="tabular-nums">
              {idx + 1}/{total}
            </span>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Next draft"
              disabled={idx >= total - 1}
              onClick={() => setIndex(Math.min(total - 1, idx + 1))}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                chevron_right
              </span>
            </Button>
          </div>
        )}
      </div>

      {/* secondary lines */}
      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {draft.note && <p className="italic">“{draft.note}”</p>}
        {draft.last_returned_note && (
          <p>
            <span className="font-medium text-foreground">{t("wiki.banner.reviewerAsked", "Reviewer asked:")}</span>{" "}
            {draft.last_returned_note}
          </p>
        )}
        {draft.suggested_reviewers?.length > 0 && (
          <p>
            <span className="font-medium text-foreground">
              {t("wiki.banner.suggestedReviewers", "Suggested reviewers:")}
            </span>{" "}
            {draft.suggested_reviewers.map((r) => `${r.name || r.email || "?"} (${r.score})`).join(", ")}
          </p>
        )}
        {isCreate && (
          <>
            <p className="font-mono">
              Slug: {meta.slug || draft.page_slug} · Type: {meta.page_type || "concept"} · Scope:{" "}
              {meta.scope_type || draft.page_scope_type}
              {(meta.scope_id ?? draft.page_scope_id) ? ` (${draft.page_scope_name || meta.scope_id || draft.page_scope_id})` : ""}
            </p>
            {tags.length > 0 && <p>Tags: {tags.join(", ")}</p>}
          </>
        )}
      </div>

      {/* view tabs */}
      <div className="mt-3 overflow-hidden rounded-lg border bg-background">
        <div className="flex flex-wrap items-center gap-1 border-b px-2 pt-1.5">
          {(isCreate ? (["proposed"] as const) : (["diff", "proposed", "current"] as const)).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={cn(
                "-mb-px border-b-2 px-3 py-1.5 text-xs font-medium",
                tab === k
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {k === "diff"
                ? t("wiki.banner.tabDiff", "Diff")
                : k === "proposed"
                  ? t("wiki.banner.tabProposed", "Proposed")
                  : t("wiki.banner.tabCurrent", "Current")}
            </button>
          ))}
          {tab === "diff" && !isCreate && (
            <div className="ml-auto flex items-center gap-2 pb-1 text-xs">
              <span className="text-muted-foreground">{t("wiki.banner.compareWith", "Compare with:")}</span>
              <Select value={compare} onValueChange={(v) => setCompare(v ? String(v) : "current")}>
                <SelectTrigger size="sm" className="h-7 min-w-40 text-xs">
                  <SelectValue>
                    {() =>
                      compareDraft
                        ? `Draft by ${compareDraft.author_name || "Unknown"} (round ${compareDraft.revision_round + 1})`
                        : t("wiki.banner.tabCurrent", "Current page")
                    }
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="current">{t("wiki.banner.tabCurrent", "Current page")}</SelectItem>
                  {otherEditDrafts.map((d) => (
                    <SelectItem key={d.id} value={d.id}>
                      Draft by {d.author_name || "Unknown"} (round {d.revision_round + 1})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto p-3">
          {tab === "diff" ? (
            <WikiDraftDiff oldText={compareText} newText={draft.content_md} mode="unified" contextLines={3} />
          ) : tab === "proposed" ? (
            draft.content_md.trim() ? (
              <WikiContent markdown={draft.content_md} />
            ) : (
              <p className="text-sm text-muted-foreground italic">{t("wiki.banner.emptyContent", "Empty content.")}</p>
            )
          ) : (
            <WikiContent markdown={currentContent.trim() ? currentContent : "_(empty page)_"} />
          )}
        </div>
      </div>

      <WikiAiCheckPanel className="mt-3" status={ai.status} results={ai.results} />

      {/* note form */}
      {noteMode && (
        <div className="mt-3 grid gap-1.5">
          <label className="text-xs font-medium" htmlFor={`draft-note-${draft.id}`}>
            {noteMode === "reject"
              ? t("wiki.banner.rejectLabel", "Reason for rejection (required)")
              : t("wiki.banner.requestChangesLabel", "Request changes — note for the author (required)")}
          </label>
          <textarea
            id={`draft-note-${draft.id}`}
            value={noteText}
            onChange={(e) => setNoteState({ id: draft.id, mode: noteMode, text: e.target.value })}
            placeholder={
              noteMode === "reject"
                ? t("wiki.banner.rejectPrompt", "Explain why this draft is rejected…")
                : t("wiki.banner.requestChangesPrompt", "Explain what the author should fix…")
            }
            rows={3}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <span
            className={cn(
              "text-[11px] tabular-nums",
              noteText.trim().length >= MIN_NOTE ? "text-muted-foreground" : "text-amber-700 dark:text-amber-300",
            )}
          >
            {noteText.trim().length}/{MIN_NOTE} {t("wiki.banner.minChars", "characters minimum")}
          </span>
        </div>
      )}

      {shownError && <p className="mt-2 text-sm text-destructive">{shownError}</p>}

      {/* actions */}
      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        {noteMode ? (
          <>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => openNote(null)}>
              {t("common.cancel", "Cancel")}
            </Button>
            {noteMode === "reject" ? (
              <Button variant="destructive" size="sm" disabled={busy} onClick={submitNote}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  cancel
                </span>
                {t("wiki.banner.confirmReject", "Confirm reject")}
              </Button>
            ) : (
              <Button size="sm" disabled={busy} onClick={submitNote}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  edit_note
                </span>
                {t("wiki.banner.sendBack", "Send back")}
              </Button>
            )}
          </>
        ) : isMine ? (
          <>
            {needsRevision && onResubmitDraft && (
              <Button size="sm" disabled={busy} onClick={() => onResubmitDraft(draft)}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  edit
                </span>
                {t("wiki.banner.editResubmit", "Edit & resubmit")}
              </Button>
            )}
            {!withdrawn ? (
              <Button variant="outline" size="sm" disabled={busy} onClick={withdraw}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  remove_circle
                </span>
                {t("wiki.banner.withdraw", "Withdraw")}
              </Button>
            ) : (
              <span className="text-xs text-muted-foreground">
                {t("wiki.banner.withdrawnNotice", "You withdrew this draft.")}
              </span>
            )}
          </>
        ) : needsRevision ? (
          <span className="text-xs text-muted-foreground">
            {t("wiki.banner.waitingResubmit", "Waiting for the author to resubmit.")}
          </span>
        ) : withdrawn ? (
          <span className="text-xs text-muted-foreground">
            {t("wiki.banner.noLongerReview", "This draft is no longer under review.")}
          </span>
        ) : (
          <>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => openNote("request")}>
              {t("wiki.banner.requestChangesBtn", "Request changes")}
            </Button>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => openNote("reject")}>
              {t("wiki.banner.rejectBtn", "Reject")}
            </Button>
            <Button size="sm" disabled={busy} onClick={approve}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                check_circle
              </span>
              {t("wiki.banner.approveBtn", "Approve")}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
