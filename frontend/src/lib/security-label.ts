type LabelUser = { role?: string; clearance_level?: string; permissions?: string[] } | null | undefined;
const LEVELS = ["PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL"] as const;

export function selectableSecurityLabels(user: LabelUser): readonly string[] {
  if (user?.role === "admin") return LEVELS;
  const rank = LEVELS.indexOf(user?.clearance_level?.toUpperCase() as typeof LEVELS[number]);
  return LEVELS.slice(0, (rank < 0 ? 1 : rank) + 1);
}

export function defaultSecurityLabel(user: LabelUser): "PUBLIC" | "INTERNAL" {
  return selectableSecurityLabels(user).includes("INTERNAL") ? "INTERNAL" : "PUBLIC";
}

export function canEditSecurityLabel(user: LabelUser): boolean {
  return user?.role === "admin" || !!user?.permissions?.includes("doc:edit:all");
}
