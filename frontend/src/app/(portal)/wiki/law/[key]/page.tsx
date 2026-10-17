"use client";

import { Suspense } from "react";
import { LegalDocDetailView } from "@/components/law/legal-doc-detail";

export default function LegalDocDetailPage() {
  return (
    <Suspense fallback={null}>
      <LegalDocDetailView />
    </Suspense>
  );
}
