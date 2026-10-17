// Data shapes used by the /knowledge screen and its dialogs.
import type { DocMeta, Validity } from "@/types/legal-doc";

export type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  /** Hex colour string, e.g. "#6366f1" */
  color: string;
  description?: string | null;
  sort_order: number;
  source_count?: number;
};

export type Department = {
  id: string;
  name: string;
};

export type SourceDocMeta = DocMeta & { validity?: Validity | null };

export type SourceStatus =
  | "pending"
  | "processing"
  | "ready"
  | "plan_ready"
  | "awaiting_approval"
  | "partial"
  | "error"
  | string;

export type Source = {
  id: string;
  title: string;
  file_name?: string | null;
  source_type?: string | null;
  status: SourceStatus;
  progress?: number | null;
  progress_message?: string | null;
  error_message?: string | null;
  chunk_status?: string | null;
  chunk_progress?: number | null;
  chunk_error_message?: string | null;
  wiki_status?: string | null;
  wiki_progress?: number | null;
  wiki_error_message?: string | null;
  page_count?: number | null;
  wiki_page_count?: number | null;
  extracted_token_count?: number | null;
  image_count?: number | null;
  knowledge_type_id?: string | null;
  knowledge_type_name?: string | null;
  knowledge_type_color?: string | null;
  department_ids?: string[];
  department_names?: string[];
  contributed_by_name?: string | null;
  scope_type?: string | null;
  scope_id?: string | null;
  preserve_verbatim?: boolean;
  pipeline_strategy?: string | null;
  pipeline_phase?: string | null;
  doc_meta?: SourceDocMeta | null;
  created_at: string;
  updated_at?: string | null;
};

export type SourceListResponse = {
  items: Source[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

/** Error text for display: Error.message when available, otherwise the given fallback. */
export function errorText(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** Tailwind-free colour helpers for hex colours with alpha (#rrggbb + aa). */
export function hexAlpha(hex: string | null | undefined, alpha: number): string | undefined {
  if (!hex) return undefined;
  const clean = hex.trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(clean)) return clean;
  const a = Math.round(Math.max(0, Math.min(1, alpha)) * 255)
    .toString(16)
    .padStart(2, "0");
  return `${clean}${a}`;
}
