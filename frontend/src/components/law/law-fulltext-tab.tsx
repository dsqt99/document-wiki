"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { LegalDocDetail } from "@/types/legal-doc";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { FormattedInlineText } from "@/components/wiki/formatted-inline-text";
import { WikiContent } from "@/components/wiki/wiki-content";
import { slugPath } from "@/components/review/review-utils";

type CreatedPages = { overview_slug: string; article_slugs: (string | null)[]; end_section_slugs?: (string | null)[] };

function EditedBadge() {
  return (
    <span
      title="Nội dung đã được hiệu đính trên trang wiki"
      className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-400"
    >
      Đã hiệu đính
    </span>
  );
}

/** Opens the wiki page holding this part of the text, in edit mode when the user may edit. */
function PageAction({
  slug,
  canEdit,
  busy,
  onCreate,
}: {
  slug: string | null;
  canEdit: boolean;
  busy: boolean;
  onCreate: () => void;
}) {
  const cls = "inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-primary";
  if (slug) {
    return (
      <Link
        href={`/wiki/${slugPath(slug)}${canEdit ? "?edit=1" : ""}`}
        title={canEdit ? "Mở trang wiki để sửa nội dung (vd. lỗi OCR)" : "Mở trang wiki"}
        className={cls}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
          {canEdit ? "edit_note" : "open_in_new"}
        </span>
        {canEdit && <span>Sửa</span>}
      </Link>
    );
  }
  if (!canEdit) return null;
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onCreate}
      title="Tạo trang wiki cho văn bản này để sửa nội dung"
      className={cls + " disabled:opacity-50"}
    >
      <span className={"material-symbols-outlined" + (busy ? " animate-spin" : "")} style={{ fontSize: 16 }}>
        {busy ? "progress_activity" : "edit_note"}
      </span>
      <span>Sửa</span>
    </button>
  );
}

/** "Toàn văn": preamble and articles grouped under chapter headings, with a searchable index. */
export function LawFulltextTab({ doc }: { doc: LegalDocDetail }) {
  const router = useRouter();
  const { user, hasPermission } = useAuth();
  const canEdit = user?.role === "admin" || hasPermission("wiki:write:all");
  // -1 is the preamble; tail sections follow the article indexes.
  const [creating, setCreating] = useState<number | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const articles = doc.articles ?? [];
  const endSections = doc.end_sections ?? [];
  const preamble = (doc.preamble ?? "").trim();
  const needle = query.trim().toLowerCase();
  const matches = articles
    .map((a, i) => ({ a, i }))
    .filter(({ a }) => !needle || (a.heading ?? "").toLowerCase().includes(needle));
  const endMatches = endSections.map((section, i) => ({ section, i: articles.length + i }))
    .filter(({ section }) => !needle || section.title.toLowerCase().includes(needle));

  // Văn bản chưa có trang wiki theo điều: tách thành trang tổng quan + mỗi điều một trang, rồi mở trang cần sửa.
  const createAndEdit = async (target: number) => {
    setCreating(target);
    setCreateError(null);
    try {
      const res = await api<CreatedPages>(`/api/wiki/legal-docs/${encodeURIComponent(doc.id)}/pages`, {
        method: "POST",
        timeoutMs: 300_000,
      });
      const slug = target < 0 ? res.overview_slug : target < articles.length
        ? res.article_slugs[target] : res.end_section_slugs?.[target - articles.length];
      if (slug) router.push(`/wiki/${slugPath(slug)}?edit=1`);
      else setCreateError("Không xác định được trang Wiki của phần này");
    } catch (err: unknown) {
      setCreateError(err instanceof Error && err.message ? err.message : "Không tạo được trang wiki");
    } finally {
      setCreating(null);
    }
  };

  const jumpTo = (i: number) => {
    setActive(i);
    document.getElementById(`art-${i}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Theo dõi điều đang đọc: điều đầu tiên còn nằm trong dải phía trên khung nhìn.
  useEffect(() => {
    const count = (doc.articles?.length ?? 0) + (doc.end_sections?.length ?? 0);
    if (count === 0) return;
    const visible = new Set<number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const i = Number((e.target as HTMLElement).dataset.idx);
          if (e.isIntersecting) visible.add(i);
          else visible.delete(i);
        }
        if (visible.size > 0) setActive(Math.min(...visible));
      },
      { rootMargin: "-96px 0px -55% 0px" },
    );
    for (let i = 0; i < count; i++) {
      const el = document.getElementById(`art-${i}`);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [doc.articles, doc.end_sections]);

  // Giữ mục đang đọc trong vùng nhìn thấy của danh sách, chỉ cuộn danh sách chứ không cuộn trang.
  useEffect(() => {
    const list = listRef.current;
    const item = list?.querySelector<HTMLElement>(`[data-toc="${active}"]`);
    if (!list || !item) return;
    const top = item.offsetTop;
    const bottom = top + item.offsetHeight;
    if (top < list.scrollTop || bottom > list.scrollTop + list.clientHeight) {
      list.scrollTo({ top: top - list.clientHeight / 2 + item.offsetHeight / 2, behavior: "smooth" });
    }
  }, [active, query]);

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_17rem] 2xl:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 rounded-xl border bg-card p-6 md:p-8">
        {createError && (
          <p className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {createError}
          </p>
        )}
        {preamble && (
          <div className="mb-6 border-b pb-6 text-[15px]">
            <div className="mb-1 flex items-center justify-end gap-2">
              {doc.preamble_edited && <EditedBadge />}
              <PageAction
                slug={doc.overview_slug}
                canEdit={canEdit}
                busy={creating === -1}
                onCreate={() => createAndEdit(-1)}
              />
            </div>
            <WikiContent markdown={doc.preamble} />
          </div>
        )}
        {articles.length === 0 && endSections.length === 0 && !preamble && (
          <p className="text-sm text-muted-foreground">Văn bản chưa có nội dung trích xuất.</p>
        )}
        {articles.map((a, i) => {
          const prev = i > 0 ? articles[i - 1] : null;
          const showChapter = !!a.chapter_title && (!prev || prev.chapter_num !== a.chapter_num);
          const last = i === articles.length - 1;
          return (
            <section key={i} id={`art-${i}`} data-idx={i} className="scroll-mt-24">
              {showChapter && (
                <div className="my-6 text-center">
                  <p className="font-bold uppercase">Chương {a.chapter_num ?? ""}</p>
                  <p className="font-medium">{a.chapter_title}</p>
                </div>
              )}
              <div className={last ? "py-4" : "border-b border-border/50 py-4"}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-[15px] font-bold">
                    <FormattedInlineText text={a.heading} />
                  </h3>
                  <div className="flex shrink-0 items-center gap-2">
                    {a.edited && <EditedBadge />}
                    <PageAction
                      slug={a.wiki_slug}
                      canEdit={canEdit}
                      busy={creating === i}
                      onCreate={() => createAndEdit(i)}
                    />
                  </div>
                </div>
                {(a.content_md ?? "").trim() && (
                  <div className="mt-2 text-[15px]">
                    <WikiContent markdown={a.content_md} />
                  </div>
                )}
              </div>
            </section>
          );
        })}
        {endSections.map((section, i) => (
          <section key={`end-${i}`} id={`art-${articles.length + i}`} data-idx={articles.length + i} className="scroll-mt-24 border-t py-6">
            <div className="mb-3 flex items-start justify-between gap-3">
              <h3 className="text-base font-bold"><FormattedInlineText text={section.title} /></h3>
              <div className="flex shrink-0 items-center gap-2">
                {section.edited && <EditedBadge />}
                <PageAction slug={section.wiki_slug} canEdit={canEdit} busy={creating === articles.length + i}
                  onCreate={() => createAndEdit(articles.length + i)} />
              </div>
            </div>
            <WikiContent markdown={section.content_md} showToc={false} />
          </section>
        ))}
      </div>

      {(articles.length > 0 || endSections.length > 0) && (
        <aside className="flex flex-col gap-3 rounded-xl border bg-card p-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)]">
          <span className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
            Danh sách điều khoản ({articles.length})
          </span>
          <div className="relative">
            <span
              className="material-symbols-outlined pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted-foreground"
              style={{ fontSize: 16 }}
            >
              search
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Tìm điều khoản, phụ lục..."
              className="h-8 w-full rounded-lg border border-input bg-transparent pr-2 pl-8 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
          <div ref={listRef} className="relative max-h-[60vh] min-h-0 overflow-y-auto lg:max-h-none lg:flex-1">
            {matches.length === 0 && endMatches.length === 0 ? (
              <p className="px-2 py-3 text-xs text-muted-foreground">Không có kết quả</p>
            ) : (
              <ul className="flex flex-col">
                {matches.map(({ a, i }) => (
                  <li key={i}>
                    <button
                      type="button"
                      data-toc={i}
                      onClick={() => jumpTo(i)}
                      title={a.heading}
                      aria-current={i === active ? "true" : undefined}
                      className={
                        "w-full rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted hover:text-primary " +
                        (i === active ? "bg-muted font-medium text-primary" : "")
                      }
                    >
                      <span className="line-clamp-2">
                        <FormattedInlineText text={a.heading} />
                      </span>
                    </button>
                  </li>
                ))}
                {endMatches.length > 0 && (
                  <li className="mt-3 border-t px-2 pt-3 pb-1 text-[11px] font-semibold text-muted-foreground">Ghi chú &amp; phụ lục</li>
                )}
                {endMatches.map(({ section, i }) => (
                  <li key={`end-${i}`}>
                    <button type="button" data-toc={i} onClick={() => jumpTo(i)} title={section.title}
                      aria-current={i === active ? "true" : undefined}
                      className={"w-full rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted hover:text-primary " + (i === active ? "bg-muted font-medium text-primary" : "")}>
                      <span className="line-clamp-2"><FormattedInlineText text={section.title} /></span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
