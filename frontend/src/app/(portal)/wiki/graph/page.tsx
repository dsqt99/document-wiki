"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiGraph } from "@/components/wiki/wiki-graph";
import { encodeSlugPath } from "@/components/wiki/wiki-pages-loader";
import { wikiTypeColor, wikiTypeGroupLabel, wikiTypeIcon } from "@/components/wiki/wiki-type-badge";
import { api } from "@/lib/api";
import { useIsEmbedded } from "@/lib/embed";
import { cn } from "@/lib/utils";
import type { WikiGraphData, WikiGraphEdge, WikiGraphNode, WikiPageDetail } from "@/types/wiki";

const BATCH = 10;
const FILTER_TYPES = ["entity", "concept", "topic", "source"] as const;
const MAX_MATCHES = 8;

export default function WikiGraphPage() {
  return (
    <Suspense fallback={null}>
      <GraphScreen />
    </Suspense>
  );
}

type GraphState = {
  base: string;
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
  total: number;
  firstLoaded: boolean;
  done: boolean;
};

type Preview = { slug: string; status: "loading" | "ok" | "error"; page?: WikiPageDetail };

function GraphScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const embedded = useIsEmbedded();
  const projectId = searchParams.get("projectId");

  const baseUrl = projectId ? `/api/projects/${encodeURIComponent(projectId)}/wiki/graph` : "/api/wiki/graph";
  const heading = projectId ? "Workspace Graph" : "Knowledge Graph";
  const backHref = projectId ? "/workspaces" : "/wiki/law";
  const pageScopeQs = projectId ? `?scope_type=project&scope_id=${encodeURIComponent(projectId)}` : "";

  // ------------------------------------------------------------ progressive loading
  const [graph, setGraph] = useState<GraphState>({
    base: "",
    nodes: [],
    edges: [],
    total: 0,
    firstLoaded: false,
    done: false,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let offset = 0;
      const seen = new Set<string>();
      let nodes: WikiGraphNode[] = [];
      let edges: WikiGraphEdge[] = [];
      let total = 0;
      for (;;) {
        let batch: WikiGraphData;
        try {
          batch = await api<WikiGraphData>(`${baseUrl}?offset=${offset}&limit=${BATCH}`);
        } catch {
          break;
        }
        if (cancelled) return;
        const incoming = Array.isArray(batch?.nodes) ? batch.nodes : [];
        const fresh = incoming.filter((n) => n && !seen.has(n.slug));
        fresh.forEach((n) => seen.add(n.slug));
        nodes = [...nodes, ...fresh];
        edges = [...edges, ...(Array.isArray(batch?.edges) ? batch.edges : [])];
        total = typeof batch?.total === "number" ? batch.total : Math.max(total, nodes.length);
        offset += incoming.length;
        const more = !!batch?.has_more && incoming.length > 0;
        setGraph({ base: baseUrl, nodes, edges, total, firstLoaded: true, done: !more });
        if (!more) return;
      }
      if (!cancelled) setGraph({ base: baseUrl, nodes, edges, total, firstLoaded: true, done: true });
    })();
    return () => {
      cancelled = true;
    };
  }, [baseUrl]);

  const current = graph.base === baseUrl ? graph : null;
  const allNodes = useMemo(() => current?.nodes ?? [], [current]);
  const allEdges = useMemo(() => current?.edges ?? [], [current]);
  const loadedFirst = !!current?.firstLoaded;
  const finished = !!current?.done;
  const total = current?.total ?? 0;

  // ------------------------------------------------------------ type filter
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(FILTER_TYPES));
  const toggleType = (t: string) =>
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  const visible = useMemo(() => {
    const nodes = allNodes.filter((n) => enabled.has(n.page_type));
    const keep = new Set(nodes.map((n) => n.slug));
    const edges = allEdges.filter((e) => keep.has(e.from) && keep.has(e.to));
    return { nodes, edges };
  }, [allNodes, allEdges, enabled]);

  // ------------------------------------------------------------ find node
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState<string | undefined>(undefined);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return allNodes
      .filter((n) => n.title?.toLowerCase().includes(q) || n.slug.toLowerCase().includes(q))
      .slice(0, MAX_MATCHES);
  }, [query, allNodes]);
  const pick = (slug: string) => {
    setHighlight(slug);
    setQuery("");
  };

  // ------------------------------------------------------------ quick view
  const [preview, setPreview] = useState<Preview | null>(null);
  const openPreview = (slug: string) => {
    setPreview({ slug, status: "loading" });
    api<WikiPageDetail>(`/api/wiki/pages/${encodeSlugPath(slug)}${pageScopeQs}`)
      .then((page) => setPreview((p) => (p && p.slug === slug ? { slug, status: "ok", page } : p)))
      .catch(() => setPreview((p) => (p && p.slug === slug ? { slug, status: "error" } : p)));
  };
  const fullHref = (slug: string) => `/wiki/${encodeSlugPath(slug)}${pageScopeQs}`;

  const fill = embedded ? "-m-4 md:-m-5" : "-mx-6 -mt-4 -mb-6 md:-mx-8 md:-mb-8 lg:-mx-10 lg:-mb-10";
  const progress = total > 0 ? Math.min(100, (allNodes.length / total) * 100) : 0;

  return (
    <div className={cn("flex h-screen min-h-0 flex-col", fill)}>
      <header className="flex flex-wrap items-center gap-3 border-b px-4 py-2.5">
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label="Back to Wiki"
                onClick={() => router.push(backHref)}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              />
            }
          >
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
              arrow_back
            </span>
          </TooltipTrigger>
          <TooltipContent>Back to Wiki</TooltipContent>
        </Tooltip>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: 22 }}>
            hub
          </span>
          <h1 className="text-base font-semibold">{heading}</h1>
        </div>
        <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{visible.nodes.length} pages</span>
        <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">{visible.edges.length} links</span>

        <div className="relative w-56">
          <span
            className="material-symbols-outlined pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted-foreground"
            style={{ fontSize: 17 }}
          >
            search
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && matches[0]) {
                e.preventDefault();
                pick(matches[0].slug);
              } else if (e.key === "Escape") {
                setQuery("");
              }
            }}
            placeholder="Find node..."
            className="h-8 w-full rounded-md border bg-background pr-7 pl-8 text-sm outline-none focus:border-primary"
          />
          {query && (
            <button
              type="button"
              aria-label="Clear"
              onClick={() => setQuery("")}
              className="absolute top-1/2 right-1.5 flex -translate-y-1/2 items-center text-muted-foreground hover:text-foreground"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                close
              </span>
            </button>
          )}
          {matches.length > 0 && (
            <div className="absolute top-full right-0 left-0 z-30 mt-1 max-h-80 overflow-y-auto rounded-md border bg-popover p-1 shadow-lg">
              {matches.map((n) => (
                <button
                  key={n.slug}
                  type="button"
                  onClick={() => pick(n.slug)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
                >
                  <span
                    className="material-symbols-outlined shrink-0"
                    style={{ fontSize: 16, color: wikiTypeColor(n.page_type) }}
                  >
                    {wikiTypeIcon(n.page_type)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{n.title || n.slug}</span>
                    <span className="block truncate font-mono text-[11px] text-muted-foreground">{n.slug}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {FILTER_TYPES.map((t) => {
            const on = enabled.has(t);
            const color = wikiTypeColor(t);
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                onClick={() => toggleType(t)}
                className={cn(
                  "flex items-center gap-1.5 rounded-[10px] border px-2 py-1 text-xs transition-opacity",
                  !on && "opacity-45",
                )}
                style={on ? { borderColor: color, backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)` } : undefined}
              >
                <span className="size-2 rounded-full" style={{ backgroundColor: color }} />
                <span className="material-symbols-outlined" style={{ fontSize: 14, color }}>
                  {wikiTypeIcon(t)}
                </span>
                {wikiTypeGroupLabel(t)}
              </button>
            );
          })}
        </div>
      </header>

      <div className="relative min-h-0 flex-1">
        {!loadedFirst ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
            <span className="material-symbols-outlined animate-spin" style={{ fontSize: 32 }}>
              progress_activity
            </span>
            <span className="text-sm">Building graph...</span>
          </div>
        ) : allNodes.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <span className="material-symbols-outlined text-muted-foreground/60" style={{ fontSize: 64 }}>
              hub
            </span>
            <h2 className="text-lg font-semibold">No wiki pages yet</h2>
            <p className="text-sm text-muted-foreground">
              Upload and compile documents to start building the knowledge graph.
            </p>
          </div>
        ) : (
          <>
            {!finished && (
              <>
                <div className="absolute inset-x-0 top-0 z-10 h-0.5 bg-muted">
                  <div className="h-full bg-primary transition-[width]" style={{ width: `${progress}%` }} />
                </div>
                <div className="absolute top-3 left-1/2 z-10 -translate-x-1/2 rounded-full border bg-background/90 px-3 py-1 text-xs text-muted-foreground shadow-sm">
                  Loading {allNodes.length} / {total} nodes...
                </div>
              </>
            )}
            <WikiGraph nodes={visible.nodes} edges={visible.edges} centerSlug={highlight} onNodeClick={openPreview} />
          </>
        )}
      </div>

      <Sheet open={!!preview} onOpenChange={(open) => !open && setPreview(null)}>
        <SheetContent
          side="right"
          showCloseButton={false}
          className="w-[400px] gap-0 p-0 data-[side=right]:sm:max-w-[540px] sm:w-[540px]"
        >
          {preview && (
            <>
              <div className="flex items-center gap-2 border-b px-4 py-3">
                <SheetTitle className="min-w-0 flex-1 truncate text-base font-semibold">
                  {preview.status === "loading" ? "Loading..." : preview.page?.title || preview.slug}
                </SheetTitle>
                <Button size="sm" variant="outline" onClick={() => router.push(fullHref(preview.slug))}>
                  View Full
                </Button>
                <button
                  type="button"
                  aria-label="Close"
                  onClick={() => setPreview(null)}
                  className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                    close
                  </span>
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
                {preview.status === "loading" ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <span className="material-symbols-outlined animate-spin" style={{ fontSize: 18 }}>
                      progress_activity
                    </span>
                    Loading page...
                  </div>
                ) : preview.status === "ok" && preview.page ? (
                  <WikiContent markdown={preview.page.content_md} />
                ) : (
                  <p className="text-sm text-muted-foreground">Failed to load content.</p>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
