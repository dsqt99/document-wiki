"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WIKI_STATUS_COLORS, normalizeWikiStatus } from "@/components/wiki/wiki-status-badge";
import { cn } from "@/lib/utils";
import type { GraphInstance } from "./force-graph-canvas";
import type { EdgeInput, GraphLink, GraphNode, NodeInput } from "./types";
import { nodeRadius } from "./utils";

const ForceGraphCanvas = dynamic(() => import("./force-graph-canvas"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">Đang tải sơ đồ…</div>
  ),
});

// ---------------------------------------------------------------------------
// Relation lookup tables (exported for other screens)
// ---------------------------------------------------------------------------

export const RELATION_COLORS: Record<string, string> = {
  la_mot: "#3b82f6", // blue
  thuoc: "#8b5cf6", // violet
  quy_dinh: "#10b981", // emerald
  ap_dung_cho: "#f59e0b", // amber
  lien_quan: "#64748b", // slate
  sua_doi: "#ef4444", // red
  bo_sung: "#f97316", // orange
  thay_the: "#f43f5e", // rose
  bai_bo: "#b91c1c", // dark red
  huong_dan: "#14b8a6", // teal
  can_cu: "#0ea5e9", // sky
  dan_chieu: "#64748b", // slate
  wikilink: "rgba(120, 113, 108, 0.45)", // translucent grey
  concept: "#3b82f6",
  legal: "#ef4444",
};

export const RELATION_LABELS: Record<string, string> = {
  la_mot: "Là một (is-a)",
  thuoc: "Thuộc về (part-of)",
  quy_dinh: "Quy định (regulates)",
  ap_dung_cho: "Áp dụng cho (applies-to)",
  lien_quan: "Liên quan (relates-to)",
  sua_doi: "Sửa đổi (amends)",
  bo_sung: "Bổ sung (supplements)",
  thay_the: "Thay thế (replaces)",
  bai_bo: "Bãi bỏ (repeals)",
  huong_dan: "Hướng dẫn (guides)",
  can_cu: "Căn cứ (basis)",
  dan_chieu: "Dẫn chiếu (cites)",
  wikilink: "Liên kết wiki",
};

const CANVAS_BG = "#faf6ef"; // warm cream
const ACCENT = "#c0603a"; // terracotta
const DARK_RING = "#3b3530";
const LIGHT_RING = "#fdfbf7";

const SCOPE_LEVEL_COLORS: Record<string, string> = {
  global: "#d8c3a5", // beige
  department: "#c0603a", // terracotta
  project: "#e9967a", // salmon
};

const SCOPE_LEVEL_META: Record<string, { icon: string; fallback: string }> = {
  project: { icon: "folder_special", fallback: "Workspace" },
  department: { icon: "business", fallback: "Department" },
  global: { icon: "public", fallback: "Global" },
};

type EdgeFilter = "all" | "concept" | "legal" | "wikilink";
type ColorMode = "scope" | "status";

const EDGE_FILTERS: { key: EdgeFilter; label: string }[] = [
  { key: "all", label: "Tất cả" },
  { key: "concept", label: "Khái niệm" },
  { key: "legal", label: "Pháp lý" },
  { key: "wikilink", label: "Wiki link" },
];

const EDGE_LEGEND: { label: string; color: string }[] = [
  { label: "Là một (is-a)", color: RELATION_COLORS.la_mot },
  { label: "Thuộc về (part-of)", color: RELATION_COLORS.thuoc },
  { label: "Quy định / Áp dụng", color: RELATION_COLORS.quy_dinh },
  { label: "Sửa đổi / Bổ sung", color: RELATION_COLORS.sua_doi },
  { label: "Wiki link", color: RELATION_COLORS.wikilink },
];

function scopeLevel(n: { scope_type?: string }): "global" | "department" | "project" {
  if (n.scope_type === "department" || n.scope_type === "project") return n.scope_type;
  return "global";
}

function endId(end: string | GraphNode): string {
  return typeof end === "string" ? end : end.id;
}

function relationColor(l: GraphLink): string | undefined {
  return (
    (l.predicate && RELATION_COLORS[l.predicate]) ||
    (l.label && RELATION_COLORS[l.label]) ||
    (l.type && RELATION_COLORS[l.type]) ||
    undefined
  );
}

function hexAlpha(color: string, alpha: number): string {
  if (/^#[0-9a-f]{6}$/i.test(color)) {
    const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255)
      .toString(16)
      .padStart(2, "0");
    return color + a;
  }
  return color;
}

/** Spread `count` centres evenly across the inner 70% of `width` (15% margin each side). */
function spreadCentres(count: number, width: number): number[] {
  if (count <= 0) return [];
  const left = -width / 2 + width * 0.15;
  const span = width * 0.7;
  return Array.from({ length: count }, (_, i) => (count === 1 ? 0 : left + ((i + 0.5) * span) / count));
}

type WikiGraphProps = {
  nodes: NodeInput[];
  edges: EdgeInput[];
  centerSlug?: string;
  mini?: boolean;
  height?: number;
  onNodeClick?: (slug: string) => void;
};

export function WikiGraph({ nodes, edges, centerSlug, mini = false, height, onNodeClick }: WikiGraphProps) {
  const router = useRouter();
  const graphRef = useRef<GraphInstance | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const fittedRef = useRef(false);
  // Node objects are kept per slug so the simulation keeps positions as data grows.
  const [nodeCache] = useState(() => new Map<string, GraphNode>());

  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: height ?? 0 });
  const [edgeFilter, setEdgeFilter] = useState<EdgeFilter>("all");
  const [colorMode, setColorMode] = useState<ColorMode>("scope");
  const [hover, setHover] = useState<GraphNode | null>(null);
  const [mouse, setMouse] = useState<{ x: number; y: number } | null>(null);
  const [scopeQuery, setScopeQuery] = useState("");

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setSize({ w: Math.floor(r.width), h: Math.floor(r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const layoutWidth = Math.max(size.w || 800, 400);

  // ---- data assembly -------------------------------------------------------
  const graphData = useMemo(() => {
    const bySlug = new Map<string, NodeInput>();
    for (const n of nodes) if (n?.slug) bySlug.set(n.slug, n);

    const links: GraphLink[] = [];
    for (const e of edges) {
      if (!bySlug.has(e.from) || !bySlug.has(e.to)) continue;
      const type = e.type || "wikilink";
      if (edgeFilter !== "all" && type !== edgeFilter) continue;
      links.push({ ...e, type, source: e.from, target: e.to });
    }

    const degree = new Map<string, number>();
    for (const l of links) {
      degree.set(l.from, (degree.get(l.from) ?? 0) + 1);
      degree.set(l.to, (degree.get(l.to) ?? 0) + 1);
    }

    const graphNodes: GraphNode[] = [];
    for (const n of bySlug.values()) {
      const prev = nodeCache.get(n.slug);
      const node: GraphNode = prev ?? { ...n, id: n.slug, degree: 0 };
      Object.assign(node, n, { id: n.slug, degree: degree.get(n.slug) ?? 0 });
      if (n.slug === centerSlug) {
        node.fx = 0;
        node.fy = 0;
      } else if (prev && prev.fx === 0 && prev.fy === 0) {
        // previously pinned centre: release it
        delete node.fx;
        delete node.fy;
      }
      nodeCache.set(n.slug, node);
      graphNodes.push(node);
    }

    // connected components (union-find)
    const parent = new Map<string, string>();
    const find = (x: string): string => {
      let r = x;
      while (parent.get(r) !== r) r = parent.get(r)!;
      let c = x;
      while (parent.get(c) !== r) {
        const next = parent.get(c)!;
        parent.set(c, r);
        c = next;
      }
      return r;
    };
    for (const n of graphNodes) parent.set(n.id, n.id);
    for (const l of links) {
      const a = find(l.from);
      const b = find(l.to);
      if (a !== b) parent.set(a, b);
    }
    const compMembers = new Map<string, GraphNode[]>();
    for (const n of graphNodes) {
      const root = find(n.id);
      const list = compMembers.get(root) ?? [];
      list.push(n);
      compMembers.set(root, list);
    }
    const comps = [...compMembers.values()].sort((a, b) => b.length - a.length);
    const compX = spreadCentres(comps.length, layoutWidth);
    const nodeCompX = new Map<string, number>();
    comps.forEach((members, i) => members.forEach((m) => nodeCompX.set(m.id, compX[i])));

    // non-global scope clusters, spread on the same axis
    const scopeKeys = [
      ...new Set(graphNodes.filter((n) => scopeLevel(n) !== "global").map((n) => `${n.scope_type}:${n.scope_id ?? ""}`)),
    ].sort();
    const scopeX = new Map<string, number>();
    spreadCentres(scopeKeys.length, layoutWidth).forEach((x, i) => scopeX.set(scopeKeys[i], x));

    for (const n of graphNodes) {
      const cx = nodeCompX.get(n.id) ?? 0;
      if (scopeLevel(n) === "global") n.targetX = cx;
      else n.targetX = 0.7 * (scopeX.get(`${n.scope_type}:${n.scope_id ?? ""}`) ?? cx) + 0.3 * cx;
    }

    return { nodes: graphNodes, links };
  }, [nodes, edges, edgeFilter, centerSlug, layoutWidth, nodeCache]);

  // ---- hover neighbourhood -------------------------------------------------
  const neighbours = useMemo(() => {
    const set = new Set<string>();
    if (!hover) return set;
    set.add(hover.id);
    for (const l of graphData.links) {
      const s = endId(l.source);
      const t = endId(l.target);
      if (s === hover.id) set.add(t);
      if (t === hover.id) set.add(s);
    }
    return set;
  }, [hover, graphData]);

  const nodeColor = useCallback(
    (n: GraphNode) =>
      colorMode === "status"
        ? WIKI_STATUS_COLORS[normalizeWikiStatus(n.status)]
        : SCOPE_LEVEL_COLORS[scopeLevel(n)],
    [colorMode],
  );

  const drawNode = useCallback(
    (n: GraphNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const x = n.x ?? 0;
      const y = n.y ?? 0;
      const isHover = hover?.id === n.id;
      const isCenter = n.id === centerSlug;
      const dimmed = !!hover && !neighbours.has(n.id);
      const r = nodeRadius(n.degree, mini) * (isHover ? 1.3 : 1);
      const color = nodeColor(n);

      ctx.save();
      ctx.globalAlpha = dimmed ? 0.15 : 1;

      if (isHover) {
        ctx.beginPath();
        ctx.arc(x, y, r * 1.8, 0, 2 * Math.PI);
        ctx.fillStyle = hexAlpha(color, 0.12);
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(x, y, r + 1.5, 0, 2 * Math.PI);
      ctx.fillStyle = CANVAS_BG;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
      if (isCenter) {
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = DARK_RING;
      } else if (isHover) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = color;
      } else {
        ctx.lineWidth = 1;
        ctx.strokeStyle = LIGHT_RING;
      }
      ctx.stroke();

      const showLabel = !mini && !dimmed && (isHover || isCenter || scale >= 1.2 || n.degree >= 4);
      if (showLabel) {
        const title = n.title.length > 24 ? `${n.title.slice(0, 22)}…` : n.title;
        const fontPx = (isHover ? 12 : 11) / scale;
        ctx.font = `${isHover ? 600 : 400} ${fontPx}px Inter, system-ui, sans-serif`;
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.globalAlpha = isHover || isCenter ? 1 : 0.7;
        ctx.fillStyle = DARK_RING;
        ctx.fillText(title, x + r + 3 / scale, y);
      }
      ctx.restore();
    },
    [hover, neighbours, centerSlug, mini, nodeColor],
  );

  const paintPointer = useCallback(
    (n: GraphNode, paintColor: string, ctx: CanvasRenderingContext2D) => {
      ctx.beginPath();
      ctx.arc(n.x ?? 0, n.y ?? 0, nodeRadius(n.degree, mini) + 4, 0, 2 * Math.PI);
      ctx.fillStyle = paintColor;
      ctx.fill();
    },
    [mini],
  );

  const linkColor = useCallback(
    (l: GraphLink) => {
      const rel = relationColor(l);
      if (!hover) return rel ?? RELATION_COLORS.wikilink;
      const touches = endId(l.source) === hover.id || endId(l.target) === hover.id;
      return touches ? (rel ?? ACCENT) : "rgba(120, 113, 108, 0.06)";
    },
    [hover],
  );

  const linkWidth = useCallback(
    (l: GraphLink) => {
      const base = Math.min(3, Math.max(1, (l.weight ?? 1) * 1.2));
      if (!hover) return base;
      const touches = endId(l.source) === hover.id || endId(l.target) === hover.id;
      return touches ? base * 1.8 : 0.8;
    },
    [hover],
  );

  const handleEngineStop = () => {
    if (fittedRef.current) return;
    const fg = graphRef.current;
    if (!fg) return;
    fittedRef.current = true;
    if (mini) {
      fg.centerAt(0, 0);
      fg.zoom(1.4);
      return;
    }
    if (graphData.nodes.length <= 1) {
      const n = graphData.nodes[0];
      fg.centerAt(n?.x ?? 0, n?.y ?? 0, 400);
      fg.zoom(2, 400);
    } else {
      fg.zoomToFit(400, 60);
    }
  };

  const handleClick = (n: GraphNode) => {
    if (onNodeClick) onNodeClick(n.id);
    else router.push(`/wiki/${n.id}`);
  };

  // ---- legend data ---------------------------------------------------------
  const statusCounts = useMemo(() => {
    const c: Record<string, number> = { evergreen: 0, mature: 0, developing: 0, seed: 0 };
    for (const n of graphData.nodes) c[normalizeWikiStatus(n.status)]++;
    return c;
  }, [graphData]);

  const levelCounts = useMemo(() => {
    const c: Record<string, number> = { global: 0, department: 0, project: 0 };
    for (const n of graphData.nodes) c[scopeLevel(n)]++;
    return c;
  }, [graphData]);

  const scopeList = useMemo(() => {
    const m = new Map<string, { key: string; level: string; name: string; count: number }>();
    for (const n of graphData.nodes) {
      const level = scopeLevel(n);
      const key = `${level}:${n.scope_id ?? ""}`;
      const cur = m.get(key) ?? {
        key,
        level,
        name: n.scope_name || SCOPE_LEVEL_META[level].fallback,
        count: 0,
      };
      cur.count++;
      m.set(key, cur);
    }
    return [...m.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [graphData]);

  const filteredScopes = useMemo(() => {
    const q = scopeQuery.trim().toLowerCase();
    return q ? scopeList.filter((s) => s.name.toLowerCase().includes(q)) : scopeList;
  }, [scopeList, scopeQuery]);

  const zoomBy = (factor: number) => {
    const fg = graphRef.current;
    if (!fg) return;
    fg.zoom(fg.zoom() * factor, 200);
  };

  const hoverMeta = hover ? SCOPE_LEVEL_META[scopeLevel(hover)] : null;

  return (
    <div
      ref={containerRef}
      className={cn("relative w-full overflow-hidden", !height && "h-full", mini ? "rounded-lg" : "rounded-xl")}
      style={{ height: height ?? undefined, backgroundColor: CANVAS_BG }}
      onMouseMove={(e) => {
        if (mini || !hover) return;
        const rect = e.currentTarget.getBoundingClientRect();
        setMouse({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      }}
    >
      {size.w > 0 && (
        <ForceGraphCanvas
          graphRef={graphRef}
          mini={mini}
          graphData={graphData}
          nodeId="id"
          width={size.w}
          height={height ?? size.h}
          backgroundColor={CANVAS_BG}
          nodeCanvasObject={drawNode}
          nodePointerAreaPaint={paintPointer}
          linkColor={linkColor}
          linkWidth={linkWidth}
          linkDirectionalArrowLength={mini ? 0 : 3.5}
          linkDirectionalArrowRelPos={0.88}
          minZoom={0.2}
          maxZoom={5}
          d3AlphaDecay={0.06}
          d3VelocityDecay={0.55}
          cooldownTicks={mini ? 50 : 90}
          onEngineStop={handleEngineStop}
          onNodeHover={(n) => {
            setHover(n ?? null);
            if (!n) setMouse(null);
          }}
          onNodeClick={handleClick}
          enableNodeDrag={!mini}
          enableZoomInteraction={!mini}
          enablePanInteraction={!mini}
        />
      )}

      {/* hover tooltip */}
      {!mini && hover && mouse && (
        <div
          className="pointer-events-none absolute z-20 max-w-[220px] rounded-lg border bg-background/95 px-3 py-2 text-xs shadow-md"
          style={{ left: mouse.x + 14, top: mouse.y + 14 }}
        >
          <div className="mb-1 font-semibold text-foreground">{hover.title}</div>
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <span className="size-2 rounded-full" style={{ backgroundColor: nodeColor(hover) }} />
            <span>{hover.page_type}</span>
            <span>·</span>
            <span>{hover.degree} links</span>
          </div>
          {hoverMeta && (
            <div className="mt-1 flex items-center gap-1 text-muted-foreground">
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                {hoverMeta.icon}
              </span>
              <span className="truncate">{hover.scope_name || hoverMeta.fallback}</span>
            </div>
          )}
        </div>
      )}

      {!mini && (
        <>
          {/* top-right controls */}
          <div className="absolute top-3 right-3 z-10 flex flex-col items-end gap-2">
            <div className="flex items-center gap-1 rounded-lg border bg-background/90 p-1 text-xs shadow-sm">
              <span className="px-1.5 text-muted-foreground">Quan hệ:</span>
              {EDGE_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setEdgeFilter(f.key)}
                  className={cn(
                    "rounded-md px-2 py-1 font-medium transition-colors",
                    edgeFilter === f.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1 rounded-lg border bg-background/90 p-1 text-xs shadow-sm">
              {(
                [
                  ["scope", "Scope"],
                  ["status", "Maturity"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setColorMode(key)}
                  className={cn(
                    "rounded-md px-2 py-1 font-medium transition-colors",
                    colorMode === key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* bottom-left legend */}
          <div className="absolute bottom-3 left-3 z-10 max-h-[50vh] w-[240px] max-w-[240px] overflow-y-auto rounded-lg border bg-background/90 p-3 text-xs shadow-sm">
            {colorMode === "status" ? (
              <LegendSection title="Maturity Lifecycle">
                {(["evergreen", "mature", "developing", "seed"] as const).map((s) => (
                  <LegendRow
                    key={s}
                    swatch={<span className="size-2.5 rounded-full" style={{ backgroundColor: WIKI_STATUS_COLORS[s] }} />}
                    label={s[0].toUpperCase() + s.slice(1)}
                    count={statusCounts[s]}
                  />
                ))}
              </LegendSection>
            ) : (
              <>
                <LegendSection title="Scope Levels">
                  {(["global", "department", "project"] as const).map((lv) => (
                    <LegendRow
                      key={lv}
                      swatch={
                        <span
                          className="material-symbols-outlined"
                          style={{ fontSize: 14, color: SCOPE_LEVEL_COLORS[lv] }}
                        >
                          {SCOPE_LEVEL_META[lv].icon}
                        </span>
                      }
                      label={SCOPE_LEVEL_META[lv].fallback}
                      count={levelCounts[lv]}
                    />
                  ))}
                </LegendSection>
                <LegendSection title="Scope">
                  {scopeList.length > 8 && (
                    <div className="relative mb-1.5">
                      <input
                        value={scopeQuery}
                        onChange={(e) => setScopeQuery(e.target.value)}
                        placeholder="Filter scopes…"
                        className="h-7 w-full rounded-md border bg-background px-2 pr-6 text-xs outline-none focus:border-primary"
                      />
                      {scopeQuery && (
                        <button
                          type="button"
                          aria-label="Clear"
                          onClick={() => setScopeQuery("")}
                          className="absolute top-1/2 right-1 flex -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                            close
                          </span>
                        </button>
                      )}
                    </div>
                  )}
                  <div className={cn(scopeList.length > 8 && "max-h-40 overflow-y-auto")}>
                    {filteredScopes.length === 0 ? (
                      <div className="py-1 text-muted-foreground">No matching scopes.</div>
                    ) : (
                      filteredScopes.map((s) => (
                        <LegendRow
                          key={s.key}
                          swatch={
                            <span
                              className="material-symbols-outlined"
                              style={{ fontSize: 14, color: SCOPE_LEVEL_COLORS[s.level] }}
                            >
                              {SCOPE_LEVEL_META[s.level].icon}
                            </span>
                          }
                          label={s.name}
                          count={s.count}
                        />
                      ))
                    )}
                  </div>
                </LegendSection>
              </>
            )}
            <LegendSection title="Loại quan hệ (Edges)" last>
              {EDGE_LEGEND.map((e) => (
                <LegendRow
                  key={e.label}
                  swatch={<span className="h-0.5 w-4 rounded" style={{ backgroundColor: e.color }} />}
                  label={e.label}
                />
              ))}
            </LegendSection>
          </div>

          {/* bottom-right zoom */}
          <div className="absolute right-3 bottom-3 z-10 flex flex-col overflow-hidden rounded-lg border bg-background/90 shadow-sm">
            <ZoomButton icon="add" label="Zoom In" onClick={() => zoomBy(1.2)} />
            <ZoomButton icon="remove" label="Zoom Out" onClick={() => zoomBy(1 / 1.2)} />
            <ZoomButton icon="fit_screen" label="Fit View" onClick={() => graphRef.current?.zoomToFit(400, 60)} />
          </div>
        </>
      )}
    </div>
  );
}

function LegendSection({ title, children, last }: { title: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className={cn(!last && "mb-3")}>
      <div className="mb-1.5 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function LegendRow({ swatch, label, count }: { swatch: React.ReactNode; label: string; count?: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex w-4 shrink-0 items-center justify-center">{swatch}</span>
      <span className="min-w-0 flex-1 truncate text-foreground">{label}</span>
      {count !== undefined && <span className="tabular-nums text-muted-foreground">{count}</span>}
    </div>
  );
}

function ZoomButton({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={label}
            onClick={onClick}
            className="flex size-8 items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground"
          />
        }
      >
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          {icon}
        </span>
      </TooltipTrigger>
      <TooltipContent side="left">{label}</TooltipContent>
    </Tooltip>
  );
}
