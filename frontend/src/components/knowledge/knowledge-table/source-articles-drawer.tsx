"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { WikiPageSummary } from "@/types/wiki";

type Props = {
  source?: { id: string; title: string; file_name?: string | null };
  sourceId?: string;
  sourceTitle?: string;
  onClose?: () => void;
};

type PageLite = Pick<WikiPageSummary, "slug" | "title" | "summary">;

const ARTICLE_PREFIX = "Điều ";
const collator = new Intl.Collator("vi", { numeric: true, sensitivity: "base" });

function isArticle(p: PageLite): boolean {
  return (p.title ?? "").startsWith(ARTICLE_PREFIX);
}

/** Short label: the part before the first " - " separator. */
function shortTitle(title: string): string {
  const idx = title.indexOf(" - ");
  return idx > 0 ? title.slice(0, idx) : title;
}

/** Inline table-row drawer listing the "Điều" pages compiled from one source. */
export function SourceArticlesDrawer({ source, sourceId, onClose }: Props) {
  const id = source?.id ?? sourceId ?? "";
  // pages are keyed by the source id they were fetched for, so stale data never shows
  const [result, setResult] = useState<{ id: string; pages: PageLite[] } | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    api<unknown>(`/api/wiki/pages?source_id=${encodeURIComponent(id)}&limit=1000`)
      .then((res) => {
        if (!cancelled) setResult({ id, pages: Array.isArray(res) ? (res as PageLite[]) : [] });
      })
      .catch(() => {
        if (!cancelled) setResult({ id, pages: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const loading = !!id && result?.id !== id;
  const pages = result?.id === id ? result.pages : [];

  const overview = pages.find((p) => !isArticle(p) || p.slug.includes("tong-quan"));
  const articles = pages.filter(isArticle).sort((a, b) => collator.compare(a.title, b.title));
  const others = pages.filter((p) => p !== overview && !isArticle(p));

  const needle = filter.trim().toLowerCase();
  const visibleArticles = needle
    ? articles.filter(
        (p) =>
          p.title.toLowerCase().includes(needle) ||
          p.slug.toLowerCase().includes(needle) ||
          (p.summary ?? "").toLowerCase().includes(needle)
      )
    : articles;

  return (
    <div className="animate-in fade-in border-t bg-muted/40 px-6 py-4 duration-200">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1.5 text-xs font-semibold">
            <span className="material-symbols-outlined text-primary" style={{ fontSize: 17 }}>
              menu_book
            </span>
            Mục lục Điều luật ({articles.length} Điều)
          </span>
          {overview && (
            <Link
              href={`/wiki/${overview.slug}`}
              className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/15"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
                open_in_new
              </span>
              Xem toàn văn Trang Tổng quan &amp; Căn cứ
            </Link>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <div className="relative w-[200px] sm:w-[280px]">
            <span
              className="material-symbols-outlined pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted-foreground"
              style={{ fontSize: 15 }}
            >
              search
            </span>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Lọc số Điều (VD: Điều 4, Điều 15)..."
              className="h-7 w-full rounded-md border bg-background pr-7 pl-7 text-xs outline-none focus:ring-2 focus:ring-primary/30"
            />
            {filter && (
              <button
                type="button"
                onClick={() => setFilter("")}
                className="absolute top-1/2 right-2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground"
                aria-label="Xóa"
              >
                ✕
              </button>
            )}
          </div>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              title="Đóng bảng Điều"
              aria-label="Đóng bảng Điều"
              className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 17 }}>
                close
              </span>
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
          <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>
            progress_activity
          </span>
          Đang tải danh sách Điều...
        </div>
      ) : pages.length === 0 ? (
        <p className="py-4 text-xs text-muted-foreground">Văn bản này chưa có trang Wiki Điều luật nào được bóc tách.</p>
      ) : (
        <>
          {articles.length > 0 &&
            (visibleArticles.length === 0 ? (
              <p className="py-3 text-xs text-muted-foreground">
                Không tìm thấy Điều nào khớp với &quot;{filter.trim()}&quot;
              </p>
            ) : (
              <div className="grid max-h-[320px] grid-cols-1 gap-1.5 overflow-y-auto sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                {visibleArticles.map((p) => (
                  <Link
                    key={p.slug}
                    href={`/wiki/${p.slug}`}
                    title={p.title}
                    className="group flex min-w-0 items-center gap-2 rounded-md border border-border/60 bg-card px-2.5 py-1.5 text-xs hover:border-primary/40 hover:text-primary"
                  >
                    <span className="size-1.5 shrink-0 rounded-full bg-emerald-500 transition-transform group-hover:scale-150" />
                    <span className="truncate">{shortTitle(p.title)}</span>
                  </Link>
                ))}
              </div>
            ))}

          {others.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t pt-3">
              <span className="text-[11px] text-muted-foreground">Các trang tri thức liên quan ({others.length}):</span>
              {others.map((p) => (
                <Link
                  key={p.slug}
                  href={`/wiki/${p.slug}`}
                  title={p.title}
                  className="max-w-[240px] truncate rounded-full bg-secondary px-2 py-0.5 text-[11px] hover:text-primary"
                >
                  {p.title}
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
