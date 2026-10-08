"use client";

import React from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";
import { WikiContent } from "@/components/wiki/wiki-content";
import { WikiGraph } from "@/components/wiki/wiki-graph";
import { WikiGraphData } from "@/types/wiki";
import { LegalArticle, LegalDocDetail, LegalDocRelation } from "@/types/legal-doc";
import {
  RELATION_INCOMING_LABEL_VI,
  RELATION_LABEL_VI,
  VALIDITY_INFO,
  formatViDate,
  validityOf,
} from "@/lib/legal-doc";

const TABS = [
  { id: "fulltext", label: "Toàn văn", icon: "article" },
  { id: "overview", label: "Tổng quan", icon: "info" },
  { id: "schema", label: "Lược đồ", icon: "account_tree" },
  { id: "graph", label: "Đồ thị", icon: "hub" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function isTab(v: string | null): v is TabId {
  return TABS.some((t) => t.id === v);
}

const articleAnchor = (idx: number) => `art-${idx}`;

export default function LegalDocDetailPage() {
  const params = useParams();
  const key = decodeURIComponent(String(params.key ?? ""));
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawTab = searchParams.get("tab");
  const tab: TabId = isTab(rawTab) ? rawTab : "fulltext";

  // Response tagged with the key it answers; loading is derived.
  const [result, setResult] = React.useState<{ key: string; doc: LegalDocDetail | null; error: string } | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    api<LegalDocDetail>(`/api/wiki/legal-docs/${encodeURIComponent(key)}`)
      .then((doc) => !cancelled && setResult({ key, doc, error: "" }))
      .catch((e) => {
        if (!cancelled) setResult({ key, doc: null, error: e instanceof Error ? e.message : "Không tải được văn bản" });
      });
    return () => {
      cancelled = true;
    };
  }, [key]);
  const fresh = result?.key === key ? result : null;
  const doc = fresh?.doc ?? null;

  const setTab = (id: TabId) => {
    const p = new URLSearchParams(searchParams.toString());
    p.set("tab", id);
    router.replace(`/wiki/law/${encodeURIComponent(key)}?${p.toString()}`, { scroll: false });
  };

  if (!fresh) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">progress_activity</span>
      </div>
    );
  }
  if (!doc) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <EmptyState icon="error" title="Không mở được văn bản" description={fresh.error} />
      </div>
    );
  }

  const v = VALIDITY_INFO[validityOf(doc)];
  const m = doc.meta;

  return (
    <div className="flex flex-col gap-4">
      <BackLink />

      {/* Title + badges */}
      <div>
        <h1 className="text-xl md:text-2xl font-bold tracking-tight leading-snug">{doc.title}</h1>
        <div className="mt-2 flex items-center gap-2 flex-wrap text-xs">
          {m.doc_type && (
            <span className="px-2 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary font-semibold">
              {m.doc_type}
            </span>
          )}
          <span className={cn("px-2 py-0.5 rounded-full border font-semibold", v.badge)}>{v.label}</span>
          {m.doc_number && (
            <span className="px-2 py-0.5 rounded-full border border-border bg-muted/50 font-medium">{m.doc_number}</span>
          )}
          {doc.knowledge_type && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-border bg-background font-medium">
              <span className="size-2 rounded-full" style={{ backgroundColor: doc.knowledge_type.color }} />
              {doc.knowledge_type.name}
            </span>
          )}
          {m.field && (
            <span className="px-2 py-0.5 rounded-full border border-border bg-background text-muted-foreground">
              {m.field}
            </span>
          )}
          {doc.download_url && (
            <a
              href={doc.download_url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border bg-background font-medium hover:bg-muted"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>download</span>
              Tải về
            </a>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto overflow-y-hidden">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 -mb-px text-sm font-medium border-b-2 whitespace-nowrap transition-colors cursor-pointer",
              tab === t.id ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 17 }}>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "fulltext" && <FullTextTab doc={doc} />}
      {tab === "overview" && <OverviewTab doc={doc} />}
      {tab === "schema" && <SchemaTab doc={doc} />}
      {tab === "graph" && <GraphTab doc={doc} />}
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/wiki/law"
      className="self-start flex items-center gap-1 text-sm text-muted-foreground hover:text-primary transition-colors"
    >
      <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_back</span>
      Danh sách văn bản
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* Toàn văn                                                            */
/* ------------------------------------------------------------------ */

function FullTextTab({ doc }: { doc: LegalDocDetail }) {
  const [q, setQ] = React.useState("");
  const toc = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    return doc.articles
      .map((a, idx) => ({ a, idx }))
      .filter(({ a }) => !needle || a.heading.toLowerCase().includes(needle));
  }, [doc.articles, q]);

  const jump = (idx: number) =>
    document.getElementById(articleAnchor(idx))?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_17rem] xl:grid-cols-[minmax(0,1fr)_20rem] gap-6 items-start">
      <div className="min-w-0 bg-card border border-border rounded-xl px-6 py-5">
        {doc.preamble && (
          <div className="pb-4 mb-4 border-b border-border text-[15px]">
            <WikiContent markdown={doc.preamble} />
          </div>
        )}
        {doc.articles.length === 0 && !doc.preamble && (
          <p className="text-sm text-muted-foreground">Văn bản chưa có nội dung trích xuất.</p>
        )}
        {doc.articles.map((a, idx) => (
          <ArticleBlock
            key={idx}
            article={a}
            idx={idx}
            showChapter={!!a.chapter_title && a.chapter_num !== doc.articles[idx - 1]?.chapter_num}
          />
        ))}
      </div>

      {doc.articles.length > 0 && (
        <aside className="bg-card border border-border rounded-xl px-3 pt-3 pb-2 lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] flex flex-col">
          <p className="px-1 pb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Danh sách điều khoản ({doc.articles.length})
          </p>
          <div className="relative mb-2">
            <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-2 top-1/2 -translate-y-1/2">
              search
            </span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Tìm điều khoản..."
              className="h-8 w-full pl-7 pr-2 text-xs rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 placeholder:text-muted-foreground/60"
            />
          </div>
          <div className="flex-1 overflow-y-auto max-h-[60vh] lg:max-h-none flex flex-col gap-px pr-1">
            {toc.map(({ a, idx }) => (
              <button
                key={idx}
                onClick={() => jump(idx)}
                className="text-left px-2 py-1.5 rounded-md text-[13px] leading-snug text-foreground/80 hover:bg-muted hover:text-primary cursor-pointer"
                title={a.heading}
              >
                <span className="line-clamp-2">{a.heading}</span>
              </button>
            ))}
            {toc.length === 0 && <p className="text-xs text-muted-foreground px-2 py-1">Không có kết quả</p>}
          </div>
        </aside>
      )}
    </div>
  );
}

function ArticleBlock({ article: a, idx, showChapter }: { article: LegalArticle; idx: number; showChapter: boolean }) {
  return (
    <section id={articleAnchor(idx)} className="scroll-mt-4">
      {showChapter && (
        <h2 className="mt-6 mb-3 text-center text-sm font-bold uppercase tracking-wide text-foreground">
          {a.chapter_num ? `Chương ${a.chapter_num}` : ""}
          <span className="block font-semibold normal-case text-[15px] mt-0.5">{a.chapter_title}</span>
        </h2>
      )}
      <div className="group py-3 border-b border-border/60 last:border-b-0">
        <div className="flex items-start gap-2">
          <h3 className="flex-1 font-bold text-[15px] text-foreground">{a.heading}</h3>
          {a.wiki_slug && (
            <Link
              href={`/wiki/${a.wiki_slug}`}
              title="Mở trang wiki của điều này"
              className="shrink-0 text-muted-foreground/60 hover:text-primary"
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>open_in_new</span>
            </Link>
          )}
        </div>
        {a.content_md.trim() && (
          <div className="mt-1.5 text-[15px]">
            <WikiContent markdown={a.content_md} />
          </div>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Tổng quan                                                           */
/* ------------------------------------------------------------------ */

function OverviewTab({ doc }: { doc: LegalDocDetail }) {
  const m = doc.meta;
  const validity = validityOf(doc);
  const v = VALIDITY_INFO[validity];

  const rows: [string, React.ReactNode][] = [
    ["Số hiệu", m.doc_number || "—"],
    ["Ngày ban hành", formatViDate(m.issued_date)],
    ["Loại văn bản", m.doc_type || "—"],
    ["Ngày hiệu lực", formatViDate(m.effective_date)],
    ["Cơ quan ban hành", m.issuing_authority || "—"],
    ["Ngày hết hiệu lực", formatViDate(m.expiry_date)],
    ["Lĩnh vực", m.field || "—"],
    [
      "Tình trạng pháp lý",
      <span key="v" className="font-semibold" style={{ color: v.color }}>
        {v.label}
      </span>,
    ],
    [
      "Nguồn thu thập",
      doc.file_url || doc.url ? (
        <a
          key="src"
          href={doc.file_url || doc.url || "#"}
          target="_blank"
          rel="noreferrer"
          className="text-primary hover:underline inline-flex items-center gap-1"
        >
          Mở văn bản gốc
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>open_in_new</span>
        </a>
      ) : (
        doc.file_name || "—"
      ),
    ],
    ["Bố cục", m.article_count ? `${m.article_count} điều` : doc.articles.length ? `${doc.articles.length} điều` : "—"],
  ];

  let validityText = v.label;
  if (validity === "con_hieu_luc" && m.effective_date) validityText = `Còn hiệu lực từ ${formatViDate(m.effective_date)}`;
  if (validity === "chua_co_hieu_luc" && m.effective_date) validityText = `Có hiệu lực từ ${formatViDate(m.effective_date)}`;
  if (doc.replaced_by.length) validityText = `Bị thay thế bởi ${doc.replaced_by.join(", ")}`;
  else if (doc.repealed_by.length) validityText = `Bị bãi bỏ bởi ${doc.repealed_by.join(", ")}`;
  else if (validity === "het_hieu_luc" && m.expiry_date) validityText = `Hết hiệu lực từ ${formatViDate(m.expiry_date)}`;

  return (
    <div className="flex flex-col gap-4 max-w-5xl">
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <dl className="grid grid-cols-1 md:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex border-b border-border md:[&:nth-last-child(-n+2)]:border-b-0 last:border-b-0">
              <dt className="w-40 shrink-0 px-4 py-2.5 text-sm text-muted-foreground bg-muted/40">{label}</dt>
              <dd className="flex-1 px-4 py-2.5 text-sm font-medium min-w-0 break-words">{value}</dd>
            </div>
          ))}
        </dl>
        {m.official_title && (
          <div className="flex border-t border-border">
            <dt className="w-40 shrink-0 px-4 py-2.5 text-sm text-muted-foreground bg-muted/40">Trích yếu</dt>
            <dd className="flex-1 px-4 py-2.5 text-sm font-medium">{m.official_title}</dd>
          </div>
        )}
      </div>

      <div className={cn("rounded-lg px-4 py-2.5 text-sm font-semibold text-white flex items-center gap-2", v.bar)}>
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          {validity === "con_hieu_luc" ? "verified" : validity === "chua_co_hieu_luc" ? "schedule" : "info"}
        </span>
        {validityText}
      </div>

      <div className="bg-card border border-border rounded-xl px-5 py-4">
        <p className="text-sm font-bold mb-2 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: 18 }}>summarize</span>
          Tóm tắt văn bản
        </p>
        {doc.summary ? (
          <div className="text-[15px]">
            <WikiContent markdown={doc.summary} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Chưa có tóm tắt.</p>
        )}
        {doc.overview_slug && (
          <Link
            href={`/wiki/${doc.overview_slug}`}
            className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            Xem trang wiki tổng quan
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>arrow_forward</span>
          </Link>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Lược đồ                                                             */
/* ------------------------------------------------------------------ */

function describeTarget(r: LegalDocRelation, withDoc: boolean, fallback = "—"): string {
  const parts: string[] = [];
  if (r.clause) parts.push(`Khoản ${r.clause}`);
  if (r.article) parts.push(`Điều ${r.article}`);
  if (withDoc && r.doc_number) parts.push(r.doc_number);
  return parts.join(" ") || fallback;
}

function RelationGroups({
  title,
  icon,
  relations,
  labels,
  fromLabel,
  targetLabel,
}: {
  title: string;
  icon: string;
  relations: LegalDocRelation[];
  labels: Record<string, string>;
  fromLabel: (r: LegalDocRelation) => string | null;
  targetLabel: (r: LegalDocRelation) => string;
}) {
  const groups = React.useMemo(() => {
    const g = new Map<string, LegalDocRelation[]>();
    for (const r of relations) {
      const arr = g.get(r.relation_type) ?? [];
      arr.push(r);
      g.set(r.relation_type, arr);
    }
    return Array.from(g);
  }, [relations]);

  return (
    <div className="bg-card border border-border rounded-xl px-5 py-4">
      <p className="text-sm font-bold mb-3 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-primary" style={{ fontSize: 18 }}>{icon}</span>
        {title}
        <span className="text-xs font-normal text-muted-foreground tabular-nums">({relations.length})</span>
      </p>
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa ghi nhận quan hệ nào.</p>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map(([type, items]) => (
            <div key={type}>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                {labels[type] ?? type} <span className="tabular-nums">({items.length})</span>
              </p>
              <ul className="flex flex-col divide-y divide-border/60 border border-border rounded-lg">
                {items.map((r, i) => {
                  const from = fromLabel(r);
                  return (
                    <li key={i} className="px-3 py-2 text-sm">
                      <div className="flex items-center gap-2 flex-wrap">
                        {from && <span className="text-muted-foreground">{from}</span>}
                        {from && (
                          <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>
                            arrow_forward
                          </span>
                        )}
                        <span className="font-medium">{targetLabel(r)}</span>
                      </div>
                      {r.quote && <p className="mt-1 text-xs text-muted-foreground line-clamp-2">{r.quote}</p>}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SchemaTab({ doc }: { doc: LegalDocDetail }) {
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
      <RelationGroups
        title="Văn bản này tác động / căn cứ"
        icon="call_made"
        relations={doc.relations.outgoing}
        labels={RELATION_LABEL_VI}
        fromLabel={(r) => (r.from_article ? `Điều ${r.from_article}` : null)}
        targetLabel={(r) => describeTarget(r, true)}
      />
      {/* Incoming: doc_number is the acting document; the target is a part of this one. */}
      <RelationGroups
        title="Văn bản khác tác động"
        icon="call_received"
        relations={doc.relations.incoming}
        labels={RELATION_INCOMING_LABEL_VI}
        fromLabel={(r) => describeTarget(r, false, "Toàn văn bản")}
        targetLabel={(r) =>
          [r.doc_number, r.from_article ? `Điều ${r.from_article}` : null].filter(Boolean).join(" · ") || "—"
        }
      />
      {doc.wiki_pages.length > 0 && (
        <div className="bg-card border border-border rounded-xl px-5 py-4 xl:col-span-2">
          <p className="text-sm font-bold mb-3 flex items-center gap-1.5">
            <span className="material-symbols-outlined text-primary" style={{ fontSize: 18 }}>auto_stories</span>
            Trang wiki sinh từ văn bản
            <span className="text-xs font-normal text-muted-foreground tabular-nums">({doc.wiki_pages.length})</span>
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-1">
            {doc.wiki_pages.map((p) => (
              <Link
                key={p.slug}
                href={`/wiki/${p.slug}`}
                className="px-2 py-1.5 rounded-md text-[13px] text-foreground/80 hover:bg-muted hover:text-primary truncate"
                title={p.title}
              >
                {p.title}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Đồ thị                                                              */
/* ------------------------------------------------------------------ */

function GraphTab({ doc }: { doc: LegalDocDetail }) {
  const router = useRouter();
  const slug = doc.overview_slug;
  const [graph, setGraph] = React.useState<{ slug: string; data: WikiGraphData | null } | null>(null);
  React.useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    api<WikiGraphData>(`/api/wiki/graph?slug=${encodeURIComponent(slug)}&depth=1`)
      .then((data) => !cancelled && setGraph({ slug, data }))
      .catch(() => !cancelled && setGraph({ slug, data: null }));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (!slug) {
    return (
      <EmptyState
        icon="hub"
        title="Chưa có đồ thị"
        description="Văn bản chưa có trang wiki tổng quan để dựng đồ thị liên kết."
      />
    );
  }
  const data = graph?.slug === slug ? graph.data : undefined;
  if (data === undefined) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">progress_activity</span>
      </div>
    );
  }
  if (!data || data.nodes.length === 0) {
    return <EmptyState icon="hub" title="Chưa có đồ thị" description="Không có liên kết nào quanh văn bản này." />;
  }
  return (
    <div className="rounded-xl overflow-hidden border border-border bg-background">
      <WikiGraph
        nodes={data.nodes}
        edges={data.edges}
        centerSlug={slug}
        height={600}
        onNodeClick={(s) => router.push(`/wiki/${s}`)}
      />
    </div>
  );
}
