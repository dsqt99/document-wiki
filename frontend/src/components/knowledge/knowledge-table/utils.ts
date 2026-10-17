import type { Source } from "../types";

/** Material Symbol per file extension (lower-case, without the dot). */
export const fileIcons: Record<string, string> = {
  pdf: "picture_as_pdf",
  docx: "description",
  doc: "description",
  rtf: "description",
  xlsx: "table_chart",
  xls: "table_chart",
  csv: "table_chart",
  txt: "article",
  md: "article",
  pptx: "slideshow",
  ppt: "slideshow",
};

/** Extension after the last dot of `file_name`, lower-cased; "" when there is none. */
export function getFileExt(source: Pick<Source, "file_name">): string {
  const name = source.file_name ?? "";
  const dot = name.lastIndexOf(".");
  if (dot < 0 || dot === name.length - 1) return "";
  return name.slice(dot + 1).toLowerCase();
}

/** Icon for a table row: by extension, else a link icon for URL sources, else a generic document. */
export function sourceIcon(source: Pick<Source, "file_name" | "source_type">): string {
  const byExt = fileIcons[getFileExt(source)];
  if (byExt) return byExt;
  return source.source_type === "url" ? "link" : "description";
}

/** dd/mm/yyyy in the vi-VN locale; "" when the date cannot be parsed. */
export function formatCreatedDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Key used in /wiki/law/{key} links: the document slug when known, else the id. */
export function lawKey(source: Pick<Source, "id" | "doc_meta">): string {
  return encodeURIComponent(source.doc_meta?.doc_slug || source.id);
}

/** Uppercased initial of the last word in a person's name, "?" when empty. */
export function lastWordInitial(name: string | null | undefined): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  const last = words[words.length - 1];
  return last ? last.charAt(0).toUpperCase() : "?";
}

/** True when a row may use the branch-specific retry entries (chunk / wiki / all). */
export function hasBranchRetry(source: Source): boolean {
  const statusOk = ["error", "partial", "plan_ready", "ready"].includes(source.status);
  const branchStarted =
    (!!source.chunk_status && source.chunk_status !== "pending") ||
    (!!source.wiki_status && source.wiki_status !== "pending");
  return statusOk && branchStarted;
}

export function isRunning(source: Pick<Source, "status">): boolean {
  return source.status === "pending" || source.status === "processing";
}

export function isFailed(source: Pick<Source, "status">): boolean {
  return source.status === "error" || source.status === "partial";
}
