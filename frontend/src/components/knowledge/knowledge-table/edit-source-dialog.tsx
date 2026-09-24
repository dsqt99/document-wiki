import React from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Source, KnowledgeType, Department } from "./types";
import { useI18n } from "@/lib/i18n";

export function EditSourceDialog({
  source,
  types,
  departments,
  onClose,
  onSaved,
}: {
  source: Source;
  types: KnowledgeType[];
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = React.useState(source.title);
  const [typeId, setTypeId] = React.useState(source.knowledge_type_id || "");

  // Determine initial scope mode: 'department' or 'global'
  const initialMode = React.useMemo(() => {
    if (source.scope_type === "department" || (source.department_ids && source.department_ids.length > 0)) {
      return "department";
    }
    return "global";
  }, [source.scope_type, source.department_ids]);

  const [scopeMode, setScopeMode] = React.useState<"global" | "department">(initialMode);
  const [selectedDepts, setSelectedDepts] = React.useState<string[]>(source.department_ids || []);
  const originalDepts = React.useRef<string[]>(source.department_ids || []);

  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [pendingConfirm, setPendingConfirm] = React.useState(false);

  const toggleDept = (deptId: string) => {
    setSelectedDepts((prev) =>
      prev.includes(deptId) ? prev.filter((d) => d !== deptId) : [...prev, deptId]
    );
  };

  const scopeChanged = () => {
    if (scopeMode !== initialMode) return true;
    if (scopeMode === "department") {
      const orig = new Set(originalDepts.current);
      const cur = new Set(selectedDepts);
      return orig.size !== cur.size || selectedDepts.some((d) => !orig.has(d));
    }
    return false;
  };

  const doSave = async () => {
    if (scopeMode === "department" && selectedDepts.length === 0) {
      setError(t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban"));
      return;
    }

    setSaving(true);
    setError("");
    setPendingConfirm(false);
    try {
      const body: Record<string, unknown> = {
        title: title || undefined,
        knowledge_type_id: typeId || null,
        scope_type: scopeMode,
        scope_id: null,
        department_ids: scopeMode === "department" ? selectedDepts : [],
      };

      await api(`/api/sources/${source.id}`, { method: "PATCH", body });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () => {
    if (source.status === "ready" && scopeChanged()) {
      setPendingConfirm(true);
    } else {
      doSave();
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.edit.title", "Edit Document")}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 mt-2">
          {/* Document Title */}
          <div className="flex flex-col gap-1.5">
            <Label>{t("common.name", "Title")}</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="bg-background"
            />
          </div>

          {/* Knowledge Type */}
          <div className="flex flex-col gap-1.5">
            <Label>{t("knowledge.upload.typeLabel", "Knowledge Type")}</Label>
            <Select value={typeId} onValueChange={(v) => setTypeId(v ?? "")}>
              <SelectTrigger className="bg-background">
                {typeId ? (() => {
                  const item = types.find(x => x.id === typeId);
                  return item ? (
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                      <span>{item.name}</span>
                    </div>
                  ) : <SelectValue placeholder={t("knowledge.upload.none", "No type")} />;
                })() : <SelectValue placeholder={t("knowledge.upload.none", "No type")} />}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">{t("knowledge.upload.none", "No type")}</SelectItem>
                {types.map((typeItem) => (
                  <SelectItem key={typeItem.id} value={typeItem.id}>
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: typeItem.color }} />
                      {typeItem.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Unified Scope / Visibility Selector */}
          <div className="flex flex-col gap-1.5 pt-1 border-t">
            <Label className="font-semibold text-foreground flex items-center gap-1.5">
              <span className="material-symbols-outlined text-base">visibility</span>
              {t("knowledge.upload.visibility", "Phạm vi hiển thị")}
            </Label>
            <p className="text-xs text-muted-foreground">
              {t("knowledge.edit.scopeHint", "Chọn phạm vi hiển thị và quyền truy cập của tài liệu.")}
            </p>

            <Select
              value={scopeMode}
              onValueChange={(val) => {
                const mode = (val || "global") as "global" | "department";
                setScopeMode(mode);
                if (mode === "global") {
                  setSelectedDepts([]);
                }
              }}
            >
              <SelectTrigger className="bg-background font-medium">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-base text-primary">
                    {scopeMode === "global" ? "public" : "apartment"}
                  </span>
                  <span>
                    {scopeMode === "global"
                      ? t("knowledge.scope.global", "Toàn hệ thống")
                      : t("knowledge.scope.department", "Theo phòng ban")}
                  </span>
                </div>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-base">public</span>
                    <div>
                      <div className="font-medium">{t("knowledge.scope.global", "Toàn hệ thống")}</div>
                      <div className="text-xs text-muted-foreground">Hiển thị cho tất cả cán bộ trong hệ thống</div>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="department">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-base">apartment</span>
                    <div>
                      <div className="font-medium">{t("knowledge.scope.department", "Theo phòng ban")}</div>
                      <div className="text-xs text-muted-foreground">Giới hạn trong các phòng ban được chọn</div>
                    </div>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Conditional Sub-selector: Global Notice */}
          {scopeMode === "global" && (
            <div className="rounded-lg border border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20 px-3 py-2 text-xs text-blue-800 dark:text-blue-300 flex items-start gap-1.5">
              <span className="material-symbols-outlined shrink-0 text-blue-600 dark:text-blue-400" style={{ fontSize: 16 }}>public</span>
              <span>{t("knowledge.upload.globalNotice", "Nội dung tài liệu sẽ được biên soạn vào wiki chung và hiển thị cho tất cả nhân sự.")}</span>
            </div>
          )}

          {/* Conditional Sub-selector: Department Checklist */}
          {scopeMode === "department" && (
            <div className="flex flex-col gap-1.5 bg-muted/30 p-3 rounded-lg border">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">{t("knowledge.upload.departments", "Chọn phòng ban được truy cập:")}</Label>
                <span className="text-xs text-muted-foreground">Đã chọn {selectedDepts.length}</span>
              </div>
              <div className="border rounded-lg p-2 max-h-40 overflow-y-auto bg-background">
                {departments.length === 0 ? (
                  <span className="text-xs text-muted-foreground">{t("dept.noDepts", "Chưa có phòng ban")}</span>
                ) : (
                  departments.map((d) => (
                    <label
                      key={d.id}
                      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted cursor-pointer transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={selectedDepts.includes(d.id)}
                        onChange={() => toggleDept(d.id)}
                        className="rounded border-border"
                      />
                      <span className="text-sm">{d.name}</span>
                    </label>
                  ))
                )}
              </div>
              {selectedDepts.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {selectedDepts.map((id) => {
                    const name = departments.find((d) => d.id === id)?.name ?? id;
                    return (
                      <span
                        key={id}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary border border-primary/20"
                      >
                        {name}
                        <button
                          type="button"
                          onClick={() => toggleDept(id)}
                          className="hover:text-destructive font-bold ml-0.5"
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Scope change confirmation notice */}
          {pendingConfirm && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30 p-3 flex flex-col gap-2.5">
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined text-amber-600 dark:text-amber-400 shrink-0 text-base mt-0.5">warning</span>
                <p className="text-xs text-amber-800 dark:text-amber-300">
                  {t(
                    "knowledge.edit.scopeChangeConfirm",
                    "Việc thay đổi phạm vi hiển thị sẽ kích hoạt biên soạn lại tri thức bằng AI. Bạn có muốn tiếp tục?"
                  )}
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setPendingConfirm(false)}>
                  {t("common.cancel", "Hủy")}
                </Button>
                <Button size="sm" onClick={doSave} className="bg-amber-600 hover:bg-amber-700 text-white">
                  {t("common.confirm", "Xác nhận")}
                </Button>
              </div>
            </div>
          )}

          {/* Error display */}
          {error && (
            <p className="text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-1.5">
              <span className="material-symbols-outlined text-base">error</span>
              {error}
            </p>
          )}

          {/* Footer Actions */}
          <div className="flex justify-end gap-2 mt-2 pt-2 border-t">
            <Button variant="outline" onClick={onClose}>{t("common.cancel", "Hủy")}</Button>
            <Button
              disabled={saving || pendingConfirm}
              onClick={handleSave}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {saving ? (
                <span className="flex items-center gap-2">
                  <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                  {t("common.loading", "Đang lưu...")}
                </span>
              ) : t("common.save", "Lưu thay đổi")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
