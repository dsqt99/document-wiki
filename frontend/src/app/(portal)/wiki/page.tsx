import { redirect } from "next/navigation";

/** `/wiki` has no screen of its own; send readers to the legal-document library. */
export default function WikiIndexPage() {
  redirect("/wiki/law");
}
