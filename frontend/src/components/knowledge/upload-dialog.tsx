"use client";

import { useState, useRef, useCallback } from "react";
import { apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
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
import { useI18n } from "@/lib/i18n";

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
};

type Department = {
  id: string;
  name: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  types: KnowledgeType[];
  departments: Department[];
  onUploaded: () => void;
};

const ACCEPTED_EXTENSIONS = ["pdf", "docx", "xlsx", "xls", "csv", "txt", "md", "pptx"];
const ACCEPT_STRING = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(",");

function getFileExtension(name: string): string {
  return (name.split(".").pop() || "").toLowerCase();
}

function getFileIcon(ext: string): { icon: string; color: string } {
  switch (ext) {
    case "pdf":
      return { icon: "picture_as_pdf", color: "text-rose-500 bg-rose-500/10" };
    case "docx":
      return { icon: "description", color: "text-blue-500 bg-blue-500/10" };
    case "xlsx":
    case "xls":
    case "csv":
      return { icon: "table_chart", color: "text-emerald-500 bg-emerald-500/10" };
    case "pptx":
    case "ppt":
      return { icon: "slideshow", color: "text-amber-500 bg-amber-500/10" };
    case "md":
    case "txt":
      return { icon: "article", color: "text-slate-500 bg-slate-500/10" };
    default:
      return { icon: "draft", color: "text-primary bg-primary/10" };
  }
}

function validateFile(f: File): string | null {
  const ext = getFileExtension(f.name);
  if (ext === "doc") {
    return `"${f.name}": Định dạng file .doc cũ không được hỗ trợ. Vui lòng chuyển đổi sang .docx hoặc .pdf trước khi tải lên.`;
  }
  if (!ext || !ACCEPTED_EXTENSIONS.includes(ext)) {
    return `"${f.name}": Đuôi file ".${ext || "không rõ"}" không được hỗ trợ. Chỉ chấp nhận: ${ACCEPTED_EXTENSIONS.join(", ").toUpperCase()}`;
  }
  if (f.size > 50 * 1024 * 1024) {
    return `"${f.name}": Dung lượng file vượt quá giới hạn 50 MB.`;
  }
  return null;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadDialog({ open, onOpenChange, types, departments, onUploaded }: Props) {
  const { t } = useI18n();
  const [files, setFiles] = useState<File[]>([]);
  const [selectedTypeId, setSelectedTypeId] = useState<string | null>(null);
  const defaultTypeId = types.find((t) => t.slug === "general")?.id || "";
  const typeId = selectedTypeId !== null ? selectedTypeId : defaultTypeId;
  const [selectedDepts, setSelectedDepts] = useState<string[]>([]);
  const [scopeType, setScopeType] = useState<"global" | "department">("global");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string>("");
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [isDragInvalid, setIsDragInvalid] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const toggleDept = (deptId: string) => {
    setSelectedDepts((prev) =>
      prev.includes(deptId) ? prev.filter((d) => d !== deptId) : [...prev, deptId]
    );
  };

  const addFiles = useCallback((incoming: File[]) => {
    if (!incoming.length) return;
    const errors: string[] = [];
    const valid: File[] = [];

    incoming.forEach((f) => {
      const err = validateFile(f);
      if (err) {
        errors.push(err);
      } else {
        valid.push(f);
      }
    });

    if (errors.length > 0) {
      setError(errors.slice(0, 2).join("; ") + (errors.length > 2 ? ` (+${errors.length - 2} more)` : ""));
    } else {
      setError("");
    }

    if (valid.length > 0) {
      setFiles((prev) => {
        const existingKeys = new Set(prev.map((f) => `${f.name}_${f.size}`));
        const filtered = valid.filter((f) => !existingKeys.has(`${f.name}_${f.size}`));
        return [...prev, ...filtered];
      });
    }
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      setIsDragInvalid(false);
      const droppedFiles = Array.from(e.dataTransfer.files || []);
      if (droppedFiles.length) addFiles(droppedFiles);
    },
    [addFiles]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
    if (e.dataTransfer.items) {
      for (let i = 0; i < e.dataTransfer.items.length; i++) {
        const item = e.dataTransfer.items[i];
        if (item.kind === "file" && (item.type === "application/msword" || item.type === "")) {
          setIsDragInvalid(true);
          return;
        }
      }
    }
    setIsDragInvalid(false);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    setIsDragInvalid(false);
  }, []);

  const handleUpload = async () => {
    if (files.length === 0) return;
    if (scopeType === "department" && selectedDepts.length === 0) {
      setError(t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban"));
      return;
    }

    setUploading(true);
    setError("");
    let successCount = 0;
    const failedNames: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      setUploadProgress(`Uploading ${i + 1}/${files.length}: ${f.name}`);

      try {
        const formData = new FormData();
        formData.append("file", f);
        if (typeId) formData.append("knowledge_type_id", typeId);

        if (scopeType === "department" && selectedDepts.length > 0) {
          formData.append("department_ids", selectedDepts.join(","));
        }
        formData.append("scope_type", scopeType);

        await apiUpload("/api/sources/upload", formData);
        successCount++;
      } catch {
        failedNames.push(f.name);
      }
    }

    setUploading(false);
    setUploadProgress("");

    if (failedNames.length === 0) {
      onUploaded();
      onOpenChange(false);
      setFiles([]);
      setSelectedTypeId(null);
      setSelectedDepts([]);
      setScopeType("global");
    } else {
      if (successCount > 0) {
        onUploaded();
      }
      setFiles((prev) => prev.filter((f) => failedNames.includes(f.name)));
      setError(`Uploaded ${successCount}/${files.length} file(s). Failed: ${failedNames.join(", ")}`);
    }
  };

  const totalBytes = files.reduce((acc, f) => acc + f.size, 0);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!uploading) onOpenChange(o); }}>
      <DialogContent className="sm:max-w-xl max-h-[88vh] flex flex-col p-0 overflow-hidden gap-0">
        {/* Fixed Header */}
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60 shrink-0 pr-12">
          <DialogTitle className="text-xl font-heading font-semibold text-foreground">
            {t("knowledge.upload.title", "Tải lên tài liệu")}
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t("knowledge.upload.subtitle", "Tải lên một hoặc nhiều tài liệu vào cơ sở tri thức")}
          </p>
        </DialogHeader>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-4">
          {/* File input & Dropzone */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT_STRING}
            onChange={(e) => {
              const selected = Array.from(e.target.files || []);
              if (selected.length) addFiles(selected);
              e.target.value = "";
            }}
            className="hidden"
          />

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium">{t("knowledge.upload.files", "Tập tin")}</Label>
              {files.length > 0 && (
                <span className="text-xs text-muted-foreground">
                  {files.length} file{files.length > 1 ? "s" : ""} · {formatFileSize(totalBytes)}
                </span>
              )}
            </div>

            {files.length === 0 ? (
              /* Empty dropzone */
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={`
                  relative flex flex-col items-center justify-center gap-2 px-4 py-8
                  rounded-xl border-2 border-dashed cursor-pointer transition-all duration-200
                  ${isDragInvalid
                    ? "border-destructive bg-destructive/5 scale-[1.01]"
                    : dragOver
                    ? "border-primary bg-primary/5 scale-[1.01]"
                    : "border-border hover:border-primary/40 hover:bg-accent/30"
                  }
                `}
              >
                <div className={`w-11 h-11 rounded-full flex items-center justify-center transition-colors ${
                  isDragInvalid ? "bg-destructive/15" : dragOver ? "bg-primary/15" : "bg-accent/70"
                }`}>
                  <span className={`material-symbols-outlined transition-colors ${
                    isDragInvalid ? "text-destructive" : dragOver ? "text-primary" : "text-muted-foreground"
                  }`} style={{ fontSize: 24 }}>
                    {isDragInvalid ? "block" : "upload_file"}
                  </span>
                </div>
                <div className="text-center">
                  <p className={`text-sm font-medium ${isDragInvalid ? "text-destructive" : "text-foreground"}`}>
                    {isDragInvalid
                      ? t("knowledge.upload.dropzoneInvalid", "Định dạng file không được hỗ trợ!")
                      : dragOver
                      ? t("knowledge.upload.dropzoneActive", "Thả tài liệu vào đây")
                      : t("knowledge.upload.dropzone", "Kéo thả tài liệu vào đây hoặc nhấp để duyệt")}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {t("knowledge.upload.hint", "Chấp nhận: PDF, DOCX, XLSX, CSV, TXT, MD, PPTX (tối đa 50 MB)")}
                  </p>
                </div>
              </div>
            ) : (
              /* Selected files list + Add more button */
              <div className="flex flex-col gap-2">
                <div className="border rounded-xl bg-background/50 divide-y divide-border/60 max-h-48 overflow-y-auto">
                  {files.map((f, idx) => {
                    const ext = getFileExtension(f.name);
                    const iconInfo = getFileIcon(ext);
                    return (
                      <div
                        key={`${f.name}_${f.size}_${idx}`}
                        className="flex items-center gap-3 px-3 py-2 hover:bg-accent/20 transition-colors"
                      >
                        <div className={`w-8 h-8 rounded-lg ${iconInfo.color} flex items-center justify-center shrink-0`}>
                          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                            {iconInfo.icon}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-foreground truncate" title={f.name}>
                            {f.name}
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            {formatFileSize(f.size)} · .{ext.toUpperCase()}
                          </p>
                        </div>
                        {!uploading && (
                          <button
                            type="button"
                            onClick={() => removeFile(idx)}
                            className="p-1 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                            title="Xóa tài liệu"
                          >
                            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>

                {!uploading && (
                  <div className="flex items-center justify-between pt-1">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                      className="text-xs h-8 gap-1.5"
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: 15 }}>add</span>
                      {t("knowledge.upload.addMore", "Thêm tài liệu")}
                    </Button>
                    <button
                      type="button"
                      onClick={() => setFiles([])}
                      className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                    >
                      {t("knowledge.upload.clearAll", "Xóa tất cả")}
                    </button>
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="text-destructive text-xs bg-destructive/10 border border-destructive/20 px-3.5 py-2.5 rounded-xl flex items-start gap-2.5 animate-in fade-in-50">
                <span className="material-symbols-outlined shrink-0 text-destructive mt-0.5" style={{ fontSize: 16 }}>error</span>
                <span className="font-medium leading-relaxed">{error}</span>
              </div>
            )}
          </div>

          {/* Knowledge Type */}
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs font-medium">{t("knowledge.upload.typeLabel", "Phân loại tri thức")}</Label>
            <Select value={typeId} onValueChange={(v) => setSelectedTypeId(v ?? "")}>
              <SelectTrigger className="bg-background w-full h-9 text-xs">
                {typeId ? (() => {
                  const item = types.find((x) => x.id === typeId);
                  return item ? (
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                      <span>{item.name}</span>
                    </div>
                  ) : <SelectValue placeholder={t("knowledge.upload.typePlaceholder", "Chọn phân loại (tùy chọn)")} />;
                })() : <SelectValue placeholder={t("knowledge.upload.typePlaceholder", "Chọn phân loại (tùy chọn)")} />}
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">{t("knowledge.upload.none", "Không chọn")}</SelectItem>
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

          {/* Visibility / Scope Selector */}
          <div className="flex flex-col gap-1.5 pt-1 border-t border-border/40">
            <Label className="text-xs font-medium flex items-center gap-1.5">
              <span className="material-symbols-outlined text-sm">visibility</span>
              {t("knowledge.upload.visibility", "Phạm vi hiển thị")}
            </Label>
            <p className="text-[11px] text-muted-foreground">
              {t("knowledge.edit.scopeHint", "Chọn phạm vi hiển thị và quyền truy cập của tài liệu.")}
            </p>

            <Select
              value={scopeType}
              onValueChange={(val) => {
                const mode = (val || "global") as "global" | "department";
                setScopeType(mode);
                if (mode === "global") {
                  setSelectedDepts([]);
                }
              }}
            >
              <SelectTrigger className="bg-background w-full h-9 text-xs">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-primary" style={{ fontSize: 15 }}>
                    {scopeType === "global" ? "public" : "apartment"}
                  </span>
                  <span className="font-medium">
                    {scopeType === "global"
                      ? t("knowledge.scope.global", "Toàn hệ thống")
                      : t("knowledge.scope.department", "Theo phòng ban")}
                  </span>
                </div>
              </SelectTrigger>
              <SelectContent className="min-w-[220px]">
                <SelectItem value="global">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>public</span>
                    <div>
                      <div className="font-medium">{t("knowledge.scope.global", "Toàn hệ thống")}</div>
                      <div className="text-[10px] text-muted-foreground">Hiển thị cho tất cả cán bộ trong hệ thống</div>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="department">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="material-symbols-outlined" style={{ fontSize: 14 }}>apartment</span>
                    <div>
                      <div className="font-medium">{t("knowledge.scope.department", "Theo phòng ban")}</div>
                      <div className="text-[10px] text-muted-foreground">Giới hạn trong các phòng ban được chọn</div>
                    </div>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>

            {scopeType === "global" && (
              <p className="text-[11px] text-blue-700 dark:text-blue-300 bg-blue-50/60 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900 rounded-lg p-2.5 flex items-start gap-1.5 mt-0.5">
                <span className="material-symbols-outlined shrink-0 text-blue-600 dark:text-blue-400" style={{ fontSize: 14, marginTop: 1 }}>public</span>
                <span>{t("knowledge.upload.globalNotice", "Nội dung tài liệu sẽ được biên soạn vào wiki chung và hiển thị cho tất cả nhân sự.")}</span>
              </p>
            )}

            {scopeType === "department" && (
              <div className="flex flex-col gap-1.5 bg-muted/30 p-2.5 rounded-lg border mt-1">
                <div className="flex items-center justify-between">
                  <Label className="text-xs font-medium">{t("knowledge.upload.departments", "Chọn phòng ban được truy cập:")}</Label>
                  <span className="text-[11px] text-muted-foreground">Đã chọn {selectedDepts.length}</span>
                </div>
                <div className="border rounded-lg p-2 max-h-32 overflow-y-auto bg-background divide-y divide-border/40">
                  {departments.length === 0 ? (
                    <span className="text-xs text-muted-foreground px-1">{t("dept.noDepts", "Chưa có phòng ban")}</span>
                  ) : (
                    departments.map((d) => (
                      <label
                        key={d.id}
                        className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-muted/50 cursor-pointer text-xs"
                      >
                        <input
                          type="checkbox"
                          checked={selectedDepts.includes(d.id)}
                          onChange={() => toggleDept(d.id)}
                          className="rounded border-border"
                        />
                        <span>{d.name}</span>
                      </label>
                    ))
                  )}
                </div>
                {selectedDepts.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {selectedDepts.map((id) => {
                      const name = departments.find((d) => d.id === id)?.name ?? id;
                      return (
                        <span
                          key={id}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-primary/10 text-primary border border-primary/20"
                        >
                          {name}
                          <button type="button" onClick={() => toggleDept(id)} className="hover:text-destructive font-bold ml-0.5">×</button>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Fixed Pinned Footer */}
        <div className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0 flex items-center justify-between">
          <div className="text-xs text-muted-foreground truncate max-w-[200px]">
            {uploading ? (
              <span className="text-primary font-medium">{uploadProgress}</span>
            ) : files.length > 0 ? (
              `${files.length} ${t("knowledge.upload.files", "tập tin")}`
            ) : (
              t("knowledge.upload.noFiles", "Chưa chọn tài liệu")
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={uploading}
              className="text-xs h-8"
            >
              {t("common.cancel", "Hủy")}
            </Button>
            <Button
              size="sm"
              disabled={files.length === 0 || uploading}
              onClick={handleUpload}
              className="bg-primary text-primary-foreground hover:bg-primary/90 text-xs h-8 gap-1.5"
            >
              {uploading ? (
                <>
                  <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                  <span>{t("knowledge.upload.uploading", "Đang tải lên...")}</span>
                </>
              ) : (
                `${t("knowledge.upload.startBtn", "Tải lên")} ${files.length > 1 ? `(${files.length})` : ""}`
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
