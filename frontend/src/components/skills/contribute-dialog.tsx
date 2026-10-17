"use client";

import { useEffect, useState, type FormEvent, type ReactElement } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DeptChecklist, fieldLabelCls } from "./dept-checklist";
import { ScopeSelect, type GlobalOrDept } from "./scope-select";
import { errMessage, isValidDisplayName } from "./skill-utils";
import type { Department, Skill, SkillListResponse } from "./types";

type Props = {
  /** Present → improve an existing skill (fork). Absent → propose a brand new one. */
  skillId?: string;
  skillName?: string;
  versions?: { version_number: number }[];
  onContributionCreated: (id: string) => void;
  /** Custom trigger element (rendered through DialogTrigger). */
  trigger?: ReactElement;
  allDepartments?: Department[];
  /** Controlled open state (optional; the dialog manages its own state otherwise). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export function ContributeDialog({
  skillId,
  skillName,
  versions,
  onContributionCreated,
  trigger,
  allDepartments,
  open: openProp,
  onOpenChange,
}: Props) {
  const { canAccess } = useAuth();
  const isFork = !!skillId;
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = (o: boolean) => {
    if (openProp === undefined) setOpenState(o);
    onOpenChange?.(o);
  };

  const [title, setTitle] = useState("");
  const [scope, setScope] = useState<GlobalOrDept>("global");
  const [deptIds, setDeptIds] = useState<string[]>([]);
  // Default base version = first entry at the time the dialog is built (may be empty).
  const [baseVersion, setBaseVersion] = useState<string | null>(
    versions && versions.length ? String(versions[0].version_number) : null,
  );
  const [busy, setBusy] = useState(false);
  const [duplicate, setDuplicate] = useState<Skill | null>(null);
  const [fetchedDepts, setFetchedDepts] = useState<Department[]>([]);

  const needDepts = !isFork && !allDepartments;
  useEffect(() => {
    if (!needDepts || !open) return;
    let alive = true;
    api<Department[]>("/api/departments")
      .then((d) => alive && setFetchedDepts(Array.isArray(d) ? d : []))
      .catch(() => alive && setFetchedDepts([]));
    return () => {
      alive = false;
    };
  }, [needDepts, open]);

  if (!canAccess("skill", "create")) return null;

  const departments = allDepartments ?? fetchedDepts;
  const titleOk = isFork || isValidDisplayName(title);
  const titleInvalid = !isFork && title.length > 0 && !isValidDisplayName(title);
  const canSubmit = !busy && titleOk && (isFork || scope !== "department" || deptIds.length > 0);

  const create = async (targetSkillId: string | null, base: number | null) => {
    setBusy(true);
    try {
      const res = await api<{ id: string }>("/api/skill-contributions", {
        method: "POST",
        body: {
          skill_id: targetSkillId,
          base_version: base,
          title: isFork ? `Improve ${skillName ?? ""}` : title,
          scope_type: targetSkillId ? "global" : scope,
          scope_ids: targetSkillId ? null : scope === "department" ? deptIds : [],
        },
      });
      setDuplicate(null);
      setOpen(false);
      onContributionCreated(res.id);
    } catch (err) {
      alert(errMessage(err, "Failed to create contribution"));
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    if (!isFork) {
      try {
        const q = encodeURIComponent(title.trim());
        const res = await api<SkillListResponse>(`/api/skills?q=${q}&limit=1`);
        const hit = res?.items?.find((s) => s.name.toLowerCase() === title.trim().toLowerCase());
        if (hit) {
          setDuplicate(hit);
          return;
        }
      } catch {
        // duplicate check is best effort
      }
    }
    await create(skillId ?? null, isFork && baseVersion ? Number(baseVersion) : null);
  };

  const defaultTrigger = (
    <Button variant="outline" className="text-primary hover:text-primary" />
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (busy) return;
        setOpen(o);
        if (!o) setDuplicate(null);
      }}
    >
      {trigger ? (
        <DialogTrigger render={trigger} />
      ) : (
        <DialogTrigger render={defaultTrigger}>
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>edit_square</span>
          Contribute
        </DialogTrigger>
      )}
      <DialogContent className="overflow-hidden sm:max-w-[500px]">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle className="font-serif text-xl">
              {isFork ? `Contribute to ${skillName ?? ""}` : "Create New Skill"}
            </DialogTitle>
            <DialogDescription>
              {isFork ? "Propose changes to improve this skill." : "Propose a brand new skill to the Document Wiki platform."}
            </DialogDescription>
          </DialogHeader>

          {!isFork && (
            <>
              <div className="space-y-1.5">
                <label htmlFor="contrib-title" className={fieldLabelCls}>Title</label>
                <Input
                  id="contrib-title"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. SRS-writing-skill"
                  disabled={busy}
                  aria-invalid={titleInvalid || undefined}
                  className={cn("h-11", titleInvalid && "border-destructive")}
                />
                {titleInvalid && (
                  <p className="text-xs text-destructive">
                    Title contains invalid characters. Use only letters, numbers, spaces, - and _.
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <span className={fieldLabelCls}>Visibility</span>
                <ScopeSelect
                  value={scope}
                  onChange={(v) => {
                    setScope(v);
                    setDeptIds([]);
                  }}
                  disabled={busy}
                  labels={{
                    global: "Global",
                    department: "Department",
                    globalItem: "Global (All Departments)",
                    departmentItem: "Specific Departments",
                  }}
                />
              </div>
              {scope === "department" && (
                <div className="space-y-1.5">
                  <span className={fieldLabelCls}>Target Departments</span>
                  <DeptChecklist
                    departments={departments}
                    selected={deptIds}
                    onChange={setDeptIds}
                    maxHeight={160}
                    disabled={busy}
                  />
                </div>
              )}
            </>
          )}

          {isFork && versions && versions.length > 0 && (
            <div className="space-y-1.5">
              <span className={fieldLabelCls}>Base Version</span>
              <Select value={baseVersion} onValueChange={(v) => setBaseVersion(v as string | null)} disabled={busy}>
                <SelectTrigger className="h-11! w-full">
                  <SelectValue placeholder="Select version">
                    {(v: string | null) => (v ? `Version ${v}` : "Select version")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {versions.map((v) => (
                    <SelectItem key={v.version_number} value={String(v.version_number)}>
                      Version {v.version_number}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <DialogFooter>
            <Button type="submit" disabled={!canSubmit} className="w-full sm:w-auto">
              {busy ? "Initializing..." : isFork ? "Start Improving" : "Start Creating"}
            </Button>
          </DialogFooter>
        </form>

        {duplicate && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
            <div className="w-full max-w-[400px] space-y-4 rounded-2xl border bg-card p-6 text-center shadow-xl">
              <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-amber-500/10 text-amber-600">
                <span className="material-symbols-outlined" style={{ fontSize: 28 }}>warning</span>
              </div>
              <h3 className="font-serif text-xl font-bold italic">Skill Already Exists</h3>
              <p className="text-sm text-muted-foreground">
                A skill named <strong className="text-foreground">&quot;{duplicate.name}&quot;</strong> already exists.
                Would you like to contribute to the existing skill instead?
              </p>
              <div className="flex flex-col gap-2">
                <Button disabled={busy} onClick={() => void create(duplicate.id, null)}>
                  Yes, contribute to existing
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => setDuplicate(null)}>
                  No, I&apos;ll change the name
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
