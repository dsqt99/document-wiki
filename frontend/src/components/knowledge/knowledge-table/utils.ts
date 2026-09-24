import { Source } from "./types";

export const fileIcons: Record<string, string> = {
  pdf: "picture_as_pdf",
  docx: "description",
  xlsx: "table_chart",
  xls: "table_chart",
  csv: "table_chart",
  txt: "article",
  md: "article",
  pptx: "slideshow",
};

export function getFileExt(source: Source): string {
  const name = source.file_name || "";
  return name.split(".").pop()?.toLowerCase() || "";
}

export type LegalCategory = "all" | "luat" | "nghi_dinh" | "thong_tu" | "vbhn" | "quyet_dinh" | "other" | "khac";

export interface LegalMetaInfo {
  category: LegalCategory;
  categoryLabel: string;
  badgeLabel: string;
  badgeClass: string;
  badgeBg: string;
  badgeBorder: string;
  badgeColor: string;
  icon: string;
  docNumber: string | null;
  issuedDate: string | null;
  docDate: string | null;
  authority: string | null;
  issuingAuthority: string | null;
  officialTitle: string | null;
}

export function parseSourceLegalMeta(source: { title?: string; file_name?: string }): LegalMetaInfo {
  const text = (source.title || "") + " " + (source.file_name || "");

  let category: LegalCategory = "other";
  let categoryLabel = "Tài liệu";
  let badgeClass = "border-slate-500/30 text-slate-700 bg-slate-500/10 dark:text-slate-300";
  let badgeBg = "bg-slate-500/10";
  let badgeBorder = "border-slate-500/30";
  let badgeColor = "#64748b";
  let icon = "description";

  if (/vbhn|văn[\s\._\-]*bản[\s\._\-]*hợp[\s\._\-]*nhất/i.test(text)) {
    category = "vbhn";
    categoryLabel = "Văn bản hợp nhất";
    badgeClass = "border-purple-500/30 text-purple-700 bg-purple-500/10 dark:text-purple-300 dark:border-purple-500/40";
    badgeBg = "bg-purple-500/10";
    badgeBorder = "border-purple-500/30";
    badgeColor = "#a855f7";
    icon = "merge_type";
  } else if (/\bluật\b|\bquốc\s*hội\b|\bqh\d+/i.test(text)) {
    category = "luat";
    categoryLabel = "Luật";
    badgeClass = "border-rose-500/30 text-rose-700 bg-rose-500/10 dark:text-rose-300 dark:border-rose-500/40";
    badgeBg = "bg-rose-500/10";
    badgeBorder = "border-rose-500/30";
    badgeColor = "#e11d48";
    icon = "gavel";
  } else if (/nghị[\s\-_]*định|nđ[\-_]cp/i.test(text)) {
    category = "nghi_dinh";
    categoryLabel = "Nghị định";
    badgeClass = "border-amber-500/30 text-amber-700 bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/40";
    badgeBg = "bg-amber-500/10";
    badgeBorder = "border-amber-500/30";
    badgeColor = "#d97706";
    icon = "account_balance";
  } else if (/thông[\s\-_]*tư[\s\-_]*liên[\s\-_]*tịch|ttlt/i.test(text)) {
    category = "thong_tu";
    categoryLabel = "Thông tư LT";
    badgeClass = "border-teal-500/30 text-teal-700 bg-teal-500/10 dark:text-teal-300 dark:border-teal-500/40";
    badgeBg = "bg-teal-500/10";
    badgeBorder = "border-teal-500/30";
    badgeColor = "#0d9488";
    icon = "handshake";
  } else if (/thông[\s\-_]*tư|tt[\-_]bca|tt[\-_]btc/i.test(text)) {
    category = "thong_tu";
    categoryLabel = "Thông tư";
    badgeClass = "border-sky-500/30 text-sky-700 bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/40";
    badgeBg = "bg-sky-500/10";
    badgeBorder = "border-sky-500/30";
    badgeColor = "#0284c7";
    icon = "history_edu";
  } else if (/quyết[\s\-_]*định|qđ[\-_]/i.test(text)) {
    category = "quyet_dinh";
    categoryLabel = "Quyết định";
    badgeClass = "border-emerald-500/30 text-emerald-700 bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/40";
    badgeBg = "bg-emerald-500/10";
    badgeBorder = "border-emerald-500/30";
    badgeColor = "#059669";
    icon = "verified";
  }

  // Extract Doc Number
  const numMatch = text.match(/(?:số\s*[:\s]*|s[oố]\s+)([0-9]+(?:\/[0-9]{4})?\/[A-Za-z0-9\/\-\_ĐđÀ-ỹ]+|[0-9]+[\-_][0-9]{4}[\-_][A-Za-z0-9\-]+|[0-9]+\/VBHN\-[A-Z]+)/i);
  let docNumber = numMatch ? numMatch[1].trim() : null;
  if (!docNumber) {
    const fnMatch = (source.file_name || "").match(/(\d+[\-_]\d+[\-_][A-Za-z0-9\-]+)/);
    if (fnMatch) {
      docNumber = fnMatch[1].replace(/_/g, "/").replace(/-/g, "/");
    }
  }

  // Extract Date
  const dateMatch = text.match(/ngày\s+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4}|\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})/i);
  const issuedDate = dateMatch ? dateMatch[1].trim() : null;

  // Extract Authority
  let authority: string | null = null;
  if (/của\s+Chính\s+phủ/i.test(text)) authority = "Chính phủ";
  else if (/của\s+Quốc\s+hội/i.test(text)) authority = "Quốc hội";
  else if (/của\s+Bộ\s+Công\s+an/i.test(text)) authority = "Bộ Công an";
  else if (/của\s+Bộ\s+Tư\s+pháp/i.test(text)) authority = "Bộ Tư pháp";
  else if (/của\s+Bộ\s+Tài\s+chính/i.test(text)) authority = "Bộ Tài chính";
  else if (/của\s+Văn\s+phòng\s+Quốc\s+hội/i.test(text)) authority = "Văn phòng Quốc hội";
  else if (/của\s+Công\s+an/i.test(text)) authority = "Công an";

  // Official title / subject
  let officialTitle: string | null = null;
  const parenMatch = (source.title || "").match(/\(([^)]+)\)$/);
  if (parenMatch) {
    officialTitle = parenMatch[1].trim();
  }

  return {
    category,
    categoryLabel,
    badgeLabel: categoryLabel,
    badgeClass,
    badgeBg,
    badgeBorder,
    badgeColor,
    icon,
    docNumber,
    issuedDate,
    docDate: issuedDate,
    authority,
    issuingAuthority: authority,
    officialTitle,
  };
}

