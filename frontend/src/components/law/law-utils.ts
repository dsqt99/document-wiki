// Helpers for the legal document detail screen (/wiki/law/[key]).

export type LawTab = "source" | "fulltext" | "overview" | "schema" | "graph";

export const LAW_TABS: { id: LawTab; label: string; icon: string }[] = [
  { id: "source", label: "Tài liệu gốc", icon: "description" },
  { id: "fulltext", label: "Toàn văn", icon: "article" },
  { id: "overview", label: "Tổng quan", icon: "info" },
  { id: "schema", label: "Lược đồ", icon: "account_tree" },
  { id: "graph", label: "Đồ thị", icon: "hub" },
];

export function isLawTab(v: string | null | undefined): v is LawTab {
  return LAW_TABS.some((t) => t.id === v);
}

// Phrases that start the amendment trailer of a consolidated document title. An optional
// "," or ";" plus whitespace in front of the phrase belongs to the trailer.
const TRAILER_START = /[,;]?\s*(có hiệu lực kể từ|đã được sửa đổi|được sửa đổi|sửa đổi, bổ sung bởi)/iu;
const MIN_MAIN_LENGTH = 20;

/** Split a long title into its main part and the amendment trailer (empty when none). */
export function splitLegalTitle(title: string | null | undefined): { main: string; tail: string } {
  const text = title ?? "";
  const m = TRAILER_START.exec(text);
  if (!m || m.index < MIN_MAIN_LENGTH) return { main: text, tail: "" };
  return {
    main: text.slice(0, m.index).trim(),
    tail: text.slice(m.index).replace(/^[\s,;]+/, ""),
  };
}

export type FileKind = "pdf" | "image" | "office" | "other";

const IMAGE_EXT = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"];
const OFFICE_EXT = [".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".md", ".csv", ".json"];

export function fileKindOf(fileName: string | null | undefined): FileKind {
  const name = (fileName ?? "").toLowerCase();
  if (name.endsWith(".pdf")) return "pdf";
  if (IMAGE_EXT.some((e) => name.endsWith(e))) return "image";
  if (OFFICE_EXT.some((e) => name.endsWith(e))) return "office";
  return "other";
}

/** "Khoản 2 Điều 5 <doc_number>" style description of a relation target. */
export function targetDescription(
  rel: { clause: string | null; article: string | null; doc_number: string | null },
  withDocNumber: boolean,
  fallback: string,
): string {
  const parts: string[] = [];
  if (rel.clause) parts.push(`Khoản ${rel.clause}`);
  if (rel.article) parts.push(`Điều ${rel.article}`);
  if (withDocNumber && rel.doc_number) parts.push(rel.doc_number);
  return parts.length ? parts.join(" ") : fallback;
}
