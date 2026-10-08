import { redirect } from "next/navigation";

// The standalone wiki index was folded into "Trang wiki" (/wiki/law).
export default function WikiIndexRedirect() {
  redirect("/wiki/law");
}
