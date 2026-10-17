"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/** Legacy URL: editing now happens from the library and detail pages. */
export default function SkillEditRedirect() {
  const params = useParams<{ slug: string }>();
  const router = useRouter();
  const slug = String(params?.slug ?? "");

  useEffect(() => {
    if (slug) router.replace(`/skills/${slug}`);
  }, [slug, router]);

  return null;
}
