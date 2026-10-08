import { DocMeta, Validity } from "@/types/legal-doc";

export type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
};

export type Department = {
  id: string;
  name: string;
};

export type Source = {
  id: string;
  title: string;
  file_name?: string;
  source_type?: string;
  status: "ready" | "processing" | "error" | "partial" | "pending" | "plan_ready" | "awaiting_approval" | string;
  progress?: number;
  progress_message?: string;
  error_message?: string;
  // Dual pipeline: branch A = raw chunks, branch B = wiki
  chunk_status?: string;
  chunk_progress?: number;
  chunk_error_message?: string;
  wiki_status?: string;
  wiki_progress?: number;
  wiki_error_message?: string;
  page_count?: number;
  wiki_page_count?: number;
  extracted_token_count?: number;
  image_count?: number;
  knowledge_type_id?: string;
  knowledge_type_name?: string;
  knowledge_type_color?: string;
  department_ids?: string[];
  department_names?: string[];
  contributed_by_name?: string;
  scope_type?: string;
  scope_id?: string;
  preserve_verbatim?: boolean;
  pipeline_strategy?: string;
  pipeline_phase?: string;
  // Extracted document metadata (số hiệu, ngày ban hành/hiệu lực, lĩnh vực) + derived validity
  doc_meta?: (DocMeta & { validity?: Validity }) | null;
  created_at: string;
  updated_at?: string;
};
