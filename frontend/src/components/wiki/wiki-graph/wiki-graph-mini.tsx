"use client";

import { WikiGraph } from "./index";
import type { EdgeInput, NodeInput } from "./types";

/** Compact 180px local graph centred on one page (no controls, no zoom/pan). */
export function WikiGraphMini({ slug, nodes, edges }: { slug: string; nodes: NodeInput[]; edges: EdgeInput[] }) {
  return <WikiGraph nodes={nodes} edges={edges} centerSlug={slug} mini height={180} />;
}
