"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type RoleInfo = { id: string; name: string; description: string };

type RbacMatrix = {
  managed?: boolean;
  portal_role_permissions?: Record<string, string[]>;
  roles: RoleInfo[];
  groups: Record<string, string[]>;
  labels: Record<string, string>;
  descriptions: Record<string, string>;
  all_permissions: string[];
  role_permissions: Record<string, string[]>;
};

type SaveResponse = { success: boolean; role_permissions: Record<string, string[]> };

const PORTAL_PERMISSION_LABELS: Record<string, string> = {
  "portal.use": "Sử dụng hệ thống", "users.manage": "Quản lý cán bộ", "org.manage": "Quản lý đơn vị",
  "roles.manage": "Quản lý vai trò và chính sách", "knowledge.manage": "Quản lý kho tri thức",
  "knowledge.approve": "Duyệt tri thức", "ai.models.manage": "Quản lý mô hình AI",
  "ai.prompts.manage": "Quản lý câu lệnh AI", "ai.rag.manage": "Quản lý truy xuất tri thức",
  "ai.guardrails.manage": "Quản lý an toàn AI", "system.config.manage": "Cấu hình hệ thống",
  "monitor.read": "Xem giám sát", "logs.read": "Xem nhật ký", "audit.read": "Xem kiểm vết",
  "alerts.manage": "Quản lý cảnh báo", "reports.export": "Xuất báo cáo",
};

/** Roles that can be edited from this screen; admin is fixed. */
const EDITABLE_ROLES = ["viewer", "contributor", "knowledge_manager"] as const;
type EditableRole = (typeof EDITABLE_ROLES)[number];

const ROLE_SHORT: Record<EditableRole, string> = {
  viewer: "viewer",
  contributor: "contributor",
  knowledge_manager: "KM",
};

const GROUP_META: Record<string, { title: string; icon: string }> = {
  Documents: { title: "Tài liệu & Văn bản (Documents)", icon: "description" },
  Wiki: { title: "Wiki Tri thức (Knowledge Wiki)", icon: "auto_stories" },
  "AI Skills": { title: "Kỹ năng AI (AI Skills)", icon: "bolt" },
  Organization: { title: "Tổ chức & Hệ thống (Organization)", icon: "corporate_fare" },
  Workspaces: { title: "Không gian làm việc (Workspaces)", icon: "workspaces" },
};

function groupMeta(key: string) {
  return GROUP_META[key] ?? { title: key, icon: "folder" };
}

function toSets(source: Record<string, string[]>): Record<string, Set<string>> {
  const out: Record<string, Set<string>> = {};
  for (const [role, perms] of Object.entries(source)) out[role] = new Set(perms);
  return out;
}

export function RolesPermissionsCard() {
  const [matrix, setMatrix] = useState<RbacMatrix | null>(null);
  const [draft, setDraft] = useState<Record<string, Set<string>>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saved, setSaved] = useState(false);
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let alive = true;
    api<RbacMatrix>("/api/rbac/matrix")
      .then((m) => {
        if (!alive) return;
        setMatrix(m);
        setDraft(toSets(m.role_permissions ?? {}));
        setLoadError("");
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setLoadError(err instanceof Error && err.message ? err.message : "Không thể tải ma trận phân quyền");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      if (savedTimer.current) clearTimeout(savedTimer.current);
    };
  }, []);

  const allPerms = matrix?.all_permissions ?? [];
  const total = allPerms.length;
  const q = search.trim().toLowerCase();

  function labelOf(perm: string) {
    return matrix?.labels?.[perm] || perm;
  }
  function descOf(perm: string) {
    return matrix?.descriptions?.[perm] || "";
  }
  function matches(perm: string) {
    if (!q) return true;
    return (
      perm.toLowerCase().includes(q) || labelOf(perm).toLowerCase().includes(q) || descOf(perm).toLowerCase().includes(q)
    );
  }

  function has(role: string, perm: string) {
    return draft[role]?.has(perm) ?? false;
  }

  function toggle(role: string, perm: string, on: boolean) {
    if (role === "admin") return;
    setDraft((prev) => {
      const next = new Set(prev[role] ?? []);
      if (on) next.add(perm);
      else next.delete(perm);
      return { ...prev, [role]: next };
    });
  }

  function toggleGroup(role: string, perms: string[]) {
    if (role === "admin" || perms.length === 0) return;
    setDraft((prev) => {
      const current = prev[role] ?? new Set<string>();
      const allOn = perms.every((p) => current.has(p));
      const next = new Set(current);
      for (const p of perms) {
        if (allOn) next.delete(p);
        else next.add(p);
      }
      return { ...prev, [role]: next };
    });
  }

  async function save() {
    if (!matrix) return;
    setSaving(true);
    setSaveError("");
    setSaved(false);
    try {
      const role_permissions: Record<string, string[]> = {};
      for (const role of matrix.roles) {
        const set = draft[role.id] ?? new Set<string>();
        // Keep the catalogue order so the payload is stable.
        role_permissions[role.id] = allPerms.filter((p) => set.has(p));
      }
      const res = await api<SaveResponse>("/api/rbac/matrix", { method: "PUT", body: { role_permissions } });
      if (res?.role_permissions) setDraft(toSets(res.role_permissions));
      setSaved(true);
      if (savedTimer.current) clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error && err.message ? err.message : "Lỗi khi lưu ma trận phân quyền");
    } finally {
      setSaving(false);
    }
  }

  const groups = Object.entries(matrix?.groups ?? {})
    .map(([key, perms]) => ({ key, perms: perms.filter(matches) }))
    .filter((g) => g.perms.length > 0);

  if (matrix?.managed) {
    return (
      <div className="space-y-4 rounded-2xl border bg-card p-5">
        <div>
          <h2 className="font-semibold">Vai trò &amp; quyền dùng chung</h2>
          <p className="mt-1 text-sm text-muted-foreground">Quản lý tại Cán bộ &amp; đơn vị → Vai trò &amp; quyền. Quyền trên Kho tri thức áp dụng theo phạm vi đơn vị và nhãn bảo mật được cấp.</p>
        </div>
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted"><tr><th className="p-3">Vai trò</th><th className="p-3">Quyền dùng chung</th><th className="p-3">Quyền trên Kho tri thức</th></tr></thead>
            <tbody>{matrix.roles.map((role) => (
              <tr key={role.id} className="border-t align-top">
                <td className="p-3 font-medium">{role.name}<p className="mt-1 text-xs font-normal text-muted-foreground">{role.description}</p></td>
                <td className="p-3"><div className="flex flex-wrap gap-1">{(matrix.portal_role_permissions?.[role.id] ?? []).map((permission) => <span key={permission} className="rounded-md bg-muted px-2 py-1 text-xs">{PORTAL_PERMISSION_LABELS[permission] ?? permission}</span>)}</div></td>
                <td className="p-3"><ul className="space-y-1">{(matrix.role_permissions[role.id] ?? []).map((permission) => <li key={permission} className="text-xs text-muted-foreground">{matrix.labels[permission] ?? permission}</li>)}</ul></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-border/80 bg-card p-6 shadow-lift">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3 border-b border-border/60 pb-4">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-400">
          <span className="material-symbols-outlined text-[20px]">admin_panel_settings</span>
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-2 text-base font-semibold tracking-tight text-foreground">
            Ma trận Vai trò &amp; Phân quyền (RBAC Matrix)
            <span className="rounded border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-violet-700 dark:text-violet-300">
              4 System Roles
            </span>
          </h2>
          <p className="text-xs text-muted-foreground">
            Cấu hình quyền hạn chi tiết cho từng vai trò người dùng (Viewer, Contributor, Knowledge Manager, Admin).
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saved && (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-700 dark:text-emerald-300">
              <span className="material-symbols-outlined text-sm">check_circle</span>
              Đã lưu quyền hạn
            </span>
          )}
          <Button type="button" size="sm" className="gap-1.5" disabled={saving || loading || !matrix} onClick={() => void save()}>
            <span className={cn("material-symbols-outlined text-base", saving && "animate-spin")}>
              {saving ? "progress_activity" : "save"}
            </span>
            Lưu ma trận quyền
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
          <span className="material-symbols-outlined animate-spin text-xl">progress_activity</span>
          Đang tải cấu hình phân quyền...
        </div>
      ) : !matrix ? (
        loadError ? (
          <ErrorFrame text={loadError} />
        ) : null
      ) : (
        <>
          {loadError && <ErrorFrame text={loadError} />}

          {/* Role summary cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {matrix.roles.map((role) => {
              const isAdmin = role.id === "admin";
              const count = isAdmin ? total : allPerms.filter((p) => has(role.id, p)).length;
              return (
                <div key={role.id} className="flex flex-col gap-1.5 rounded-xl border border-border/70 bg-background p-3.5">
                  <div className="flex items-center gap-1.5">
                    {isAdmin && (
                      <span className="material-symbols-outlined text-base text-violet-600 dark:text-violet-400">
                        verified_user
                      </span>
                    )}
                    <span className="truncate text-sm font-semibold text-foreground">{role.name}</span>
                    {isAdmin && (
                      <span className="ml-auto rounded bg-violet-500/10 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 dark:text-violet-300">
                        Cố định
                      </span>
                    )}
                  </div>
                  <p className="line-clamp-2 min-h-8 text-xs text-muted-foreground">{role.description}</p>
                  <div className="mt-auto flex items-center justify-between border-t border-border/50 pt-1.5 text-[11px] text-muted-foreground">
                    <span>Quyền kích hoạt:</span>
                    <span className="font-mono font-semibold text-foreground tabular-nums">
                      {count} / {total}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Search */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <div className="relative w-full max-w-sm">
              <span className="material-symbols-outlined pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-base text-muted-foreground">
                search
              </span>
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Tìm nhanh quyền hạn (ví dụ: wiki, đọc, xóa, skills)..."
                className="pl-8 text-sm"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Nhấp vào ô tích chọn để bật/tắt quyền hạn tương ứng cho vai trò.
            </p>
          </div>

          {saveError && <ErrorFrame text={saveError} />}

          {/* Matrix */}
          <div className="overflow-x-auto rounded-xl border border-border/70">
            <table className="w-full min-w-[700px] table-fixed border-collapse text-sm">
              <colgroup>
                <col className="w-[40%]" />
                <col className="w-[15%]" />
                <col className="w-[15%]" />
                <col className="w-[15%]" />
                <col className="w-[15%]" />
              </colgroup>
              <thead>
                <tr className="border-b border-border/70 bg-muted/30 text-xs text-muted-foreground">
                  <th className="px-4 py-2.5 text-left font-medium">Tên Quyền &amp; Mô tả</th>
                  <th className="px-2 py-2.5 text-center font-medium">Viewer</th>
                  <th className="px-2 py-2.5 text-center font-medium">Contributor</th>
                  <th className="px-2 py-2.5 text-center font-medium">Knowledge Mgr</th>
                  <th className="px-2 py-2.5 text-center font-medium">Admin</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => {
                  const meta = groupMeta(g.key);
                  const isCollapsed = !!collapsed[g.key];
                  return (
                    <GroupRows
                      key={g.key}
                      title={meta.title}
                      icon={meta.icon}
                      perms={g.perms}
                      collapsed={isCollapsed}
                      onToggleCollapse={() => setCollapsed((prev) => ({ ...prev, [g.key]: !prev[g.key] }))}
                      onToggleGroup={(role) => toggleGroup(role, g.perms)}
                      has={has}
                      onToggle={toggle}
                      labelOf={labelOf}
                      descOf={descOf}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function ErrorFrame({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
      <span className="material-symbols-outlined text-base">error</span>
      <span className="min-w-0 break-words">{text}</span>
    </div>
  );
}

function GroupRows({
  title,
  icon,
  perms,
  collapsed,
  onToggleCollapse,
  onToggleGroup,
  has,
  onToggle,
  labelOf,
  descOf,
}: {
  title: string;
  icon: string;
  perms: string[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  onToggleGroup: (role: EditableRole) => void;
  has: (role: string, perm: string) => boolean;
  onToggle: (role: string, perm: string, on: boolean) => void;
  labelOf: (perm: string) => string;
  descOf: (perm: string) => string;
}) {
  return (
    <>
      <tr className="border-b border-border/60 bg-muted/40">
        <td colSpan={5} className="px-4 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="flex items-center gap-2 text-left text-sm font-medium text-foreground"
              aria-expanded={!collapsed}
              onClick={onToggleCollapse}
            >
              <span className="material-symbols-outlined text-lg text-primary">{icon}</span>
              {title}
              <span className="font-mono text-[11px] font-normal text-muted-foreground">({perms.length} quyền)</span>
              <span className="material-symbols-outlined text-base text-muted-foreground">
                {collapsed ? "expand_more" : "expand_less"}
              </span>
            </button>
            <div className="ml-auto flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="hidden sm:inline">Chọn cả nhóm:</span>
              {EDITABLE_ROLES.map((role) => (
                <button
                  key={role}
                  type="button"
                  className="font-mono text-primary underline underline-offset-2 hover:text-primary/80"
                  onClick={() => onToggleGroup(role)}
                >
                  {ROLE_SHORT[role]}
                </button>
              ))}
            </div>
          </div>
        </td>
      </tr>
      {!collapsed &&
        perms.map((perm) => {
          const desc = descOf(perm);
          return (
            <tr key={perm} className="border-b border-border/40 last:border-b-0 hover:bg-muted/20">
              <td className="px-4 py-2.5 align-top">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium text-foreground">{labelOf(perm)}</span>
                  <span className="rounded border border-border bg-muted/50 px-1.5 py-px font-mono text-[10px] text-muted-foreground">
                    {perm}
                  </span>
                </div>
                {desc && <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>}
              </td>
              {EDITABLE_ROLES.map((role) => (
                <td key={role} className="px-2 py-2.5 text-center align-middle">
                  <Checkbox
                    aria-label={`${role}: ${perm}`}
                    checked={has(role, perm)}
                    onCheckedChange={(on) => onToggle(role, perm, on)}
                  />
                </td>
              ))}
              <td className="px-2 py-2.5 text-center align-middle">
                <span
                  className="material-symbols-outlined text-lg text-violet-600 dark:text-violet-400"
                  title="System Admin luôn sở hữu quyền này"
                >
                  check_circle
                </span>
              </td>
            </tr>
          );
        })}
    </>
  );
}
