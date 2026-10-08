/** "Wiki Pháp luật" — shapes of /api/wiki/legal-docs. */

export type Validity = "con_hieu_luc" | "chua_co_hieu_luc" | "bi_thay_the" | "het_hieu_luc" | "khong_xac_dinh";

export type LegalDocKnowledgeType = { id: string; name: string; slug: string; color: string };

export type DocMeta = {
  doc_type?: string | null;
  doc_number?: string | null;
  issuing_authority?: string | null;
  official_title?: string | null;
  issued_date?: string | null; // YYYY-MM-DD
  effective_date?: string | null;
  expiry_date?: string | null;
  field?: string | null;
  article_count?: number | null;
  doc_slug?: string | null;
  method?: string;
  extracted_at?: string;
};

export type LegalDoc = {
  id: string;
  title: string;
  file_name: string | null;
  knowledge_type: LegalDocKnowledgeType | null;
  scope_type: string;
  status: string;
  has_file: boolean;
  url: string | null;
  doc_slug: string | null;
  meta: DocMeta;
  validity: Validity | null;
  replaced_by: string[];
  repealed_by: string[];
  created_at: string | null;
  updated_at: string | null;
};

export type LegalDocList = { items: LegalDoc[]; knowledge_types: LegalDocKnowledgeType[] };

export type LegalArticle = {
  num: string;
  heading: string;
  title: string;
  content_md: string;
  chapter_num: string | null;
  chapter_title: string | null;
  wiki_slug: string | null;
};

export type LegalDocRelation = {
  relation_type: string;
  doc_number: string | null;
  article: string | null;
  clause: string | null;
  from_article: string | null;
  quote: string | null;
};

export type LegalDocDetail = LegalDoc & {
  preamble: string;
  articles: LegalArticle[];
  relations: { outgoing: LegalDocRelation[]; incoming: LegalDocRelation[] };
  wiki_pages: { slug: string; title: string; page_type: string; summary: string }[];
  overview_slug: string | null;
  summary: string;
  download_url: string | null;
  file_url: string | null;
};
