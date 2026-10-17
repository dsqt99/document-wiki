"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { encodeSlugPath } from "@/components/wiki/wiki-pages-loader";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DraftResponse, WikiPageDetail } from "@/types/wiki";

type BranchDetail = {
  id: string;
  name: string;
  description?: string | null;
  status?: string;
  drafts: DraftResponse[];
};

/** Main-page content plus the merge box, loaded once per selected draft. */
type MergeState = { draftId: string; main: string; result: string };

const REVIEW_HREF = "/wiki/review?mine=true";

function conflictTemplate(main: string, mine: string): string {
  return [
    "<<<<<<< MAIN WIKI (Phiên bản mới nhất)",
    main,
    "=======",
    mine,
    ">>>>>>> NHÁNH CỦA BẠN (Bản thay đổi)",
  ].join("\n");
}

export default function BranchRebasePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const branchId = typeof params?.id === "string" ? params.id : "";

  const [branch, setBranch] = useState<BranchDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!branchId) return;
    let cancelled = false;
    api<BranchDetail>(`/api/wiki/branches/${encodeURIComponent(branchId)}`)
      .then((b) => {
        if (cancelled) return;
        const drafts = Array.isArray(b?.drafts) ? b.drafts : [];
        setBranch({ ...b, drafts });
        setSelectedId((prev) => {
          if (prev && drafts.some((d) => d.id === prev)) return prev;
          return (drafts.find((d) => d.has_conflict) ?? drafts[0])?.id ?? null;
        });
      })
      .catch(() => {
        if (!cancelled) router.replace(REVIEW_HREF);
      });
    return () => {
      cancelled = true;
    };
  }, [branchId, tick, router]);

  const drafts = branch?.drafts ?? [];
  const selected = drafts.find((d) => d.id === selectedId) ?? null;

  // ------------------------------------------------------------ main page + merge box
  const [merge, setMerge] = useState<MergeState | null>(null);
  const selectedKey = selected ? `${selected.id}:${selected.has_conflict ? 1 : 0}:${selected.updated_at}` : "";

  useEffect(() => {
    if (!selected) return;
    const draft = selected;
    const prefill = (main: string) =>
      setMerge({
        draftId: draft.id,
        main,
        result: draft.has_conflict ? conflictTemplate(main, draft.content_md) : draft.content_md,
      });
    if (draft.draft_kind === "create") {
      prefill("");
      return;
    }
    let cancelled = false;
    const qs = `?scope_type=${encodeURIComponent(draft.page_scope_type || "global")}&scope_id=${encodeURIComponent(draft.page_scope_id ?? "")}`;
    api<WikiPageDetail>(`/api/wiki/pages/${encodeSlugPath(draft.page_slug)}${qs}`)
      .then((page) => {
        if (!cancelled) prefill(page?.content_md ?? "");
      })
      .catch(() => {
        if (cancelled) return;
        setMerge({ draftId: draft.id, main: "", result: draft.content_md });
      });
    return () => {
      cancelled = true;
    };
    // selectedKey captures the fields of `selected` this effect depends on
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  const mergeForSelected = merge && selected && merge.draftId === selected.id ? merge : null;

  // ------------------------------------------------------------ submit
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ id: string; msg: string } | null>(null);

  const submit = useCallback(async () => {
    if (!selected || !mergeForSelected || submitting || !selected.has_conflict) return;
    setSubmitting(true);
    setError(null);
    try {
      await api(`/api/wiki/branches/${encodeURIComponent(branchId)}/rebase/${encodeURIComponent(selected.id)}`, {
        method: "POST",
        body: { resolved_content_md: mergeForSelected.result },
      });
      setTick((n) => n + 1);
    } catch (e) {
      setError({ id: selected.id, msg: e instanceof Error && e.message ? e.message : "Xử lý xung đột thất bại" });
    } finally {
      setSubmitting(false);
    }
  }, [selected, mergeForSelected, submitting, branchId]);

  if (!branch) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-sm text-muted-foreground">
        Đang tải thông tin nhánh đóng góp…
      </div>
    );
  }

  const allResolved = !drafts.some((d) => d.has_conflict);
  const errorMsg = error && selected && error.id === selected.id ? error.msg : null;

  return (
    <div className="flex min-h-full grow flex-col overflow-hidden rounded-xl bg-card">
      <header className="flex flex-wrap items-center gap-4 border-b px-6 pt-4 pb-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Link
            href={REVIEW_HREF}
            className="inline-flex w-fit items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
              arrow_back
            </span>
            Quay lại danh sách nháp
          </Link>
          <h1 className="flex flex-wrap items-center gap-2 text-base leading-6 font-medium">
            <span className="rounded-sm bg-rose-100 px-1.5 py-0.5 text-[10px] leading-[15px] font-medium text-rose-700 uppercase dark:bg-rose-500/15 dark:text-rose-300">
              Giải quyết xung đột
            </span>
            {branch.name}
          </h1>
          <p className="font-mono text-[11px] text-muted-foreground">ID Nhánh: {branch.id}</p>
        </div>
        {allResolved && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300">
              <span className="material-symbols-outlined" style={{ fontSize: 22 }}>
                check_circle
              </span>
              Đã xử lý hết xung đột!
            </span>
            <Button
              size="sm"
              nativeButton={false}
              render={<Link href={`/wiki/review?mine=true&draft=${encodeURIComponent(branch.id)}`} />}
            >
              Gửi duyệt hợp nhất
            </Button>
          </div>
        )}
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r">
          <div className="border-b px-3 py-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Danh sách tập tin
          </div>
          <ul className="flex flex-col gap-0.5 overflow-y-auto p-2">
            {drafts.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(d.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm",
                    d.id === selectedId ? "bg-primary/10 text-primary" : "hover:bg-muted",
                  )}
                >
                  <span className="material-symbols-outlined shrink-0" style={{ fontSize: 17 }}>
                    {d.draft_kind === "create" ? "add_box" : "description"}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{d.page_title || d.page_slug}</span>
                  {d.has_conflict && (
                    <Tooltip>
                      <TooltipTrigger
                        render={<span className="size-2 shrink-0 animate-pulse rounded-full bg-destructive" />}
                      />
                      <TooltipContent>Có xung đột</TooltipContent>
                    </Tooltip>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="min-w-0 p-4">
          {!selected ? (
            <p className="flex h-full items-center justify-center text-sm text-muted-foreground italic">Vui lòng chọn tập tin để xử lý.</p>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-semibold">{selected.page_title || selected.page_slug}</h2>
                  <span className="font-mono text-xs text-muted-foreground">{selected.page_slug}</span>
                </div>
                {selected.has_conflict ? (
                  <span className="rounded-full bg-rose-100 px-2.5 py-1 text-xs font-medium text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">
                    Đang có xung đột (base v{selected.base_version ?? "?"} vs main v{selected.page_version})
                  </span>
                ) : (
                  <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                    Không có xung đột
                  </span>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
                <Pane title="1. Bản trên Main Wiki">
                  <TextBlock
                    text={mergeForSelected ? mergeForSelected.main : null}
                    loadingText="Đang tải trang chính…"
                    emptyText="_(Trang trống)_"
                  />
                </Pane>
                <Pane title="2. Bản nháp của bạn">
                  <TextBlock text={selected.content_md} loadingText="" emptyText="_(Trang nháp trống)_" />
                </Pane>
                <Pane title="3. Kết quả hợp nhất (Kết quả sửa đổi)">
                  <textarea
                    value={mergeForSelected?.result ?? ""}
                    disabled={!mergeForSelected}
                    onChange={(e) => {
                      const value = e.target.value;
                      setMerge((m) => (m && m.draftId === selected.id ? { ...m, result: value } : m));
                    }}
                    placeholder="Hợp nhất thủ công nội dung tại đây..."
                    className="h-[480px] w-full resize-none rounded-md border bg-background p-2 font-mono text-xs leading-relaxed outline-none focus:border-primary"
                  />
                  {errorMsg && <p className="text-sm text-destructive">{errorMsg}</p>}
                  <Button onClick={submit} disabled={submitting || !selected.has_conflict || !mergeForSelected}>
                    {submitting ? "Đang xử lý…" : "Xác nhận giải quyết xung đột"}
                  </Button>
                </Pane>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Pane({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border p-3">
      <div className="text-xs font-semibold text-muted-foreground">{title}</div>
      {children}
    </div>
  );
}

function TextBlock({ text, loadingText, emptyText }: { text: string | null; loadingText: string; emptyText: string }) {
  return (
    <pre className="h-[480px] overflow-auto rounded-md bg-muted/40 p-2 font-mono text-xs leading-relaxed whitespace-pre-wrap">
      {text === null ? <span className="text-muted-foreground">{loadingText}</span> : text || emptyText}
    </pre>
  );
}
