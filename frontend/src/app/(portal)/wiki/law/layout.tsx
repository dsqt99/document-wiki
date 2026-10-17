import { Suspense } from "react";

/**
 * The legal-document list reads query params on the client, so it needs a Suspense
 * boundary for static prerendering. The list page itself is team-owned and left untouched.
 */
export default function WikiLawLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}
