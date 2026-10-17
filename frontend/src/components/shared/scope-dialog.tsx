"use client";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/lib/i18n";

type ScopeDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  /** Accepted for future use; the dialog is informational only for now. */
  employeeId: string;
};

/** Placeholder dialog for per-person access scopes (no API calls). */
export function ScopeDialog({ open, onOpenChange, label }: ScopeDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogTitle className="flex items-center gap-2 pr-8 text-lg font-semibold">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: 20 }}>
            lock
          </span>
          {t("scope.dialogTitle").replace("{label}", label)}
        </DialogTitle>
        <p className="text-sm text-muted-foreground">{t("scope.dialogPlaceholder")}</p>
      </DialogContent>
    </Dialog>
  );
}
