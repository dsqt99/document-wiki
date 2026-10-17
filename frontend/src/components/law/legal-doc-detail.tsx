"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import type { LegalDocDetail } from "@/types/legal-doc";
import { api } from "@/lib/api";
import { VALIDITY_INFO, validityOf } from "@/lib/legal-doc";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";
import { LegalDocTitle } from "./legal-doc-title";
import { LawSourceTab } from "./law-source-tab";
import { LawFulltextTab } from "./law-fulltext-tab";
import { LawOverviewTab } from "./law-overview-tab";
import { LawSchemaTab } from "./law-schema-tab";
import { LawGraphTab } from "./law-graph-tab";
import { LAW_TABS, isLawTab, type LawTab } from "./law-utils";

function decodeKey(raw: string | string[] | undefined): string {
  const value = Array.isArray(raw) ? raw.join("/") : (raw ?? "");
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function BackLink() {
  return (
    <Link
      href="/wiki/law"
      className="inline-flex items-center gap-1 self-start text-sm text-muted-foreground hover:text-primary"
    >
      <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
        arrow_back
      </span>
      Danh sách văn bản
    </Link>
  );
}

/** Legal document detail screen (route /wiki/law/[key]). */
export function LegalDocDetailView() {
  const params = useParams<{ key: string }>();
  const key = decodeKey(params?.key);
  const router = useRouter();
  const searchParams = useSearchParams();

  const [res, setRes] = useState<{ key: string; doc: LegalDocDetail | null; error: string | null } | null>(null);

  useEffect(() => {
    if (!key) return;
    let stale = false;
    api<LegalDocDetail>(`/api/wiki/legal-docs/${encodeURIComponent(key)}`)
      .then((doc) => ({ key, doc, error: null }))
      .catch((err: unknown) => ({
        key,
        doc: null,
        error: err instanceof Error && err.message ? err.message : "Không tải được văn bản",
      }))
      .then((next) => {
        if (!stale) setRes(next);
      });
    return () => {
      stale = true;
    };
  }, [key]);

  if (!res || res.key !== key) {
    return (
      <div className="flex h-64 items-center justify-center">
        <span className="material-symbols-outlined animate-spin text-muted-foreground" style={{ fontSize: 48 }}>
          progress_activity
        </span>
      </div>
    );
  }

  if (!res.doc) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink />
        <EmptyState icon="error" title="Không mở được văn bản" description={res.error ?? "Không tải được văn bản"} />
      </div>
    );
  }

  const doc = res.doc;
  const tabParam = searchParams.get("tab");
  const hasFile = doc.has_file || !!doc.file_url;
  const tab: LawTab = isLawTab(tabParam) ? tabParam : hasFile ? "source" : "fulltext";

  const selectTab = (next: LawTab) => {
    const qs = new URLSearchParams(searchParams.toString());
    qs.set("tab", next);
    router.replace(`/wiki/law/${encodeURIComponent(key)}?${qs.toString()}`, { scroll: false });
  };

  const meta = doc.meta ?? {};
  const validity = VALIDITY_INFO[validityOf(doc)];
  const pill = "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5";

  return (
    <div className="flex flex-col gap-5">
      <BackLink />

      <div className="flex flex-col gap-2.5">
        <LegalDocTitle title={doc.title} />
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {meta.doc_type && (
            <span className={cn(pill, "border-primary/30 bg-primary/10 font-semibold text-primary")}>{meta.doc_type}</span>
          )}
          <span className={cn(pill, "font-semibold", validity.badge)}>{validity.label}</span>
          {meta.doc_number && <span className={cn(pill, "bg-muted/50 font-medium")}>{meta.doc_number}</span>}
          {doc.knowledge_type && (
            <span className={cn(pill, "font-medium")}>
              <span className="size-2 rounded-full" style={{ backgroundColor: doc.knowledge_type.color }} />
              {doc.knowledge_type.name}
            </span>
          )}
          {meta.field && <span className={cn(pill, "text-muted-foreground")}>{meta.field}</span>}
          {doc.download_url && (
            <a
              href={doc.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(pill, "ml-auto font-medium hover:bg-muted hover:text-primary")}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                download
              </span>
              Tải về
            </a>
          )}
        </div>
      </div>

      <nav className="flex overflow-x-auto border-b" role="tablist">
        {LAW_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => selectTab(t.id)}
            className={cn(
              "-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
              tab === t.id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              {t.icon}
            </span>
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "source" && <LawSourceTab doc={doc} />}
      {tab === "fulltext" && <LawFulltextTab doc={doc} />}
      {tab === "overview" && <LawOverviewTab doc={doc} />}
      {tab === "schema" && <LawSchemaTab doc={doc} />}
      {tab === "graph" && <LawGraphTab overviewSlug={doc.overview_slug} />}
    </div>
  );
}
