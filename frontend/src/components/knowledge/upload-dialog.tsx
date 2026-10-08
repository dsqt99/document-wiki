"use client";

import { useState, useRef, useCallback } from "react";
import { api, apiUpload } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
import { ScopePicker, ScopeMode } from "./scope-picker";
import { cn } from "@/lib/utils";
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

// doc/ppt/rtf are converted by LibreOffice on the server; the API rejects them
// with a clear message if LibreOffice is not installed.
const ACCEPTED_EXTENSIONS = ["pdf", "docx", "doc", "rtf", "xlsx", "xls", "csv", "txt", "md", "pptx", "ppt"];
const ACCEPT_STRING = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(",");
const MAX_BYTES = 50 * 1024 * 1024;

type Mode = "file" | "url";
type ItemState = "queued" | "uploading" | "done" | "error";
type Item = { key: string; file: File; state: ItemState; message?: string };

function getFileExtension(name: string): string {
  return (name.split(".").pop() || "").toLowerCase();
}

function getFileIcon(ext: string): { icon: string; color: string } {
  switch (ext) {
    case "pdf":
      return { icon: "picture_as_pdf", color: "text-rose-500 bg-rose-500/10" };
    case "docx":
    case "doc":
    case "rtf":
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
  if (!ext || !ACCEPTED_EXTENSIONS.includes(ext)) {
    return `"${f.name}": định dạng .${ext || "?"} không được hỗ trợ`;
  }
  if (f.size > MAX_BYTES) return `"${f.name}": vượt quá 50 MB`;
  return null;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const STATE_ICON: Record<ItemState, { icon: string; cls: string }> = {
  queued: { icon: "schedule", cls: "text-muted-foreground" },
  uploading: { icon: "progress_activity", cls: "text-primary animate-spin" },
  done: { icon: "check_circle", cls: "text-emerald-600" },
  error: { icon: "error", cls: "text-destructive" },
};

function Section({ step, title, children, aside }: { step: number; title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="flex size-5 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
          {step}
        </span>
        <Label className="text-sm font-semibold">{title}</Label>
        {aside && <span className="ml-auto">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export function UploadDialog({ open, onOpenChange, types, departments, onUploaded }: Props) {
  const { t } = useI18n();
  const [mode, setMode] = useState<Mode>("file");
  const [items, setItems] = useState<Item[]>([]);
  const [url, setUrl] = useState("");
  const [urlTitle, setUrlTitle] = useState("");
  const [selectedTypeId, setSelectedTypeId] = useState<string | null>(null);
  const defaultTypeId = types.find((x) => x.slug === "general")?.id || "";
  const typeId = selectedTypeId !== null ? selectedTypeId : defaultTypeId;
  const selectedType = types.find((x) => x.id === typeId);
  const [verbatim, setVerbatim] = useState(false);
  const [scopeMode, setScopeMode] = useState<ScopeMode>("global");
  const [selectedDepts, setSelectedDepts] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setItems([]);
    setUrl("");
    setUrlTitle("");
    setSelectedTypeId(null);
    setVerbatim(false);
    setScopeMode("global");
    setSelectedDepts([]);
    setError("");
  };

  const addFiles = useCallback((incoming: File[]) => {
    if (!incoming.length) return;
    const errors: string[] = [];
    const valid: File[] = [];
    for (const f of incoming) {
      const err = validateFile(f);
      if (err) errors.push(err);
      else valid.push(f);
    }
    setError(errors.length ? errors.slice(0, 2).join("; ") + (errors.length > 2 ? ` (+${errors.length - 2})` : "") : "");
    if (valid.length) {
      setItems((prev) => {
        const keys = new Set(prev.map((i) => i.key));
        const added = valid
          .map((file) => ({ key: `${file.name}_${file.size}`, file, state: "queued" as const }))
          .filter((i) => !keys.has(i.key));
        return [...prev, ...added];
      });
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      addFiles(Array.from(e.dataTransfer.files || []));
    },
    [addFiles],
  );

  const patchItem = (key: string, patch: Partial<Item>) =>
    setItems((prev) => prev.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  const pending = items.filter((i) => i.state !== "done");
  const doneCount = items.filter((i) => i.state === "done").length;
  const canSubmit =
    !uploading &&
    (mode === "file" ? pending.length > 0 : /^https?:\/\/\S+$/i.test(url.trim())) &&
    !(scopeMode === "department" && selectedDepts.length === 0);

  const handleSubmit = async () => {
    if (scopeMode === "department" && selectedDepts.length === 0) {
      setError(t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban"));
      return;
    }
    setUploading(true);
    setError("");

    if (mode === "url") {
      try {
        await api("/api/sources/url", {
          method: "POST",
          body: {
            url: url.trim(),
            title: urlTitle.trim() || undefined,
            knowledge_type_id: typeId || undefined,
            department_ids: scopeMode === "department" ? selectedDepts : [],
            preserve_verbatim: verbatim,
          },
        });
        onUploaded();
        onOpenChange(false);
        reset();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Không thêm được liên kết");
      } finally {
        setUploading(false);
      }
      return;
    }

    let failed = 0;
    let succeeded = 0;
    for (const item of pending) {
      patchItem(item.key, { state: "uploading", message: undefined });
      try {
        const fd = new FormData();
        fd.append("file", item.file);
        if (typeId) fd.append("knowledge_type_id", typeId);
        fd.append("scope_type", scopeMode);
        if (scopeMode === "department") fd.append("department_ids", selectedDepts.join(","));
        fd.append("preserve_verbatim", String(verbatim));
        await apiUpload("/api/sources/upload", fd);
        patchItem(item.key, { state: "done" });
        succeeded++;
      } catch (err) {
        failed++;
        patchItem(item.key, { state: "error", message: err instanceof Error ? err.message : "Tải lên thất bại" });
      }
    }
    setUploading(false);
    if (succeeded) onUploaded();
    if (!failed) {
      onOpenChange(false);
      reset();
    } else {
      setError(`Tải lên ${succeeded}/${succeeded + failed} tệp. Kiểm tra các tệp lỗi bên dưới.`);
    }
  };

  const totalBytes = pending.reduce((acc, i) => acc + i.file.size, 0);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!uploading) onOpenChange(o); }}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col p-0 overflow-hidden gap-0">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60 shrink-0 pr-12">
          <DialogTitle className="text-lg font-semibold text-foreground">
            {t("knowledge.upload.title", "Tải lên tài liệu")}
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5">
            Tài liệu được trích xuất nội dung, tách điều khoản và biên soạn vào Trang wiki.
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT_STRING}
            onChange={(e) => {
              addFiles(Array.from(e.target.files || []));
              e.target.value = "";
            }}
            className="hidden"
          />

          <Section
            step={1}
            title="Nguồn tài liệu"
            aside={
              <div className="inline-flex rounded-lg bg-muted p-0.5 text-xs">
                {(
                  [
                    ["file", "upload_file", "Tệp tin"],
                    ["url", "link", "Liên kết"],
                  ] as const
                ).map(([m, icon, label]) => (
                  <button
                    key={m}
                    type="button"
                    disabled={uploading}
                    onClick={() => { setMode(m); setError(""); }}
                    className={cn(
                      "flex items-center gap-1 rounded-md px-2.5 py-1 font-medium transition-colors cursor-pointer",
                      mode === m ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 15 }}>{icon}</span>
                    {label}
                  </button>
                ))}
              </div>
            }
          >
            {mode === "url" ? (
              <div className="grid gap-2 sm:grid-cols-[1fr_14rem]">
                <input
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://thuvienphapluat.vn/van-ban/..."
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
                <input
                  value={urlTitle}
                  onChange={(e) => setUrlTitle(e.target.value)}
                  placeholder="Tiêu đề (tùy chọn)"
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <div
                  onDrop={handleDrop}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onClick={() => !uploading && fileInputRef.current?.click()}
                  className={cn(
                    "flex items-center gap-3 rounded-xl border-2 border-dashed px-4 cursor-pointer transition-colors",
                    items.length ? "py-3" : "py-7 flex-col justify-center text-center",
                    dragOver ? "border-primary bg-primary/5" : "border-border hover:border-primary/40 hover:bg-accent/30",
                  )}
                >
                  <span
                    className={cn(
                      "flex shrink-0 items-center justify-center rounded-full",
                      items.length ? "size-8" : "size-11",
                      dragOver ? "bg-primary/15 text-primary" : "bg-accent/70 text-muted-foreground",
                    )}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: items.length ? 18 : 24 }}>upload_file</span>
                  </span>
                  <div className={items.length ? "text-left" : ""}>
                    <p className="text-sm font-medium text-foreground">
                      {dragOver ? "Thả tài liệu vào đây" : items.length ? "Thêm tệp khác" : "Kéo thả tài liệu hoặc nhấp để chọn"}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      PDF, DOCX, DOC, RTF, XLSX, XLS, CSV, TXT, MD, PPTX · tối đa 50 MB/tệp
                    </p>
                  </div>
                </div>

                {items.length > 0 && (
                  <div className="rounded-xl border border-border divide-y divide-border/60 max-h-56 overflow-y-auto">
                    {items.map((item) => {
                      const ext = getFileExtension(item.file.name);
                      const ic = getFileIcon(ext);
                      const st = STATE_ICON[item.state];
                      return (
                        <div key={item.key} className="flex items-center gap-3 px-3 py-2">
                          <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", ic.color)}>
                            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>{ic.icon}</span>
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-medium text-foreground" title={item.file.name}>{item.file.name}</p>
                            <p
                              className={cn("truncate text-[11px]", item.state === "error" ? "text-destructive" : "text-muted-foreground")}
                              title={item.message}
                            >
                              {item.message || `${formatFileSize(item.file.size)} · .${ext.toUpperCase()}`}
                            </p>
                          </div>
                          <span className={cn("material-symbols-outlined shrink-0", st.cls)} style={{ fontSize: 18 }} title={item.state}>
                            {st.icon}
                          </span>
                          {!uploading && item.state !== "done" && (
                            <button
                              type="button"
                              onClick={() => setItems((prev) => prev.filter((i) => i.key !== item.key))}
                              className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive cursor-pointer"
                              title="Bỏ tệp này"
                            >
                              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </Section>

          <Section step={2} title="Phân loại & xử lý">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-muted-foreground">Danh mục</span>
                <Select value={typeId} onValueChange={(v) => setSelectedTypeId(v ?? "")} disabled={uploading}>
                  <SelectTrigger className="bg-background w-full h-9 text-sm">
                    {selectedType ? (
                      <div className="flex items-center gap-2">
                        <span className="size-2.5 rounded-full" style={{ backgroundColor: selectedType.color }} />
                        <span>{selectedType.name}</span>
                      </div>
                    ) : (
                      <SelectValue placeholder="Chưa phân loại" />
                    )}
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Chưa phân loại</SelectItem>
                    {types.map((ti) => (
                      <SelectItem key={ti.id} value={ti.id}>
                        <div className="flex items-center gap-2">
                          <span className="size-2.5 rounded-full" style={{ backgroundColor: ti.color }} />
                          {ti.name}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <label className="flex items-start gap-3 rounded-lg border border-border bg-background px-3 py-2 cursor-pointer">
                <Switch checked={verbatim} onCheckedChange={(v) => setVerbatim(!!v)} disabled={uploading} className="mt-0.5" />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">Giữ nguyên văn</span>
                  <span className="block text-[11px] text-muted-foreground leading-snug">
                    Tách theo Điều, không biên soạn lại bằng AI — phù hợp văn bản pháp luật.
                  </span>
                </span>
              </label>
            </div>
          </Section>

          <Section step={3} title={t("knowledge.upload.visibility", "Phạm vi hiển thị")}>
            <ScopePicker
              mode={scopeMode}
              onModeChange={setScopeMode}
              departments={departments}
              selected={selectedDepts}
              onSelectedChange={setSelectedDepts}
              disabled={uploading}
            />
          </Section>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>error</span>
              <span className="font-medium leading-relaxed">{error}</span>
            </div>
          )}
        </div>

        <div className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0 flex items-center justify-between gap-3">
          <div className="text-xs text-muted-foreground truncate">
            {mode === "url"
              ? "Nội dung trang sẽ được tải về và xử lý như tài liệu."
              : items.length === 0
                ? "Chưa chọn tệp nào"
                : `${pending.length} tệp · ${formatFileSize(totalBytes)}${doneCount ? ` · đã xong ${doneCount}` : ""}`}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={uploading} className="h-8">
              {t("common.cancel", "Hủy")}
            </Button>
            <Button size="sm" disabled={!canSubmit} onClick={handleSubmit} className="h-8 gap-1.5">
              {uploading ? (
                <>
                  <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>progress_activity</span>
                  Đang tải lên...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{mode === "url" ? "add_link" : "upload"}</span>
                  {mode === "url" ? "Thêm liên kết" : `Tải lên${pending.length > 1 ? ` (${pending.length})` : ""}`}
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
