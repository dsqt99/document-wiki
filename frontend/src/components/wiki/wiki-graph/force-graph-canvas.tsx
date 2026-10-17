"use client";

// Client-only bridge around react-force-graph-2d. It is loaded through next/dynamic by the
// graph component; keeping the library import here lets us hand the instance ref through a
// plain prop and configure the d3 forces right after the canvas mounts.

import { useEffect, type MutableRefObject } from "react";
import ForceGraph2D, { type ForceGraphMethods, type ForceGraphProps } from "react-force-graph-2d";
import { forceManyBody, forceX, forceY } from "d3-force";
import type { GraphLink, GraphNode } from "./types";

export type GraphInstance = ForceGraphMethods<GraphNode, GraphLink>;

type Props = Omit<ForceGraphProps<GraphNode, GraphLink>, "ref"> & {
  graphRef: MutableRefObject<GraphInstance | undefined>;
  mini: boolean;
};

type LinkForceLike = {
  distance: (d: number) => LinkForceLike;
  strength: (s: number) => LinkForceLike;
};

export default function ForceGraphCanvas({ graphRef, mini, ...props }: Props) {
  const data = props.graphData;

  useEffect(() => {
    const fg = graphRef.current;
    if (!fg) return;
    fg.d3Force(
      "x",
      forceX<GraphNode>((n) => n.targetX ?? 0).strength(0.1) as never,
    );
    fg.d3Force("y", forceY<GraphNode>(0).strength(0.05) as never);
    const base = mini ? -60 : -120;
    fg.d3Force(
      "charge",
      forceManyBody<GraphNode>().strength((n) => base * Math.sqrt((n.degree ?? 0) + 1)) as never,
    );
    const link = fg.d3Force("link") as unknown as LinkForceLike | undefined;
    if (link) link.distance(mini ? 35 : 70).strength(0.4);
    fg.d3Force("center", null);
    fg.d3ReheatSimulation();
  }, [graphRef, data, mini]);

  return (
    <ForceGraph2D<GraphNode, GraphLink>
      ref={graphRef as MutableRefObject<GraphInstance | undefined>}
      {...props}
    />
  );
}
