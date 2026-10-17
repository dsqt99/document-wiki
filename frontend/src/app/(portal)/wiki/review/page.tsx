"use client";

import { Suspense } from "react";
import { ReviewDesk } from "@/components/review/review-desk";

export default function WikiReviewPage() {
  return (
    <Suspense fallback={null}>
      <ReviewDesk />
    </Suspense>
  );
}
