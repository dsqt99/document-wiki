// Type declarations shared by the wiki screens. No runtime values live here.

export type WikiPageType = "entity" | "concept" | "topic" | "source" | "index" | "log" | "hot";

export type WikiPageStatus = "seed" | "developing" | "mature" | "evergreen";

/** Visibility scope fields carried by pages and graph nodes. */
interface ScopedFields {
  scope_type?: string;
  scope_id?: string | null;
  scope_name?: string | null;
}

export interface WikiPageSummary extends ScopedFields {
  /** Page identifier; may contain "/" */
  slug: string;
  title: string;
  summary: string;
  status: WikiPageStatus;
  page_type: WikiPageType;
  /** Monotonic revision counter. */
  version: number;
  /** ISO datetime */
  updated_at: string;
  /** Ids of source documents */
  source_ids: string[];
  knowledge_type_slugs: string[];
}

export interface WikiScope {
  scope_type: string;
  scope_id: string | null;
  name: string;
}

export interface WikiPageDetail extends WikiPageSummary {
  content_md: string;
  backlinks: string[];
  outlinks: string[];
  orphaned?: boolean;
}

/** Position/velocity written onto nodes by the force simulation. */
interface SimulationState {
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  /** Pinned coordinates; null releases the pin. */
  fx?: number | null;
  fy?: number | null;
}

export interface WikiGraphNode extends ScopedFields, SimulationState {
  slug: string;
  title: string;
  status?: string;
  page_type: string;
}

export interface WikiGraphEdge {
  from: string;
  to: string;
  type?: string;
  label?: string;
  predicate?: string;
  weight?: number;
  evidence?: string | null;
  target_doc_number?: string | null;
  // Attached by the graph library
  source?: WikiGraphNode | string;
  target?: WikiGraphNode | string;
}

export interface WikiGraphData {
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
  total?: number;
  offset?: number;
  has_more?: boolean;
}

export type DraftStatus = "pending" | "needs_revision" | "withdrawn" | "approved" | "rejected";

export type DraftKind = "edit" | "create";

export type AiCheckStatus = "pending" | "queued" | "running" | "passed" | "warned" | "failed" | "skipped";

export type AiCheckMatch =
  | string
  | {
      slug?: string;
      title?: string;
      score?: number;
      line?: number;
      snippet?: string;
    };

export interface AiCheckItem {
  id: string;
  layer: "L1" | "L2" | "L3" | "L4";
  severity: "block" | "warn";
  status: "pass" | "warn" | "fail" | "skipped";
  message: string | null;
  matches: AiCheckMatch[];
}

export interface AiCheckResults {
  version: number;
  summary: { pass: number; warn: number; fail: number; skipped: number };
  checks: AiCheckItem[];
}

export interface DraftSuggestedMetadata {
  slug?: string;
  title?: string;
  page_type?: string;
  knowledge_type_slugs?: string[];
  scope_type?: string;
  scope_id?: string | null;
}

export interface AuthorStats {
  approved: number;
  rejected: number;
  needs_revision: number;
  total_reviewed: number;
  /** 0..1 */
  accuracy: number;
}

export interface SuggestedReviewer {
  id: string;
  name: string | null;
  email: string | null;
  score: number;
}

/** The wiki page a draft targets, as denormalised onto the draft. */
interface DraftTargetPage {
  page_id: string | null;
  page_slug: string;
  page_title: string;
  page_version: number;
  page_scope_type: string;
  page_scope_id: string | null;
  page_scope_name: string | null;
}

/** Who wrote the draft, plus reviewer suggestions for it. */
interface DraftAuthorship {
  author_id: string | null;
  author_name: string | null;
  author_stats: AuthorStats | null;
  suggested_reviewers: SuggestedReviewer[];
}

/** Outcome of the automated pre-review checks. */
interface DraftAiCheck {
  ai_check_status: AiCheckStatus | string;
  ai_check_results: AiCheckResults | null;
  ai_checked_at: string | null;
}

/** Human review decision recorded on the draft. */
interface DraftReviewOutcome {
  reviewer_note: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
}

export interface DraftResponse extends DraftTargetPage, DraftAuthorship, DraftAiCheck, DraftReviewOutcome {
  id: string;
  source: string;
  status: DraftStatus | string;
  draft_kind: DraftKind | string;
  note: string | null;
  content_md: string;
  base_version: number | null;
  has_conflict: boolean;
  revision_round: number;
  last_returned_note: string | null;
  suggested_metadata: DraftSuggestedMetadata | null;
  created_at: string;
  updated_at: string;
}

export interface DraftRoundResponse {
  id: string;
  round_no: number;
  content_md: string;
  author_note: string | null;
  reviewer_return_note: string | null;
  ai_check_results: AiCheckResults | null;
  submitted_at: string;
}
