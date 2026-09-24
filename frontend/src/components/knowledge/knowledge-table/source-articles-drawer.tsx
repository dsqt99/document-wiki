"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { WikiPageSummary } from "@/types/wiki";

interface Props {
  sourceId?: string;
  sourceTitle?: string;
  source?: { id: string; title: string; file_name?: string };
  onClose?: () => void;
}

export function SourceArticlesDrawer({ sourceId, sourceTitle, source, onClose }: Props) {
  const effectiveId = source?.id || sourceId || "";
  const effectiveTitle = source?.title || sourceTitle || "";

  const [pages, setPages] = useState<WikiPageSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!effectiveId) return;
    let isMounted = true;
    setLoading(true);

    api<WikiPageSummary[]>(`/api/wiki/pages?source_id=${effectiveId}&limit=1000`)
      .then((res) => {
        if (isMounted) {
          const list = Array.isArray(res) ? res : [];
          setPages(list);
        }
      })
      .catch((err) => {
        console.error("Failed to load source articles:", err);
        if (isMounted) setPages([]);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [effectiveId]);

  // Separate overview page from articles
  const overviewPage = pages.find(
    (p) => !p.title.startsWith("Điều ") || p.slug.includes("tong-quan")
  );

  const articles = pages
    .filter((p) => p.title.startsWith("Điều "))
    .sort((a, b) => a.title.localeCompare(b.title, "vi", { numeric: true }));

  const otherPages = pages.filter(
    (p) => p !== overviewPage && !p.title.startsWith("Điều ")
  );

  const filteredArticles = search.trim()
    ? articles.filter((a) => {
        const q = search.trim().toLowerCase();
        return (
          a.title.toLowerCase().includes(q) ||
          a.slug.toLowerCase().includes(q) ||
          (a.summary && a.summary.toLowerCase().includes(q))
        );
      })
    : articles;

  return (
    <div className="bg-muted/40 border-t border-border/80 px-6 py-4 rounded-b-xl animate-in fade-in duration-200">
      {/* Drawer Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-lg">
            menu_book
          </span>
          <span className="text-xs font-semibold text-foreground">
            Mục lục Điều luật ({articles.length} Điều)
          </span>
          {overviewPage && (
            <Link
              href={`/wiki/${overviewPage.slug}`}
              className="inline-flex items-center gap-1 ml-2 px-2.5 py-1 text-xs font-medium rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
            >
              <span className="material-symbols-outlined text-sm">open_in_new</span>
              Xem toàn văn Trang Tổng quan & Căn cứ
            </Link>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Quick Filter Inside Drawer */}
          <div className="relative min-w-[200px] max-w-[280px]">
            <span className="material-symbols-outlined text-xs text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2">
              search
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Lọc số Điều (VD: Điều 4, Điều 15)..."
              className="h-7 w-full pl-8 pr-2.5 text-xs rounded-md border border-border bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40 placeholder:text-muted-foreground/60"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs"
              >
                ✕
              </button>
            )}
          </div>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              title="Đóng bảng Điều"
            >
              <span className="material-symbols-outlined text-sm">close</span>
            </button>
          )}
        </div>
      </div>

      {/* Drawer Content */}
      {loading ? (
        <div className="flex items-center justify-center py-6 text-xs text-muted-foreground gap-2">
          <span className="material-symbols-outlined text-base animate-spin">
            progress_activity
          </span>
          Đang tải danh sách Điều...
        </div>
      ) : articles.length === 0 && !overviewPage && otherPages.length === 0 ? (
        <div className="text-xs text-muted-foreground py-4 text-center">
          Văn bản này chưa có trang Wiki Điều luật nào được bóc tách.
        </div>
      ) : (
        <div className="space-y-3">
          {/* Articles Grid */}
          {filteredArticles.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-1.5 max-h-[320px] overflow-y-auto pr-1">
              {filteredArticles.map((art) => {
                // Shorten title if it has " - [Doc Name]" suffix
                const cleanArtTitle = art.title.split(" - ")[0];
                return (
                  <Link
                    key={art.slug}
                    href={`/wiki/${art.slug}`}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border/60 bg-card hover:border-primary/40 hover:bg-accent/40 text-xs text-foreground transition-all group"
                    title={art.title}
                  >
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0 group-hover:scale-125 transition-transform" />
                    <span className="truncate font-medium">{cleanArtTitle}</span>
                  </Link>
                );
              })}
            </div>
          ) : (
            search && (
              <div className="text-xs text-muted-foreground py-2 text-center">
                Không tìm thấy Điều nào khớp với "{search}"
              </div>
            )
          )}

          {/* Other Wiki Pages if any */}
          {otherPages.length > 0 && (
            <div className="pt-2 border-t border-border/60">
              <span className="text-[11px] font-medium text-muted-foreground block mb-1">
                Các trang tri thức liên quan ({otherPages.length}):
              </span>
              <div className="flex flex-wrap gap-1.5">
                {otherPages.map((op) => (
                  <Link
                    key={op.slug}
                    href={`/wiki/${op.slug}`}
                    className="px-2 py-0.5 rounded text-[11px] bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
                  >
                    {op.title}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
