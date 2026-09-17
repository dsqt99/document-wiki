import { useState } from "react";
import { apiUpload, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";

type UploadSkillDialogProps = {
  allDepartments: { id: string; name: string }[];
  onUploaded: () => void;
};

export function UploadSkillDialog({ allDepartments, onUploaded }: UploadSkillDialogProps) {
  const { t } = useI18n();
  const { canAccess } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [uploadLoading, setUploadLoading] = useState(false);

  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [scopeType, setScopeType] = useState("global");
  const [deptIds, setDeptIds] = useState<string[]>([]);
  const [force, setForce] = useState(false);
  const [conflictFiles, setConflictFiles] = useState<string[]>([]);

  const resetForm = () => {
    setSelectedFiles(null);
    setScopeType("global");
    setDeptIds([]);
    setForce(false);
    setConflictFiles([]);
  };

  const handleUpload = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedFiles || selectedFiles.length === 0) return;

    try {
      setUploadLoading(true);
      const formData = new FormData();
      for (let i = 0; i < selectedFiles.length; i++) {
        formData.append("files", selectedFiles[i]);
      }
      formData.append("scope_type", scopeType);
      
      if (scopeType === "department" && deptIds.length > 0) {
        deptIds.forEach(id => {
          formData.append("department_ids", id);
        });
        formData.append("scope_id", deptIds[0]); // Legacy support
      }

      if (force) {
        formData.append("force", "true");
      }

      await apiUpload("/api/skills/upload", formData);
      onUploaded();
      setIsOpen(false);
      resetForm();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const data = err.data as { detail?: { conflicts?: string[] } } | undefined;
        setConflictFiles(data?.detail?.conflicts || []);
      } else {
        alert(err instanceof Error ? err.message : t("common.error", "Upload failed"));
      }
    } finally {
      setUploadLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      setIsOpen(open);
      if (!open) resetForm();
    }}>
      {(canAccess("skill", "create") ) && (
        <DialogTrigger
          render={
            <Button className="bg-primary text-primary-foreground hover:bg-primary/90 shadow-sahara">
              <span className="material-symbols-outlined text-base mr-1">upload</span>
              {t("skills.uploadBtn", "Upload Skill")}
            </Button>
          }
        />
      )}
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleUpload}>
          <DialogHeader>
            <DialogTitle className="text-xl font-heading">{t("skills.uploadSkill", "Upload AI Skill")}</DialogTitle>
            <DialogDescription className="font-manrope">
              {t("knowledge.upload.subtitle", "Select one or more ZIP packages containing AI skills.")}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-6 py-6">
            <div className="grid gap-2">
              <Label htmlFor="files">{t("skills.selectZip", "Skill Packages (ZIP)")}</Label>
              <Input
                id="files"
                type="file"
                accept=".zip"
                multiple
                onChange={(e) => setSelectedFiles(e.target.files)}
                className="cursor-pointer bg-secondary/5 border-dashed border-2 hover:border-primary/50 transition-all py-8 h-auto"
              />
              {selectedFiles && selectedFiles.length > 0 && (
                <p className="text-[11px] text-primary font-medium animate-in fade-in">
                  {selectedFiles.length} {t("knowledge.upload.files", "file(s) selected")}
                </p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>{t("knowledge.colVisibility", "Visibility")}</Label>
              <Select value={scopeType} onValueChange={(v) => {
                setScopeType(v || "global");
                setDeptIds([]);
              }}>
                <SelectTrigger className="bg-secondary/5 h-11">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-base text-muted-foreground">
                      {scopeType === "global" ? "public" : "corporate_fare"}
                    </span>
                    <span className="capitalize">
                      {scopeType === "global" ? t("scope.global", "Global") : t("scope.department", "Department")}
                    </span>
                  </div>
                </SelectTrigger>
                <SelectContent className="min-w-[240px]">
                  <SelectItem value="global">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-base text-muted-foreground">public</span>
                      {t("scope.global", "Global (All Departments)")}
                    </div>
                  </SelectItem>
                  <SelectItem value="department">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-base text-muted-foreground">corporate_fare</span>
                      {t("scope.department", "Specific Departments")}
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {scopeType === "department" && (
              <div className="grid gap-2 animate-in fade-in slide-in-from-top-1">
                <Label>Target Departments</Label>
                <div className="bg-secondary/5 rounded-xl border border-border p-3">
                  <div className="max-h-[200px] pr-4 overflow-y-auto custom-scrollbar">
                    <div className="grid grid-cols-1 gap-2">
                      {allDepartments.map((d) => (
                        <div key={d.id} className="flex items-center space-x-2 group/item">
                          <Checkbox 
                            id={`upload-dept-${d.id}`} 
                            checked={deptIds.includes(d.id)}
                            onCheckedChange={(checked) => {
                              if (checked) {
                                setDeptIds([...deptIds, d.id]);
                              } else {
                                setDeptIds(deptIds.filter(id => id !== d.id));
                              }
                            }}
                          />
                          <label
                            htmlFor={`upload-dept-${d.id}`}
                            className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer group-hover/item:text-primary transition-colors"
                          >
                            {d.name}
                          </label>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
            
              </div>
            )}


            {conflictFiles.length > 0 && (
              <div className="bg-destructive/5 border border-destructive/20 p-4 rounded-lg flex flex-col gap-2">
                <div className="flex items-center gap-2 text-destructive font-semibold text-sm">
                  <span className="material-symbols-outlined text-lg">warning</span>
                  Duplicate names detected
                </div>
                <p className="text-xs text-muted-foreground">
                  Existing skills: {conflictFiles.join(", ")}. Overwrite them?
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <input
                    type="checkbox"
                    id="force-check"
                    checked={force}
                    onChange={(e) => setForce(e.target.checked)}
                    className="w-4 h-4 cursor-pointer"
                  />
                  <Label htmlFor="force-check" className="text-xs cursor-pointer">I confirm to overwrite</Label>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={uploadLoading || !selectedFiles || (conflictFiles.length > 0 && !force)}>
              {uploadLoading ? "Processing..." : "Start Upload"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
