"use client";

import { useEffect, useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

type RoleDef = {
  id: string;
  name: string;
  description: string;
};

type MatrixResponse = {
  roles: RoleDef[];
  groups: Record<string, string[]>;
  labels: Record<string, string>;
  descriptions: Record<string, string>;
  all_permissions: string[];
  role_permissions: Record<string, string[]>;
};

const GROUP_ICONS: Record<string, string> = {
  Documents: "description",
  Wiki: "auto_stories",
  "AI Skills": "bolt",
  Organization: "corporate_fare",
  Workspaces: "workspaces",
};

const GROUP_TITLES: Record<string, string> = {
  Documents: "Tài liệu & Văn bản (Documents)",
  Wiki: "Wiki Tri thức (Knowledge Wiki)",
  "AI Skills": "Kỹ năng AI (AI Skills)",
  Organization: "Tổ chức & Hệ thống (Organization)",
  Workspaces: "Không gian làm việc (Workspaces)",
};

export function RolesPermissionsCard() {
  const [data, setData] = useState<MatrixResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [error, setError] = useState("");

  // Working state for role permissions: role_id -> Set of permission keys
  const [workingPerms, setWorkingPerms] = useState<Record<string, Set<string>>>({});
  const [search, setSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  useEffect(() => {
    async function loadMatrix() {
      setLoading(true);
      setError("");
      try {
        const res = await api<MatrixResponse>("/api/rbac/matrix");
        setData(res);
        const mapped: Record<string, Set<string>> = {};
        for (const [r, perms] of Object.entries(res.role_permissions)) {
          mapped[r] = new Set(perms);
        }
        setWorkingPerms(mapped);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Không thể tải ma trận phân quyền");
      } finally {
        setLoading(false);
      }
    }
    void loadMatrix();
  }, []);

  function handleToggle(roleId: string, permKey: string) {
    if (roleId === "admin") return; // Admin is immutable
    setWorkingPerms((prev) => {
      const next = { ...prev };
      const roleSet = new Set(next[roleId] || []);
      if (roleSet.has(permKey)) {
        roleSet.delete(permKey);
      } else {
        roleSet.add(permKey);
      }
      next[roleId] = roleSet;
      return next;
    });
  }

  function handleToggleGroupForRole(roleId: string, groupPerms: string[]) {
    if (roleId === "admin") return;
    setWorkingPerms((prev) => {
      const next = { ...prev };
      const roleSet = new Set(next[roleId] || []);
      const allSelected = groupPerms.every((p) => roleSet.has(p));
      if (allSelected) {
        for (const p of groupPerms) roleSet.delete(p);
      } else {
        for (const p of groupPerms) roleSet.add(p);
      }
      next[roleId] = roleSet;
      return next;
    });
  }

  async function handleSave() {
    setSaving(true);
    setSaveSuccess(false);
    setError("");

    const payload: Record<string, string[]> = {};
    for (const [r, setObj] of Object.entries(workingPerms)) {
      payload[r] = Array.from(setObj);
    }

    try {
      const res = await api<{ success: boolean; role_permissions: Record<string, string[]> }>(
        "/api/rbac/matrix",
        {
          method: "PUT",
          body: { role_permissions: payload },
        }
      );
      if (res?.success) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi khi lưu ma trận phân quyền");
    } finally {
      setSaving(false);
    }
  }

  function toggleCollapse(groupName: string) {
    setCollapsedGroups((prev) => ({ ...prev, [groupName]: !prev[groupName] }));
  }

  // Filter permissions based on search
  const filteredGroups = useMemo(() => {
    if (!data) return {};
    const query = search.trim().toLowerCase();
    if (!query) return data.groups;

    const res: Record<string, string[]> = {};
    for (const [grp, perms] of Object.entries(data.groups)) {
      const matched = perms.filter((p) => {
        const label = (data.labels[p] || "").toLowerCase();
        const desc = (data.descriptions[p] || "").toLowerCase();
        return p.toLowerCase().includes(query) || label.includes(query) || desc.includes(query);
      });
      if (matched.length > 0) {
        res[grp] = matched;
      }
    }
    return res;
  }, [data, search]);

  return (
    <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] dark:shadow-[0_4px_24px_-4px_rgba(0,0,0,0.25)] transition-all">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-6 pb-4 border-b border-border/60">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 shadow-xs">
            <span className="material-symbols-outlined text-[26px]">admin_panel_settings</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight text-foreground">
                Ma trận Vai trò &amp; Phân quyền (RBAC Matrix)
              </h2>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 font-medium">
                4 System Roles
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Cấu hình quyền hạn chi tiết cho từng vai trò người dùng (Viewer, Contributor, Knowledge Manager, Admin).
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          {saveSuccess && (
            <Badge
              variant="outline"
              className="text-emerald-600 border-emerald-500/30 bg-emerald-500/10 gap-1.5 py-1 px-3 text-xs"
            >
              <span className="material-symbols-outlined text-sm">check_circle</span>
              Đã lưu quyền hạn
            </Badge>
          )}

          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving || loading}
            className="gap-1.5 text-xs font-medium h-8 px-3.5 shadow-xs active:scale-[0.98] transition-transform"
          >
            {saving ? (
              <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
            ) : (
              <span className="material-symbols-outlined text-sm">save</span>
            )}
            Lưu ma trận quyền
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground gap-2.5">
          <span className="material-symbols-outlined animate-spin text-xl text-primary">progress_activity</span>
          <span className="text-xs font-medium">Đang tải cấu hình phân quyền...</span>
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* 4 Roles Overview Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            {data.roles.map((r) => {
              const activeCount =
                r.id === "admin"
                  ? data.all_permissions.length
                  : workingPerms[r.id]?.size || 0;
              const isLocked = r.id === "admin";

              return (
                <div
                  key={r.id}
                  className="rounded-xl border border-border/70 bg-muted/20 p-3.5 space-y-2 flex flex-col justify-between hover:border-primary/40 transition-colors"
                >
                  <div className="space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                        {r.id === "admin" && (
                          <span className="material-symbols-outlined text-sm text-purple-500">
                            verified_user
                          </span>
                        )}
                        {r.name}
                      </span>
                      {isLocked && (
                        <span className="text-[10px] text-muted-foreground font-mono bg-background px-1.5 py-0.5 rounded border border-border">
                          Cố định
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">
                      {r.description}
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-border/40 text-[11px]">
                    <span className="text-muted-foreground">Quyền kích hoạt:</span>
                    <span className="font-mono font-semibold text-primary">
                      {activeCount} / {data.all_permissions.length}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Search bar & Quick instructions */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-2">
            <div className="relative flex-1 max-w-sm">
              <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-base">
                search
              </span>
              <Input
                placeholder="Tìm nhanh quyền hạn (ví dụ: wiki, đọc, xóa, skills)..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 text-xs h-8 bg-background"
              />
            </div>

            <p className="text-[11px] text-muted-foreground">
              Nhấp vào ô tích chọn để bật/tắt quyền hạn tương ứng cho vai trò.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-xs font-medium border border-destructive/20 flex items-center gap-2">
              <span className="material-symbols-outlined text-base">error</span>
              <span>{error}</span>
            </div>
          )}

          {/* Matrix Table */}
          <div className="rounded-xl border border-border/80 overflow-hidden bg-card shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left border-collapse min-w-[700px]">
                <thead>
                  <tr className="bg-muted/50 border-b border-border text-muted-foreground font-medium select-none">
                    <th className="py-2.5 px-4 w-[40%]">Tên Quyền &amp; Mô tả</th>
                    <th className="py-2.5 px-2 text-center w-[15%]">Viewer</th>
                    <th className="py-2.5 px-2 text-center w-[15%]">Contributor</th>
                    <th className="py-2.5 px-2 text-center w-[15%]">Knowledge Mgr</th>
                    <th className="py-2.5 px-2 text-center w-[15%]">Admin</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {Object.entries(filteredGroups).map(([groupName, permKeys]) => {
                    const isCollapsed = collapsedGroups[groupName];
                    const iconName = GROUP_ICONS[groupName] || "folder";
                    const groupTitle = GROUP_TITLES[groupName] || groupName;

                    return (
                      <tr key={groupName} className="contents">
                        {/* Group Header Row */}
                        <tr className="bg-muted/30 hover:bg-muted/40 transition-colors">
                          <td colSpan={5} className="py-2 px-3">
                            <div className="flex items-center justify-between">
                              <button
                                type="button"
                                onClick={() => toggleCollapse(groupName)}
                                className="flex items-center gap-2 font-semibold text-foreground text-xs hover:text-primary transition-colors text-left"
                              >
                                <span className="material-symbols-outlined text-base text-primary">
                                  {iconName}
                                </span>
                                <span>{groupTitle}</span>
                                <span className="text-[10px] text-muted-foreground font-mono">
                                  ({permKeys.length} quyền)
                                </span>
                                <span className="material-symbols-outlined text-sm text-muted-foreground">
                                  {isCollapsed ? "expand_more" : "expand_less"}
                                </span>
                              </button>

                              {/* Quick toggle all for roles */}
                              <div className="flex items-center gap-3 text-[10px] text-muted-foreground pr-2">
                                <span className="hidden sm:inline">Chọn cả nhóm:</span>
                                {["viewer", "contributor", "knowledge_manager"].map((rId) => (
                                  <button
                                    key={rId}
                                    type="button"
                                    onClick={() => handleToggleGroupForRole(rId, permKeys)}
                                    className="hover:text-primary transition-colors font-mono underline"
                                    title={`Bật/tắt toàn bộ nhóm ${groupName} cho ${rId}`}
                                  >
                                    {rId === "knowledge_manager" ? "KM" : rId}
                                  </button>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>

                        {/* Group Permission Rows */}
                        {!isCollapsed &&
                          permKeys.map((permKey) => {
                            const label = data.labels[permKey] || permKey;
                            const desc = data.descriptions[permKey] || "";

                            return (
                              <tr
                                key={permKey}
                                className="hover:bg-muted/15 transition-colors border-b border-border/40"
                              >
                                {/* Permission Label & Key */}
                                <td className="py-2 px-4">
                                  <div className="space-y-0.5">
                                    <div className="flex items-center gap-2">
                                      <span className="font-medium text-foreground">{label}</span>
                                      <code className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-muted text-muted-foreground border border-border/60">
                                        {permKey}
                                      </code>
                                    </div>
                                    {desc && (
                                      <p className="text-[11px] text-muted-foreground leading-normal">
                                        {desc}
                                      </p>
                                    )}
                                  </div>
                                </td>

                                {/* Viewer */}
                                <td className="py-2 px-2 text-center">
                                  <input
                                    type="checkbox"
                                    checked={workingPerms["viewer"]?.has(permKey) || false}
                                    onChange={() => handleToggle("viewer", permKey)}
                                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
                                  />
                                </td>

                                {/* Contributor */}
                                <td className="py-2 px-2 text-center">
                                  <input
                                    type="checkbox"
                                    checked={workingPerms["contributor"]?.has(permKey) || false}
                                    onChange={() => handleToggle("contributor", permKey)}
                                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
                                  />
                                </td>

                                {/* Knowledge Manager */}
                                <td className="py-2 px-2 text-center">
                                  <input
                                    type="checkbox"
                                    checked={workingPerms["knowledge_manager"]?.has(permKey) || false}
                                    onChange={() => handleToggle("knowledge_manager", permKey)}
                                    className="h-4 w-4 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
                                  />
                                </td>

                                {/* Admin (Always checked, locked) */}
                                <td className="py-2 px-2 text-center">
                                  <div className="flex items-center justify-center">
                                    <span
                                      className="material-symbols-outlined text-purple-600 dark:text-purple-400 text-base"
                                      title="System Admin luôn sở hữu quyền này"
                                    >
                                      check_circle
                                    </span>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
