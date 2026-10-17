"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { DraftResponse } from "@/types/wiki";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useIsEmbedded } from "@/lib/embed";
import { cn } from "@/lib/utils";
import { ReviewQueue } from "./review-queue";
import { ReviewDraftView } from "./review-draft-view";
import { MIN_NOTE_CHARS, ReviewSidePanel } from "./review-side-panel";
import { ShortcutHelp } from "./shortcut-help";
import {
  AI_ACTIVE_STATES,
  QUEUE_STATUSES,
  branchStatusFor,
  errorMessage,
  scopeKeyOf,
  scopeOptionsOf,
  slugPath,
  type BranchDetail,
  type BranchListItem,
  type MiddleTab,
  type NoteMode,
  type QueueStatus,
} from "./review-utils";

const AI_POLL_MS = 3000;

/** Per-draft UI state; it resets whenever the viewed draft (id or kind) changes. */
type ViewState = {
  key: string;
  noteMode: NoteMode | null;
  note: string;
  error: string | null;
  compare: string;
  tab: MiddleTab;
};

function freshView(key: string, kind: string | undefined): ViewState {
  return { key, noteMode: null, note: "", error: null, compare: "", tab: kind === "create" ? "proposed" : "diff" };
}

function isTextTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/** Three-column desk for reviewing contribution branches (route /wiki/review). */
export function ReviewDesk() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const embedded = useIsEmbedded();

  // ---- URL state ----
  const statusParam = searchParams.get("status");
  const status: QueueStatus = QUEUE_STATUSES.some((s) => s.value === statusParam)
    ? (statusParam as QueueStatus)
    : "pending";
  const mine = searchParams.get("mine") === "true";
  const draftParam = searchParams.get("draft") || null;
  const scope = searchParams.get("scope") || "";

  const updateParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    const qs = next.toString();
    router.replace(qs ? `/wiki/review?${qs}` : "/wiki/review", { scroll: false });
  };

  // ---- Queue ----
  const [reloadTick, setReloadTick] = useState(0);
  const apiStatus = branchStatusFor(status);
  const queueKey = `${apiStatus}|${mine}|${reloadTick}`;
  const [queue, setQueue] = useState<{ key: string; items: BranchListItem[] } | null>(null);

  useEffect(() => {
    let stale = false;
    const qs = new URLSearchParams({ status: apiStatus });
    if (mine) qs.set("mine", "true");
    api<BranchListItem[]>(`/api/wiki/branches?${qs.toString()}`)
      .then((res) => (Array.isArray(res) ? res : []))
      .catch(() => [] as BranchListItem[])
      .then((items) => {
        if (!stale) setQueue({ key: queueKey, items });
      });
    return () => {
      stale = true;
    };
  }, [apiStatus, mine, queueKey]);

  const queueLoading = queue?.key !== queueKey;
  const branches: BranchListItem[] = !queueLoading && queue ? queue.items : [];
  const filtered = scope ? branches.filter((b) => scopeKeyOf(b) === scope) : branches;
  const scopeOptions = scopeOptionsOf(branches);

  // Keep `draft` pointing at a branch that is actually listed.
  useEffect(() => {
    if (queueLoading) return;
    if (branches.length === 0) {
      if (draftParam) updateParams({ draft: null });
      return;
    }
    const pool = filtered.length > 0 ? filtered : branches;
    if (!draftParam || !pool.some((b) => b.id === draftParam)) updateParams({ draft: pool[0].id });
  });

  // ---- Selected branch ----
  const [detail, setDetail] = useState<{ key: string; data: BranchDetail | null } | null>(null);

  useEffect(() => {
    if (!draftParam) return;
    let stale = false;
    api<BranchDetail>(`/api/wiki/branches/${encodeURIComponent(draftParam)}`)
      .then((d): BranchDetail => ({ ...d, drafts: Array.isArray(d.drafts) ? d.drafts : [] }))
      .catch(() => null)
      .then((data) => {
        if (!stale) setDetail({ key: draftParam, data });
      });
    return () => {
      stale = true;
    };
  }, [draftParam]);

  const detailLoading = !!draftParam && detail?.key !== draftParam;
  const branch = draftParam && detail?.key === draftParam ? detail.data : null;

  const [fileSel, setFileSel] = useState<{ branchId: string; draftId: string } | null>(null);
  const draft: DraftResponse | null = branch
    ? (branch.drafts.find((d) => fileSel?.branchId === branch.id && d.id === fileSel.draftId) ??
      branch.drafts[0] ??
      null)
    : null;

  // ---- Per-draft UI state ----
  const viewKey = draft ? `${draft.id}:${draft.draft_kind}` : "";
  const [viewRaw, setViewRaw] = useState<ViewState>(() => freshView("", undefined));
  const view = viewRaw.key === viewKey ? viewRaw : freshView(viewKey, draft?.draft_kind);
  const patchView = (patch: Partial<ViewState>) =>
    setViewRaw((prev) => ({ ...(prev.key === viewKey ? prev : freshView(viewKey, draft?.draft_kind)), ...patch }));

  const [busy, setBusy] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  // ---- Current page content (base of the diff) ----
  const pageKey =
    draft && draft.draft_kind !== "create" && draft.page_slug
      ? JSON.stringify([draft.page_slug, draft.page_scope_type ?? "", draft.page_scope_id ?? ""])
      : null;
  const [pageRes, setPageRes] = useState<{ key: string; content: string } | null>(null);

  useEffect(() => {
    if (!pageKey) return;
    const [slug, scopeType, scopeId] = JSON.parse(pageKey) as [string, string, string];
    const qs = new URLSearchParams();
    if (scopeType) qs.set("scope_type", scopeType);
    if (scopeId) qs.set("scope_id", scopeId);
    const query = qs.toString();
    let stale = false;
    api<{ content_md?: string }>(`/api/wiki/pages/${slugPath(slug)}${query ? `?${query}` : ""}`)
      .then((p) => p?.content_md ?? "")
      .catch(() => "")
      .then((content) => {
        if (!stale) setPageRes({ key: pageKey, content });
      });
    return () => {
      stale = true;
    };
  }, [pageKey]);

  const loadingPage = !!pageKey && pageRes?.key !== pageKey;
  const currentPage = pageKey && pageRes?.key === pageKey ? pageRes.content : "";

  // ---- AI pre-review polling ----
  const [live, setLive] = useState<DraftResponse | null>(null);
  const aiSource = draft && live && live.id === draft.id ? live : draft;
  const aiStatus = aiSource?.ai_check_status ?? "pending";
  const draftId = draft?.id ?? null;
  const polling = !!draftId && AI_ACTIVE_STATES.has(aiStatus);

  useEffect(() => {
    if (!polling || !draftId) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      api<DraftResponse>(`/api/wiki/drafts/${encodeURIComponent(draftId)}`)
        .then((d) => {
          if (!stopped && d && d.id === draftId) setLive(d);
        })
        .catch(() => {
          /* polling errors are ignored */
        });
    }, AI_POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [polling, draftId]);

  // ---- Compare with ----
  const compareOptions = draft
    ? branches
        .filter(
          (b) =>
            b.id !== draft.id &&
            b.draft_kind !== "create" &&
            b.page_id !== undefined &&
            b.page_id !== null &&
            b.page_id === draft.page_id,
        )
        .map((b) => ({
          value: b.id,
          label: `Draft by ${b.author_name || "?"}${(b.revision_round ?? 0) > 0 ? ` (r${(b.revision_round ?? 0) + 1})` : ""}`,
        }))
    : [];
  const compareItem = view.compare ? branches.find((b) => b.id === view.compare) : undefined;
  const baseText = compareItem?.content_md ?? currentPage;

  // ---- Navigation / actions ----
  const position = draftParam ? filtered.findIndex((b) => b.id === draftParam) + 1 : 0;
  const isMine = !!user && !!draft && !!draft.author_id && draft.author_id === user.id;

  const move = (delta: number) => {
    if (filtered.length === 0) return;
    const idx = filtered.findIndex((b) => b.id === draftParam);
    const next = idx < 0 ? 0 : Math.min(Math.max(idx + delta, 0), filtered.length - 1);
    if (filtered[next].id !== draftParam) updateParams({ draft: filtered[next].id });
  };

  const finishBranch = (branchId: string) => {
    const oldIndex = filtered.findIndex((b) => b.id === branchId);
    const remaining = filtered.filter((b) => b.id !== branchId);
    setQueue((q) => (q ? { ...q, items: q.items.filter((b) => b.id !== branchId) } : q));
    patchView({ noteMode: null, note: "", error: null });
    if (remaining.length > 0) {
      updateParams({ draft: remaining[Math.min(Math.max(oldIndex, 0), remaining.length - 1)].id });
    } else {
      updateParams({ draft: null });
    }
  };

  const closeBranch = async (fallback: string) => {
    if (!branch) return;
    setBusy(true);
    patchView({ error: null });
    try {
      await api(`/api/wiki/branches/${encodeURIComponent(branch.id)}/close`, { method: "POST" });
      finishBranch(branch.id);
    } catch (err) {
      patchView({ error: errorMessage(err, fallback) });
    } finally {
      setBusy(false);
    }
  };

  const merge = async () => {
    if (!branch || busy) return;
    setBusy(true);
    patchView({ error: null });
    const note = view.note.trim();
    try {
      await api(`/api/wiki/branches/${encodeURIComponent(branch.id)}/merge`, {
        method: "POST",
        body: note ? { reviewer_note: note } : {},
      });
      finishBranch(branch.id);
    } catch (err) {
      patchView({ error: errorMessage(err, "Hợp nhất nhánh thất bại") });
    } finally {
      setBusy(false);
    }
  };

  const submitNote = () => {
    if (!view.noteMode || busy) return;
    if (view.note.trim().length < MIN_NOTE_CHARS) {
      patchView({ error: `Vui lòng nhập ít nhất ${MIN_NOTE_CHARS} ký tự.` });
      return;
    }
    // The close endpoint takes no body: the note is not transmitted (documented backend behaviour).
    void closeBranch("Thao tác thất bại");
  };

  const withdraw = () => {
    if (busy) return;
    if (!window.confirm("Bạn có chắc chắn muốn hủy bỏ nhánh đóng góp này không?")) return;
    void closeBranch("Hủy nhánh thất bại");
  };

  const openNote = (mode: NoteMode) =>
    patchView(mode === "reject" ? { noteMode: mode, note: "", error: null } : { noteMode: mode, error: null });

  // ---- Keyboard shortcuts (re-bound each render so handlers see current state) ----
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      if (e.key === "Escape") {
        if (view.noteMode) {
          e.preventDefault();
          patchView({ noteMode: null });
        } else if (helpOpen) {
          setHelpOpen(false);
        }
        return;
      }
      if (isTextTarget(e.target)) return;
      const pending = draft?.status === "pending";
      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          move(1);
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          move(-1);
          break;
        case "a":
          if (pending && !view.noteMode) {
            e.preventDefault();
            void merge();
          }
          break;
        case "r":
          if (pending) {
            e.preventDefault();
            openNote("reject");
          }
          break;
        case "c":
          if (pending) {
            e.preventDefault();
            openNote("changes");
          }
          break;
        case "?":
          e.preventDefault();
          setHelpOpen((o) => !o);
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div
      className={cn(
        "flex h-screen min-h-0 border-t",
        embedded ? "-m-4 md:-m-5" : "-mx-6 -mt-4 -mb-6 md:-mx-8 md:-mb-8 lg:-mx-10 lg:-mb-10",
      )}
    >
      <ReviewQueue
        status={status}
        mine={mine}
        scope={scope}
        scopeOptions={scopeOptions}
        total={branches.length}
        items={filtered}
        loading={queueLoading}
        selectedId={draftParam}
        onStatusChange={(s) => updateParams({ status: s, draft: null })}
        onMineChange={(m) => updateParams({ mine: m ? "true" : null, draft: null })}
        onScopeChange={(s) => updateParams({ scope: s || null, draft: null })}
        onSelect={(id) => updateParams({ draft: id })}
        onRefresh={() => setReloadTick((n) => n + 1)}
        onToggleHelp={() => setHelpOpen((o) => !o)}
      />

      <ReviewDraftView
        branch={branch}
        draft={draft}
        queueLoading={queueLoading || detailLoading}
        position={position}
        count={filtered.length}
        onSelectFile={(id) => branch && setFileSel({ branchId: branch.id, draftId: id })}
        tab={view.tab}
        onTabChange={(tab) => patchView({ tab })}
        canCompare={branches.length > 1}
        compareOptions={compareOptions}
        compareValue={view.compare}
        onCompareChange={(compare) => patchView({ compare })}
        baseText={baseText}
        currentPage={currentPage}
        loadingBase={loadingPage || detailLoading}
      />

      <ReviewSidePanel
        draft={draft}
        aiStatus={aiStatus}
        aiResults={aiSource?.ai_check_results ?? null}
        isMine={isMine}
        branchConflict={!!branch?.has_conflict}
        noteMode={view.noteMode}
        note={view.note}
        error={view.error}
        busy={busy}
        onNoteChange={(note) => patchView({ note })}
        onOpenNote={openNote}
        onCancelNote={() => patchView({ noteMode: null, note: "", error: null })}
        onSubmitNote={submitNote}
        onMerge={() => void merge()}
        onWithdraw={withdraw}
      />

      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}
    </div>
  );
}
