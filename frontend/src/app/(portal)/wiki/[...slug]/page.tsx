"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { sanitizeWikiLibraryReturnTo, wikiPageQuery } from "@/lib/wiki-navigation";
import { WikiPageView } from "./wiki-page-view";
import { SourceDetailView } from "./source-detail";

export default function WikiSlugPage() {
  return (
    <Suspense fallback={null}>
      <WikiSlugRoute />
    </Suspense>
  );
}

function decodeSegments(raw: string | string[] | undefined): string {
  const parts = Array.isArray(raw) ? raw : raw ? [raw] : [];
  return parts
    .map((p) => {
      try {
        return decodeURIComponent(p);
      } catch {
        return p;
      }
    })
    .join("/");
}

/** Reads the route, owns in-place navigation (pushState / popstate) and hands the slug to the view. */
function WikiSlugRoute() {
  const params = useParams<{ slug: string[] }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const paramSlug = decodeSegments(params?.slug);
  const scopeType = searchParams.get("scopeType");
  const scopeId = searchParams.get("scopeId");
  const returnTo = sanitizeWikiLibraryReturnTo(searchParams.get("returnTo"));

  // In-place navigation keeps the component mounted; a real route change resets it.
  const [nav, setNav] = useState({ base: paramSlug, slug: paramSlug });
  const slug = nav.base === paramSlug ? nav.slug : paramSlug;

  const hasScope = !!scopeType && scopeType !== "global";
  const scopeSuffix = useMemo(
    () => wikiPageQuery(hasScope ? scopeType : null, hasScope ? scopeId : null, returnTo),
    [hasScope, scopeType, scopeId, returnTo],
  );

  const navigate = useCallback(
    (next: string) => {
      const clean = next.replace(/^\/+/, "");
      const path = `/wiki/${clean.split("/").map(encodeURIComponent).join("/")}${scopeSuffix}`;
      window.history.pushState(null, "", path);
      setNav({ base: paramSlug, slug: clean });
    },
    [paramSlug, scopeSuffix],
  );

  useEffect(() => {
    const onPop = () => {
      const p = window.location.pathname;
      if (!p.startsWith("/wiki/")) return;
      const rest = p.slice("/wiki/".length);
      setNav({ base: paramSlug, slug: decodeSegments(rest.split("/")) });
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [paramSlug]);

  if (slug.startsWith("source/") && slug.split("/").length === 2) {
    return <SourceDetailView key={slug} sourceId={slug.split("/")[1]} initialTab={searchParams.get("tab")} goTo={(href) => router.push(href)} />;
  }

  return (
    <WikiPageView
      slug={slug}
      scopeType={hasScope ? scopeType : null}
      scopeId={hasScope ? scopeId : null}
      scopeSuffix={scopeSuffix}
      returnTo={returnTo}
      navigate={navigate}
      goTo={(href) => router.push(href)}
      autoEdit={searchParams.get("edit") === "1" && slug === paramSlug}
    />
  );
}
