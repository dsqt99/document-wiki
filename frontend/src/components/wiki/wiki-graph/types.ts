// Data shapes for the force-directed wiki graph.

export interface NodeInput {
  slug: string;
  title: string;
  page_type: string;
  status?: string;
  scope_type?: string;
  scope_id?: string | null;
  scope_name?: string | null;
}

export interface EdgeInput {
  from: string;
  to: string;
  type?: string;
  label?: string;
  predicate?: string;
  weight?: number;
  evidence?: string | null;
  target_doc_number?: string | null;
}

/** Simulation node: input fields + id (= slug), degree and coordinates owned by d3-force. */
export interface GraphNode extends NodeInput {
  id: string;
  degree: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
  /** Target X used by the per-component forceX. */
  targetX?: number;
}

/** Simulation link; d3 replaces the string ends with node objects once started. */
export interface GraphLink extends Omit<EdgeInput, "from" | "to"> {
  from: string;
  to: string;
  source: string | GraphNode;
  target: string | GraphNode;
}
