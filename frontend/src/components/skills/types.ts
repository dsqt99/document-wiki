/** Data shapes shared by the skill library screens (spec 07f). */

/** Where a skill is visible: globally, or for specific departments. */
type SkillScope = {
  scope_type: string;
  scope_id: string | null;
  department_ids?: string[];
  department_names?: string[];
};

/** Versioning and lifecycle fields of a skill. */
type SkillLifecycle = {
  status: string;
  is_system: boolean;
  current_version: number;
  version_hash?: string | null;
  updated_at: string;
};

export type Skill = SkillScope &
  SkillLifecycle & {
    id: string;
    slug: string;
    name: string;
    description: string | null;
  };

export type SkillListResponse = { items: Skill[]; total: number };

export type SkillContent = { name: string; description: string; body: string };

export type SkillVersion = { version_number: number; created_at?: string; changelog?: string | null };

export type Department = { id: string; name: string };

export type ContributionStatus = "draft" | "pending" | "approved" | "rejected";

/** Row of GET /api/skill-contributions (the caller's own proposals). */
export type MyContribution = {
  id: string;
  title: string;
  status: ContributionStatus | string;
  updated_at: string;
  scope_type?: string | null;
  scope_ids?: string[] | null;
};

/** Row of GET /api/admin/skill-contributions (proposals awaiting review). */
export type PendingContribution = {
  id: string;
  title: string | null;
  skill_id?: string | null;
  contributor_id?: string;
  contributor_name?: string | null;
  description?: string | null;
  status: string;
  created_at: string;
  updated_at?: string;
};

export type ContributionMeta = {
  id: string;
  skill_id: string | null;
  base_version: number | null;
  status: string;
  title: string | null;
};

export type ContributionFile = { path: string; size: number; is_text: boolean };

export type SkillFile = { path: string; size: number; last_modified?: string; is_text: boolean };

export type DiffCode = "M" | "A" | "D";
