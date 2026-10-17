"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import type { LegalDocDetail } from "@/types/legal-doc";
import { VALIDITY_INFO, formatViDate, validityOf } from "@/lib/legal-doc";
import { cn } from "@/lib/utils";
import { WikiContent } from "@/components/wiki/wiki-content";
import { slugPath } from "@/components/review/review-utils";

function statusText(doc: LegalDocDetail): string {
  const validity = validityOf(doc);
  const effective = doc.meta?.effective_date;
  const expiry = doc.meta?.expiry_date;
  let text = VALIDITY_INFO[validity].label;
  if (validity === "con_hieu_luc" && effective) text = `Còn hiệu lực từ ${formatViDate(effective)}`;
  if (validity === "chua_co_hieu_luc" && effective) text = `Có hiệu lực từ ${formatViDate(effective)}`;
  if (doc.replaced_by?.length) text = `Bị thay thế bởi ${doc.replaced_by.join(", ")}`;
  else if (doc.repealed_by?.length) text = `Bị bãi bỏ bởi ${doc.repealed_by.join(", ")}`;
  else if (validity === "het_hieu_luc" && expiry) text = `Hết hiệu lực từ ${formatViDate(expiry)}`;
  return text;
}

/** "Tổng quan": attribute table, validity bar and summary. */
export function LawOverviewTab({ doc }: { doc: LegalDocDetail }) {
  const meta = doc.meta ?? {};
  const validity = validityOf(doc);
  const info = VALIDITY_INFO[validity];
  const sourceHref = doc.file_url || doc.url || null;
  const articleCount = meta.article_count
    ? `${meta.article_count} điều`
    : (doc.articles?.length ?? 0) > 0
      ? `${doc.articles.length} điều`
      : "—";

  const rows: { label: string; value: ReactNode }[] = [
    { label: "Số hiệu", value: meta.doc_number || "—" },
    { label: "Ngày ban hành", value: formatViDate(meta.issued_date) },
    { label: "Loại văn bản", value: meta.doc_type || "—" },
    { label: "Ngày hiệu lực", value: formatViDate(meta.effective_date) },
    { label: "Cơ quan ban hành", value: meta.issuing_authority || "—" },
    { label: "Ngày hết hiệu lực", value: formatViDate(meta.expiry_date) },
    { label: "Lĩnh vực", value: meta.field || "—" },
    {
      label: "Tình trạng pháp lý",
      value: (
        <span className="font-bold" style={{ color: info.color }}>
          {info.label}
        </span>
      ),
    },
    {
      label: "Nguồn thu thập",
      value: sourceHref ? (
        <a
          href={sourceHref}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-0.5 text-primary hover:underline"
        >
          Mở văn bản gốc
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
            open_in_new
          </span>
        </a>
      ) : (
        doc.file_name || "—"
      ),
    },
    { label: "Bố cục", value: articleCount },
  ];

  const statusIcon = validity === "con_hieu_luc" ? "verified" : validity === "chua_co_hieu_luc" ? "schedule" : "info";

  return (
    <div className="flex max-w-5xl flex-col gap-5">
      <div className="overflow-hidden rounded-xl border bg-card">
        <dl className="grid grid-cols-1 md:grid-cols-2">
          {rows.map((r, i) => (
            <div
              key={r.label}
              className={cn(
                "flex border-b text-sm",
                i === rows.length - 1 && "border-b-0",
                i === rows.length - 2 && rows.length % 2 === 0 && "md:border-b-0",
                i % 2 === 0 && "md:border-r",
              )}
            >
              <dt className="w-40 shrink-0 bg-muted/40 px-4 py-2.5 text-muted-foreground">{r.label}</dt>
              <dd className="min-w-0 flex-1 px-4 py-2.5 font-medium break-words">{r.value}</dd>
            </div>
          ))}
          {meta.official_title && (
            <div className="flex border-t text-sm md:col-span-2">
              <dt className="w-40 shrink-0 bg-muted/40 px-4 py-2.5 text-muted-foreground">Trích yếu</dt>
              <dd className="min-w-0 flex-1 px-4 py-2.5 font-medium break-words">{meta.official_title}</dd>
            </div>
          )}
        </dl>
      </div>

      <div className={cn("flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-bold text-white", info.bar)}>
        <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
          {statusIcon}
        </span>
        {statusText(doc)}
      </div>

      <div className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <h2 className="flex items-center gap-2 font-bold">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: 20 }}>
            summarize
          </span>
          Tóm tắt văn bản
        </h2>
        {(doc.summary ?? "").trim() ? (
          <div className="text-[15px]">
            <WikiContent markdown={doc.summary} />
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Chưa có tóm tắt.</p>
        )}
        {doc.overview_slug && (
          <Link
            href={`/wiki/${slugPath(doc.overview_slug)}`}
            className="inline-flex items-center gap-1 self-start text-sm font-medium text-primary hover:underline"
          >
            Xem trang wiki tổng quan
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
              arrow_forward
            </span>
          </Link>
        )}
      </div>
    </div>
  );
}
