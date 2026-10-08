import { LegalDoc, Validity } from "@/types/legal-doc";

export const VALIDITY_ORDER: Validity[] = [
  "con_hieu_luc",
  "chua_co_hieu_luc",
  "bi_thay_the",
  "het_hieu_luc",
  "khong_xac_dinh",
];

export const VALIDITY_INFO: Record<Validity, { label: string; color: string; badge: string; bar: string }> = {
  con_hieu_luc: {
    label: "Còn hiệu lực",
    color: "#059669",
    badge: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30 dark:text-emerald-400",
    bar: "bg-emerald-600",
  },
  chua_co_hieu_luc: {
    label: "Chưa có hiệu lực",
    color: "#d97706",
    badge: "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:text-amber-400",
    bar: "bg-amber-500",
  },
  bi_thay_the: {
    label: "Bị thay thế",
    color: "#7c3aed",
    badge: "bg-violet-500/10 text-violet-700 border-violet-500/30 dark:text-violet-400",
    bar: "bg-violet-600",
  },
  het_hieu_luc: {
    label: "Hết hiệu lực",
    color: "#dc2626",
    badge: "bg-red-500/10 text-red-700 border-red-500/30 dark:text-red-400",
    bar: "bg-red-600",
  },
  khong_xac_dinh: {
    label: "Chưa xác định",
    color: "#64748b",
    badge: "bg-slate-500/10 text-slate-600 border-slate-500/30 dark:text-slate-400",
    bar: "bg-slate-500",
  },
};

export function validityOf(d: Pick<LegalDoc, "validity">): Validity {
  return d.validity ?? "khong_xac_dinh";
}

/** YYYY-MM-DD → dd/mm/yyyy (no timezone shifts). */
export function formatViDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

export function docTypeOf(d: LegalDoc): string {
  return d.meta.doc_type || "Khác";
}

/** URL key for the detail page: doc_slug when present, else source id. */
export function legalDocKey(d: Pick<LegalDoc, "doc_slug" | "id">): string {
  return d.doc_slug || d.id;
}

export function legalDocHref(d: Pick<LegalDoc, "doc_slug" | "id">, tab?: string): string {
  const base = `/wiki/law/${encodeURIComponent(legalDocKey(d))}`;
  return tab ? `${base}?tab=${tab}` : base;
}

export const RELATION_LABEL_VI: Record<string, string> = {
  sua_doi: "Sửa đổi",
  bo_sung: "Bổ sung",
  thay_the: "Thay thế",
  bai_bo: "Bãi bỏ",
  huong_dan: "Hướng dẫn",
  can_cu: "Căn cứ",
  dan_chieu: "Dẫn chiếu",
};

/** Passive form, for relations other documents make to this one. */
export const RELATION_INCOMING_LABEL_VI: Record<string, string> = {
  sua_doi: "Bị sửa đổi bởi",
  bo_sung: "Được bổ sung bởi",
  thay_the: "Bị thay thế bởi",
  bai_bo: "Bị bãi bỏ bởi",
  huong_dan: "Được hướng dẫn bởi",
  can_cu: "Là căn cứ của",
  dan_chieu: "Được dẫn chiếu bởi",
};
