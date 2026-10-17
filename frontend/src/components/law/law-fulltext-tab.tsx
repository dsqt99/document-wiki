"use client";

import { useState } from "react";
import Link from "next/link";
import type { LegalDocDetail } from "@/types/legal-doc";
import { FormattedInlineText } from "@/components/wiki/formatted-inline-text";
import { WikiContent } from "@/components/wiki/wiki-content";
import { slugPath } from "@/components/review/review-utils";

/** "Toàn văn": preamble and articles grouped under chapter headings, with a searchable index. */
export function LawFulltextTab({ doc }: { doc: LegalDocDetail }) {
  const [query, setQuery] = useState("");
  const articles = doc.articles ?? [];
  const preamble = (doc.preamble ?? "").trim();
  const needle = query.trim().toLowerCase();
  const matches = articles
    .map((a, i) => ({ a, i }))
    .filter(({ a }) => !needle || (a.heading ?? "").toLowerCase().includes(needle));

  const jumpTo = (i: number) => {
    document.getElementById(`art-${i}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_17rem] 2xl:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 rounded-xl border bg-card p-6 md:p-8">
        {preamble && (
          <div className="mb-6 border-b pb-6 text-[15px]">
            <WikiContent markdown={doc.preamble} />
          </div>
        )}
        {articles.length === 0 && !preamble && (
          <p className="text-sm text-muted-foreground">Văn bản chưa có nội dung trích xuất.</p>
        )}
        {articles.map((a, i) => {
          const prev = i > 0 ? articles[i - 1] : null;
          const showChapter = !!a.chapter_title && (!prev || prev.chapter_num !== a.chapter_num);
          const last = i === articles.length - 1;
          return (
            <section key={i} id={`art-${i}`} className="scroll-mt-24">
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
                  {a.wiki_slug && (
                    <Link
                      href={`/wiki/${slugPath(a.wiki_slug)}`}
                      title="Mở trang wiki của điều này"
                      className="shrink-0 text-muted-foreground/60 hover:text-primary"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                        open_in_new
                      </span>
                    </Link>
                  )}
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
      </div>

      {articles.length > 0 && (
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
              placeholder="Tìm điều khoản..."
              className="h-8 w-full rounded-lg border border-input bg-transparent pr-2 pl-8 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>
          <div className="max-h-[60vh] min-h-0 overflow-y-auto lg:max-h-none lg:flex-1">
            {matches.length === 0 ? (
              <p className="px-2 py-3 text-xs text-muted-foreground">Không có kết quả</p>
            ) : (
              <ul className="flex flex-col">
                {matches.map(({ a, i }) => (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => jumpTo(i)}
                      title={a.heading}
                      className="line-clamp-2 w-full rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted hover:text-primary"
                    >
                      <FormattedInlineText text={a.heading} />
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
