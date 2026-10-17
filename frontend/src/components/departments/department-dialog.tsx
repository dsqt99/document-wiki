"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type EditableDepartment = { id: string; name: string; description?: string | null };

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  department: EditableDepartment | null;
  onSaved: () => void;
};

export function DepartmentDialog({ open, onOpenChange, department, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DepartmentForm
          key={department?.id ?? "new"}
          department={department}
          onCancel={() => onOpenChange(false)}
          onSaved={() => {
            onSaved();
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function DepartmentForm({
  department,
  onCancel,
  onSaved,
}: {
  department: EditableDepartment | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(department?.name ?? "");
  const [description, setDescription] = useState(department?.description ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = { name, description };
      if (department) await api(`/api/departments/${department.id}`, { method: "PUT", body });
      else await api("/api/departments", { method: "POST", body });
      onSaved();
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t("common.error"));
      setSaving(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
      <DialogTitle className="text-xl font-semibold">
        {department ? t("dept.editTitle") : t("dept.createTitle")}
      </DialogTitle>
      <div className="space-y-1.5">
        <Label htmlFor="dept-name">{t("dept.nameLabel")}</Label>
        <Input
          id="dept-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Sales, Engineering"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dept-desc">{t("dept.descLabel")}</Label>
        <Textarea
          id="dept-desc"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("type.descPlaceholder")}
        />
      </div>
      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
            error
          </span>
          <span>{error}</span>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? t("common.loading") : department ? t("common.save") : t("common.create")}
        </Button>
      </div>
    </form>
  );
}
