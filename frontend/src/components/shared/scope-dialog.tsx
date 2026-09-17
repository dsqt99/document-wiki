import React from "react";
import { useI18n } from "@/lib/i18n";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  employeeId: string;
};

/**
 * Scope dialog for managing personal access scopes.
 * Currently a placeholder — full implementation deferred to RBAC phase.
 */
export function ScopeDialog({ open, onOpenChange, label }: Props) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">lock</span>
            {t("scope.dialogTitle", `Personal Access — ${label}`).replace("{label}", label)}
          </DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <p className="text-sm text-muted-foreground">
            {t("scope.dialogPlaceholder", "Personal access scope management will be available in a future update.")}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
