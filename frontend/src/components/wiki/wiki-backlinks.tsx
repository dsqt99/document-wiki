"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { WikiGraphMini } from "@/components/wiki/wiki-graph/wiki-graph-mini";
import { encodeSlugPath, loadWikiPages, slugToTitle, WIKI_PAGES_URL } from "@/components/wiki/wiki-pages-loader";
import { api } from "@/lib/api";
import { getCachedPages } from "@/lib/wiki-store";
import { cn } from "@/lib/utils";
import type { WikiGraphData, WikiPageDetail, WikiPageSummary } from "@/types/wiki";

type Props = {
  slug: string;
  page: WikiPageDetail;
  linkSuffix?: string;
  onSelectPage?: (slug: string) => void;
};

const EMPTY_GRAPH: WikiGraphData = { nodes: [], edges: [] };

function LinkSection({
  label,
  slugs,
  titleOf,
  linkSuffix,
  onSelectPage,
}: {
  label: string;
  slugs: string[];
  titleOf: (slug: string) => string;
  linkSuffix: string;
  onSelectPage?: (slug: string) => void;
}) {
  const [open, setOpen] = useState(true);
  if (slugs.length === 0) return null;
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1 py-1 text-left text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <span
          className={cn("material-symbols-outlined transition-transform", open && "rotate-90")}
          style={{ fontSize: 16 }}
        >
          chevron_right
        </span>
        <span className="flex-1">{label}</span>
        <span className="tabular-nums">{slugs.length}</span>
      </button>
      {open && (
        <ul className="mt-0.5 space-y-0.5 pl-5">
          {slugs.map((s) => {
            const href = `/wiki/${encodeSlugPath(s)}${linkSuffix}`;
            return (
              <li key={s}>
                <Link
                  href={href}
                  title={s}
                  onClick={(e) => {
                    if (!onSelectPage || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                    e.preventDefault();
                    onSelectPage(s);
                  }}
                  className="block truncate rounded px-1.5 py-1 text-sm hover:bg-muted hover:text-primary"
                >
                  {titleOf(s)}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function WikiSidebarRight({ slug, page, linkSuffix = "", onSelectPage }: Props) {
  const [graphState, setGraphState] = useState<{ slug: string; data: WikiGraphData }>({ slug: "", data: EMPTY_GRAPH });
  const [pages, setPages] = useState<WikiPageSummary[]>(() => getCachedPages(WIKI_PAGES_URL) ?? []);

  useEffect(() => {
    let cancelled = false;
    api<WikiGraphData>(`/api/wiki/graph?slug=${encodeURIComponent(slug)}&depth=1`)
      .then((d) => {
        if (cancelled) return;
        setGraphState({
          slug,
          data: { nodes: Array.isArray(d?.nodes) ? d.nodes : [], edges: Array.isArray(d?.edges) ? d.edges : [] },
        });
      })
      .catch(() => {
        if (!cancelled) setGraphState({ slug, data: EMPTY_GRAPH });
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    loadWikiPages()
      .then((list) => {
        if (!cancelled) setPages(list);
      })
      .catch(() => {
        /* titles fall back to the slug */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const titles = new Map(pages.map((p) => [p.slug, p.title]));
  const titleOf = (s: string) => titles.get(s) || slugToTitle(s);

  const backlinks = page.backlinks ?? [];
  const outlinks = page.outlinks ?? [];
  const graph = graphState.slug === slug ? graphState.data : EMPTY_GRAPH;

  return (
    <div className="flex h-full w-72 flex-col overflow-y-auto border-l px-4 py-4">
      <section>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Liên kết</h3>
        {backlinks.length === 0 && outlinks.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có liên kết.</p>
        ) : (
          <div className="space-y-2">
            <LinkSection
              label="Liên kết trỏ đến"
              slugs={backlinks}
              titleOf={titleOf}
              linkSuffix={linkSuffix}
              onSelectPage={onSelectPage}
            />
            <LinkSection
              label="Liên kết đi ra"
              slugs={outlinks}
              titleOf={titleOf}
              linkSuffix={linkSuffix}
              onSelectPage={onSelectPage}
            />
          </div>
        )}
      </section>

      {graph.nodes.length > 1 && (
        <section className="mt-5 border-t pt-4">
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Sơ đồ cục bộ</h3>
          <div className="overflow-hidden rounded-lg border">
            <WikiGraphMini slug={slug} nodes={graph.nodes} edges={graph.edges} />
          </div>
        </section>
      )}
    </div>
  );
}

/** Alias kept for screens that import the older name. */
export const WikiBacklinks = WikiSidebarRight;
