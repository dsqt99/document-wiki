"use client";

import React from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { WikiGraphData, WikiPageDetail } from "@/types/wiki";
import { WikiGraphMini } from "./wiki-graph";
import { getCachedPages } from "@/lib/wiki-store";

type Props = {
  slug: string;
  page: WikiPageDetail;
  /** Suffix appended to /wiki/<slug> links (e.g. "?scopeType=...&scopeId=...")
   *  so backlinks/outlinks preserve the current scope context. */
  linkSuffix?: string;
  onSelectPage?: (slug: string) => void;
};

function LinkItem({
  slug,
  title,
  linkSuffix = "",
  onSelectPage,
}: {
  slug: string;
  title?: string;
  linkSuffix?: string;
  onSelectPage?: (slug: string) => void;
}) {
  const label = title || (slug.split("/").pop() ?? slug).replace(/-/g, " ");
  return (
    <Link
      href={`/wiki/${slug}${linkSuffix}`}
      onClick={(e) => {
        if (onSelectPage && !e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) {
          e.preventDefault();
          onSelectPage(slug);
        }
      }}
      className="block px-2 py-1 rounded-md text-[13px] leading-snug text-foreground/80 hover:bg-accent/50 hover:text-primary transition-colors"
      title={slug}
    >
      <span className="line-clamp-2">{label}</span>
    </Link>
  );
}

function Section({
  title,
  count,
  defaultOpen = true,
  children,
}: {
  title: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  if (count === 0) return null;
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
      >
        {title}
        <span className="tabular-nums text-foreground/70">{count}</span>
        <span className="material-symbols-outlined ml-auto" style={{ fontSize: 16 }}>
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && <div className="space-y-px pb-2">{children}</div>}
    </div>
  );
}

export function WikiSidebarRight({ slug, page, linkSuffix = "", onSelectPage }: Props) {
  const [graphData, setGraphData] = React.useState<WikiGraphData | null>(null);

  React.useEffect(() => {
    api<WikiGraphData>(`/api/wiki/graph?slug=${encodeURIComponent(slug)}&depth=1`)
      .then((d) => setGraphData(d))
      .catch(() => setGraphData(null));
  }, [slug]);

  // Titles from the page list the tree already loaded (falls back to the slug).
  const titles = React.useMemo(() => {
    const m = new Map<string, string>();
    for (const p of getCachedPages("/api/wiki/pages") ?? []) m.set(p.slug, p.title);
    return m;
  }, []);

  const hasLinks = page.backlinks.length > 0 || page.outlinks.length > 0;

  return (
    <div className="w-72 shrink-0 border-l border-border bg-card/30 flex flex-col overflow-hidden h-full">
      <div className="flex-1 overflow-y-auto px-4 pt-3 pb-4 space-y-5">
        <section>
          <p className="text-xs font-bold uppercase tracking-wider text-foreground mb-1.5">Liên kết</p>
          {hasLinks ? (
            <>
              <Section title="Liên kết trỏ đến" count={page.backlinks.length}>
                {page.backlinks.map((s) => (
                  <LinkItem key={s} slug={s} title={titles.get(s)} linkSuffix={linkSuffix} onSelectPage={onSelectPage} />
                ))}
              </Section>
              <Section title="Liên kết đi ra" count={page.outlinks.length}>
                {page.outlinks.map((s) => (
                  <LinkItem key={s} slug={s} title={titles.get(s)} linkSuffix={linkSuffix} onSelectPage={onSelectPage} />
                ))}
              </Section>
            </>
          ) : (
            <p className="text-xs text-muted-foreground py-1">Chưa có liên kết.</p>
          )}
        </section>

        {graphData && graphData.nodes.length > 1 && (
          <section>
            <p className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">Sơ đồ cục bộ</p>
            <div className="rounded-xl overflow-hidden border border-border bg-background">
              <WikiGraphMini slug={slug} nodes={graphData.nodes} edges={graphData.edges} />
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

// Keep backward-compatible export name
export { WikiSidebarRight as WikiBacklinks };
