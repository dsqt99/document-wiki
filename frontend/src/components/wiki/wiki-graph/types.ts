import { SimulationNodeDatum, SimulationLinkDatum } from "d3-force";

export type GraphNode = SimulationNodeDatum & {
  slug: string;
  title: string;
  page_type: string;
  status?: string;
  scope_type?: string;
  scope_name?: string | null;
  degree?: number;
};

export type GraphLink = SimulationLinkDatum<GraphNode> & {
  from: string;
  to: string;
  type?: string;
  label?: string;
  predicate?: string;
  weight?: number;
  evidence?: string | null;
  target_doc_number?: string | null;
};

export type EdgeInput = {
  from: string;
  to: string;
  type?: string;
  label?: string;
  predicate?: string;
  weight?: number;
  evidence?: string | null;
  target_doc_number?: string | null;
};

export type NodeInput = {
  slug: string;
  title: string;
  page_type: string;
  status?: string;
  scope_type?: string;
  scope_id?: string | null;
  scope_name?: string | null;
};
