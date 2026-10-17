"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { DeptChecklist, fieldLabelCls } from "./dept-checklist";
import { ScopeSelect, type GlobalOrDept } from "./scope-select";
import type { Department } from "./types";

/** Names the server reports as already present (409 with `detail.conflicts`). */
function conflictsOf(err: unknown): string[] | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const data = err.data as { detail?: { conflicts?: unknown } } | null;
  const list = data?.detail?.conflicts;
  return Array.isArray(list) ? list.map(String) : null;
}

/** "Tải gói ZIP": trigger button plus the multi-file skill package upload form. */
export function SkillUploadDialog({
  departments,
  onUploaded,
}: {
  departments: Department[];
  onUploaded: () => void;
}) {
  const { t } = useI18n();
  const { canAccess } = useAuth();
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [scope, setScope] = useState<GlobalOrDept>("global");
  const [deptIds, setDeptIds] = useState<string[]>([]);
  const [force, setForce] = useState(false);
  const [conflicts, setConflicts] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  if (!canAccess("skill", "create")) return null;

  const reset = () => {
    setFiles([]);
    setScope("global");
    setDeptIds([]);
    setForce(false);
    setConflicts(null);
    setInputKey((k) => k + 1);
  };

  const changeOpen = (o: boolean) => {
    if (busy) return;
    setOpen(o);
    if (!o) reset();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || files.length === 0 || (conflicts && !force)) return;
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("scope_type", scope);
    if (scope === "department" && deptIds.length) {
      deptIds.forEach((id) => fd.append("department_ids", id));
      fd.append("scope_id", deptIds[0]);
    }
    if (force) fd.append("force", "true");
    setBusy(true);
    try {
      await apiUpload("/api/skills/upload", fd);
      onUploaded();
      setOpen(false);
      reset();
    } catch (err) {
      const names = conflictsOf(err);
      if (names) {
        setConflicts(names);
        setForce(false);
      } else {
        alert(err instanceof Error && err.message ? err.message : t("common.error", "Lỗi"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger
        render={<Button variant="outline" size="sm" title="Tải lên gói kỹ năng dạng ZIP" />}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>upload</span>
        Tải gói ZIP
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl">{t("skills.uploadSkill", "Tải lên kỹ năng")}</DialogTitle>
            <DialogDescription>{t("knowledge.upload.subtitle", "")}</DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <label htmlFor="skill-zip-files" className={fieldLabelCls}>{t("skills.selectZip", "Chọn tệp ZIP")}</label>
            <input
              key={inputKey}
              id="skill-zip-files"
              type="file"
              accept=".zip"
              multiple
              disabled={busy}
              onChange={(e) => {
                setFiles(Array.from(e.target.files ?? []));
                setConflicts(null);
                setForce(false);
              }}
              className="block w-full cursor-pointer rounded-xl border-2 border-dashed border-border px-4 py-8 text-sm text-muted-foreground transition-colors hover:border-primary file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium"
            />
            {files.length > 0 && (
              <p className="text-xs font-medium text-primary">
                {files.length} {t("knowledge.upload.files", "tệp")}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <span className={fieldLabelCls}>{t("knowledge.colVisibility", "Phạm vi")}</span>
            <ScopeSelect
              value={scope}
              onChange={(v) => {
                setScope(v);
                setDeptIds([]);
              }}
              disabled={busy}
              labels={{ global: t("scope.global", "Toàn hệ thống"), department: t("scope.department", "Phòng ban") }}
            />
          </div>

          {scope === "department" && (
            <div className="space-y-1.5">
              <span className={fieldLabelCls}>Target Departments</span>
              <DeptChecklist departments={departments} selected={deptIds} onChange={setDeptIds} disabled={busy} />
            </div>
          )}

          {conflicts && (
            <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm">
              <p className="flex items-center gap-1.5 font-semibold text-destructive">
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>warning</span>
                Duplicate names detected
              </p>
              <p className="text-xs">Existing skills: {conflicts.join(", ")}. Overwrite them?</p>
              <label className="flex cursor-pointer items-center gap-2 text-xs font-medium">
                <Checkbox checked={force} onCheckedChange={(v) => setForce(v)} disabled={busy} />
                I confirm to overwrite
              </label>
            </div>
          )}

          <DialogFooter>
            <Button type="submit" disabled={busy || files.length === 0 || (!!conflicts && !force)}>
              {busy ? "Processing..." : "Start Upload"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
