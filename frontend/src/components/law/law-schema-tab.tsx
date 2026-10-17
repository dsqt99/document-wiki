"use client";

import Link from "next/link";
import type { LegalDocDetail, LegalDocRelation } from "@/types/legal-doc";
import { RELATION_INCOMING_LABEL_VI, RELATION_LABEL_VI } from "@/lib/legal-doc";
import { slugPath } from "@/components/review/review-utils";
import { targetDescription } from "./law-utils";

type RelationBlockProps = {
  title: string;
  icon: string;
  relations: LegalDocRelation[];
  labels: Record<string, string>;
  sourceLabel: (r: LegalDocRelation) => string;
  targetLabel: (r: LegalDocRelation) => string;
};

function groupByType(relations: LegalDocRelation[]): [string, LegalDocRelation[]][] {
  const groups = new Map<string, LegalDocRelation[]>();
  for (const r of relations) {
    const list = groups.get(r.relation_type);
    if (list) list.push(r);
    else groups.set(r.relation_type, [r]);
  }
  return [...groups.entries()];
}

function RelationBlock({ title, icon, relations, labels, sourceLabel, targetLabel }: RelationBlockProps) {
  const groups = groupByType(relations);
  return (
    <div className="flex flex-col gap-4 rounded-xl border bg-card p-5">
      <h2 className="flex items-center gap-2 font-bold">
        <span className="material-symbols-outlined text-primary" style={{ fontSize: 20 }}>
          {icon}
        </span>
        {title}
        <span className="font-normal text-muted-foreground">({relations.length})</span>
      </h2>
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa ghi nhận quan hệ nào.</p>
      ) : (
        groups.map(([type, items]) => (
          <div key={type} className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
              {labels[type] ?? type} ({items.length})
            </span>
            <ul className="divide-y rounded-lg border">
              {items.map((r, i) => {
                const src = sourceLabel(r);
                return (
                  <li key={i} className="flex flex-col gap-1 px-3 py-2 text-sm">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {src && (
                        <>
                          <span className="text-muted-foreground">{src}</span>
                          <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>
                            arrow_forward
                          </span>
                        </>
                      )}
                      <span className="font-medium">{targetLabel(r)}</span>
                    </div>
                    {r.quote && <p className="line-clamp-2 text-xs text-muted-foreground">{r.quote}</p>}
                  </li>
                );
              })}
            </ul>
          </div>
        ))
      )}
    </div>
  );
}

/** "Lược đồ": outgoing / incoming relations and the wiki pages generated from the document. */
export function LawSchemaTab({ doc }: { doc: LegalDocDetail }) {
  const outgoing = doc.relations?.outgoing ?? [];
  const incoming = doc.relations?.incoming ?? [];
  const pages = doc.wiki_pages ?? [];

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <RelationBlock
        title="Văn bản này tác động / căn cứ"
        icon="call_made"
        relations={outgoing}
        labels={RELATION_LABEL_VI}
        sourceLabel={(r) => (r.from_article ? `Điều ${r.from_article}` : "")}
        targetLabel={(r) => targetDescription(r, true, "—")}
      />
      <RelationBlock
        title="Văn bản khác tác động"
        icon="call_received"
        relations={incoming}
        labels={RELATION_INCOMING_LABEL_VI}
        sourceLabel={(r) => targetDescription(r, false, "Toàn văn bản")}
        targetLabel={(r) =>
          [r.doc_number, r.from_article ? `Điều ${r.from_article}` : null].filter(Boolean).join(" · ") || "—"
        }
      />
      {pages.length > 0 && (
        <div className="flex flex-col gap-3 rounded-xl border bg-card p-5 xl:col-span-2">
          <h2 className="flex items-center gap-2 font-bold">
            <span className="material-symbols-outlined text-primary" style={{ fontSize: 20 }}>
              auto_stories
            </span>
            Trang wiki sinh từ văn bản ({pages.length})
          </h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {pages.map((p) => (
              <Link
                key={p.slug}
                href={`/wiki/${slugPath(p.slug)}`}
                title={p.title}
                className="truncate rounded-lg border px-3 py-2 text-sm hover:bg-muted hover:text-primary"
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
