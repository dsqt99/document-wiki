"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { DeptChecklist, fieldLabelCls } from "./dept-checklist";
import { ScopeSelect, type GlobalOrDept } from "./scope-select";
import { errMessage, isValidDisplayName } from "./skill-utils";
import type { Department, Skill } from "./types";

/**
 * Rename / change scope of a skill. Mount with `key={skill.id}` so the form starts from the
 * skill's current values each time it opens.
 */
export function SkillRenameDialog({
  skill,
  departments,
  onClose,
  onSaved,
}: {
  skill: Skill | null;
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(skill?.name ?? "");
  const [scope, setScope] = useState<GlobalOrDept>(skill?.scope_type === "department" ? "department" : "global");
  const [deptIds, setDeptIds] = useState<string[]>(skill?.department_ids ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const system = !!skill?.is_system;
  const nameOk = system || isValidDisplayName(name);

  const save = async () => {
    if (!skill || !nameOk) return;
    setSaving(true);
    setError(null);
    const isDept = scope === "department";
    const body: Record<string, unknown> = {
      department_ids: isDept ? deptIds : [],
      scope_type: scope,
      scope_id: isDept && deptIds.length ? deptIds[0] : null,
    };
    if (!system && name) body.name = name;
    try {
      await api(`/api/skills/${skill.id}`, { method: "PATCH", body });
      onSaved();
      onClose();
    } catch (err) {
      setError(errMessage(err, "Lưu thất bại"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!skill} onOpenChange={(o) => !o && !saving && onClose()}>
      <DialogContent className="rounded-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl">Đổi tên / phạm vi</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="skill-rename-name" className={fieldLabelCls}>Tên kỹ năng</label>
            <Input
              id="skill-rename-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="vd: Soạn công văn"
              disabled={system || saving}
              title={system ? "Kỹ năng hệ thống giữ nguyên tên; hãy nhân bản nếu cần tên khác" : undefined}
              aria-invalid={!nameOk || undefined}
              className={cn("h-11", !nameOk && "border-destructive")}
            />
            {!nameOk && <p className="text-xs text-destructive">Tên chỉ gồm chữ, số, khoảng trắng, dấu - và _.</p>}
          </div>

          <div className="space-y-1.5">
            <span className={fieldLabelCls}>Phạm vi</span>
            <ScopeSelect
              value={scope}
              onChange={(v) => setScope(v)}
              disabled={saving}
              labels={{
                global: "Toàn hệ thống",
                department: "Phòng ban",
                globalItem: "Toàn hệ thống (mọi phòng ban)",
                departmentItem: "Một số phòng ban",
              }}
            />
          </div>

          {scope === "department" && (
            <div className="space-y-1.5">
              <span className={fieldLabelCls}>Phòng ban áp dụng</span>
              <DeptChecklist departments={departments} selected={deptIds} onChange={setDeptIds} disabled={saving} />
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>error</span>
              <span>{error}</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Hủy</Button>
          <Button onClick={save} disabled={saving || !nameOk}>
            {saving ? (
              <>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>progress_activity</span>
                Đang lưu...
              </>
            ) : (
              "Lưu"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
