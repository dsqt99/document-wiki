"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { WikiGraphData } from "@/types/wiki";
import { api } from "@/lib/api";
import { EmptyState } from "@/components/shared/empty-state";
import { WikiGraph } from "@/components/wiki/wiki-graph";
import { slugPath } from "@/components/review/review-utils";

/** "Đồ thị": one-hop link graph around the document's overview wiki page. */
export function LawGraphTab({ overviewSlug }: { overviewSlug: string | null }) {
  const router = useRouter();
  const [res, setRes] = useState<{ slug: string; data: WikiGraphData | null } | null>(null);

  useEffect(() => {
    if (!overviewSlug) return;
    let stale = false;
    api<WikiGraphData>(`/api/wiki/graph?slug=${encodeURIComponent(overviewSlug)}&depth=1`)
      .then((data) => data)
      .catch(() => null)
      .then((data) => {
        if (!stale) setRes({ slug: overviewSlug, data });
      });
    return () => {
      stale = true;
    };
  }, [overviewSlug]);

  if (!overviewSlug) {
    return (
      <EmptyState
        icon="hub"
        title="Chưa có đồ thị"
        description="Văn bản chưa có trang wiki tổng quan để dựng đồ thị liên kết."
      />
    );
  }

  if (res?.slug !== overviewSlug) {
    return (
      <div className="flex h-64 items-center justify-center">
        <span className="material-symbols-outlined animate-spin text-muted-foreground" style={{ fontSize: 40 }}>
          progress_activity
        </span>
      </div>
    );
  }

  const data = res.data;
  if (!data || !Array.isArray(data.nodes) || data.nodes.length === 0) {
    return <EmptyState icon="hub" title="Chưa có đồ thị" description="Không có liên kết nào quanh văn bản này." />;
  }

  return (
    <div className="overflow-hidden rounded-xl border">
      <WikiGraph
        nodes={data.nodes}
        edges={data.edges ?? []}
        centerSlug={overviewSlug}
        height={600}
        onNodeClick={(slug: string) => router.push(`/wiki/${slugPath(slug)}`)}
      />
    </div>
  );
}
