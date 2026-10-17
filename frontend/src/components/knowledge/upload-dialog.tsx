"use client";

import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { apiUpload } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { KnowledgeTypeSelect } from "./knowledge-type-select";
import { ScopePicker, type ScopeMode } from "./scope-picker";
import { errorText, type Department, type KnowledgeType } from "./types";

const ACCEPTED = ["pdf", "docx", "doc", "rtf", "xlsx", "xls", "csv", "txt", "md", "pptx", "ppt"];
const ACCEPT_ATTR = ACCEPTED.map((e) => `.${e}`).join(",");
const MAX_BYTES = 50 * 1024 * 1024;

type FileStatus = "queued" | "uploading" | "done" | "error";
type QueuedFile = { key: string; file: File; status: FileStatus; error?: string };

const STATUS_ICON: Record<FileStatus, { icon: string; cls: string }> = {
  queued: { icon: "schedule", cls: "text-muted-foreground" },
  uploading: { icon: "progress_activity", cls: "animate-spin text-primary" },
  done: { icon: "check_circle", cls: "text-emerald-600 dark:text-emerald-400" },
  error: { icon: "error", cls: "text-destructive" },
};

function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 && dot < name.length - 1 ? name.slice(dot + 1).toLowerCase() : "";
}

function fileTone(ext: string): { icon: string; cls: string } {
  switch (ext) {
    case "pdf":
      return { icon: "picture_as_pdf", cls: "bg-rose-500/10 text-rose-600 dark:text-rose-400" };
    case "docx":
    case "doc":
    case "rtf":
      return { icon: "description", cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" };
    case "xlsx":
    case "xls":
    case "csv":
      return { icon: "table_chart", cls: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" };
    case "pptx":
    case "ppt":
      return { icon: "slideshow", cls: "bg-amber-500/10 text-amber-600 dark:text-amber-400" };
    case "md":
    case "txt":
      return { icon: "article", cls: "bg-slate-500/10 text-slate-600 dark:text-slate-400" };
    default:
      return { icon: "draft", cls: "bg-primary/10 text-primary" };
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Icon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  return (
    <span className={cn("material-symbols-outlined", className)} style={{ fontSize: size }}>
      {name}
    </span>
  );
}

function StepSection({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <span className="flex size-5 items-center justify-center rounded-full bg-primary/10 text-[11px] text-primary">
          {n}
        </span>
        {title}
      </h3>
      {children}
    </section>
  );
}

type ProcessingMode = "auto" | "articles" | "verbatim_page" | "verbatim";

function isLegalType(type: KnowledgeType | undefined): boolean {
  if (!type) return false;
  const slug = (type.slug || "").toLowerCase();
  const name = (type.name || "").toLowerCase();
  return (
    ["legal", "luat", "lut"].includes(slug) ||
    ["luật", "luat", "legal", "pháp lý"].some((k) => name.includes(k))
  );
}

function modeOptions(legal: boolean): { value: ProcessingMode; icon: string; title: string; desc: string }[] {
  const options: { value: ProcessingMode; icon: string; title: string; desc: string }[] = [
    {
      value: "auto",
      icon: "auto_awesome",
      title: "Tự động (khuyến nghị)",
      desc: legal
        ? "Tách nguyên văn theo từng Điều, đồng thời LLM biên soạn trang tri thức"
        : "LLM đọc tài liệu và biên soạn các trang tri thức",
    },
  ];
  if (legal) {
    options.push({
      value: "articles",
      icon: "format_list_numbered",
      title: "Chỉ tách theo Điều",
      desc: "Mỗi Điều thành một trang nguyên văn, không dùng LLM",
    });
  }
  options.push(
    {
      value: "verbatim_page",
      icon: "article",
      title: "Nguyên văn thành trang",
      desc: "Giữ nguyên văn bản và hình ảnh trong 1 trang; tự chia nhiều phần nếu quá dài",
    },
    {
      value: "verbatim",
      icon: "manage_search",
      title: "Chỉ lưu để tra cứu",
      desc: "Không tạo trang Wiki, chỉ đánh chỉ mục để tìm kiếm và hỏi đáp",
    }
  );
  return options;
}

function ProcessingModePicker({
  value,
  onChange,
  legal,
  personal,
  disabled,
}: {
  value: ProcessingMode;
  onChange: (v: ProcessingMode) => void;
  legal: boolean;
  personal: boolean;
  disabled?: boolean;
}) {
  if (personal) {
    return (
      <p className="flex items-start gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
        <Icon name="info" size={16} className="shrink-0" />
        Tài liệu cá nhân chỉ được lưu để tra cứu, không tạo trang Wiki. Chọn phạm vi Theo phòng ban hoặc Toàn hệ thống
        để chọn cơ chế xử lý.
      </p>
    );
  }
  return (
    <div role="radiogroup" className="grid gap-2 sm:grid-cols-2">
      {modeOptions(legal).map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60",
              active ? "border-primary bg-primary/5" : "hover:border-primary/40"
            )}
          >
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-md",
                active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
              )}
            >
              <Icon name={opt.icon} size={16} />
            </span>
            <span className="min-w-0">
              <span className="block text-xs font-medium">{opt.title}</span>
              <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">{opt.desc}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  types: KnowledgeType[];
  departments: Department[];
  onUploaded: () => void;
};

export function UploadDialog({ open, onOpenChange, types, departments, onUploaded }: Props) {
  const [uploading, setUploading] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && uploading) return;
        onOpenChange(next);
      }}
    >
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        {/* Body remounts on every open, which gives a fresh default state. */}
        <UploadBody
          types={types}
          departments={departments}
          uploading={uploading}
          setUploading={setUploading}
          onCancel={() => onOpenChange(false)}
          onUploaded={onUploaded}
          onFinished={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function UploadBody({
  types,
  departments,
  uploading,
  setUploading,
  onCancel,
  onUploaded,
  onFinished,
}: {
  types: KnowledgeType[];
  departments: Department[];
  uploading: boolean;
  setUploading: (v: boolean) => void;
  onCancel: () => void;
  onUploaded: () => void;
  onFinished: () => void;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<QueuedFile[]>([]);
  const [typeId, setTypeId] = useState(() => types.find((ty) => ty.slug === "general")?.id ?? "");
  const [mode, setMode] = useState<ScopeMode>("personal");
  const [deptIds, setDeptIds] = useState<string[]>([]);
  const [procMode, setProcMode] = useState<ProcessingMode>("auto");
  const legal = isLegalType(types.find((ty) => ty.id === typeId));
  const effectiveMode: ProcessingMode = !legal && procMode === "articles" ? "auto" : procMode;
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const pending = files.filter((f) => f.status !== "done");
  const doneCount = files.length - pending.length;
  const pendingBytes = pending.reduce((sum, f) => sum + f.file.size, 0);
  const deptMissing = mode === "department" && deptIds.length === 0;
  const canUpload = !uploading && pending.length > 0 && !deptMissing;

  const addFiles = (list: FileList | File[] | null) => {
    if (!list) return;
    const problems: string[] = [];
    const accepted: QueuedFile[] = [];
    const known = new Set(files.map((f) => f.key));
    for (const file of Array.from(list)) {
      const ext = extOf(file.name);
      if (!ACCEPTED.includes(ext)) {
        problems.push(`"${file.name}": định dạng .${ext || "?"} không được hỗ trợ`);
        continue;
      }
      if (file.size > MAX_BYTES) {
        problems.push(`"${file.name}": vượt quá 50 MB`);
        continue;
      }
      const key = `${file.name}_${file.size}`;
      if (known.has(key)) continue;
      known.add(key);
      accepted.push({ key, file, status: "queued" });
    }
    if (accepted.length > 0) setFiles((prev) => [...prev, ...accepted]);
    if (problems.length > 0) {
      const extra = problems.length > 2 ? ` (+${problems.length - 2})` : "";
      setError(problems.slice(0, 2).join("; ") + extra);
    } else {
      setError(null);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    if (uploading) return;
    addFiles(e.dataTransfer.files);
  };

  const updateFile = (key: string, patch: Partial<QueuedFile>) => {
    setFiles((prev) => prev.map((f) => (f.key === key ? { ...f, ...patch } : f)));
  };

  const upload = async () => {
    if (deptMissing) {
      setError(t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban"));
      return;
    }
    const queue = files.filter((f) => f.status !== "done");
    if (queue.length === 0) return;
    setError(null);
    setUploading(true);
    let ok = 0;
    for (const item of queue) {
      updateFile(item.key, { status: "uploading", error: undefined });
      const form = new FormData();
      form.append("file", item.file);
      if (typeId) form.append("knowledge_type_id", typeId);
      form.append("scope_type", mode);
      if (mode === "department") form.append("department_ids", deptIds.join(","));
      if (mode !== "personal") form.append("processing_mode", effectiveMode);
      try {
        await apiUpload("/api/sources/upload", form);
        ok += 1;
        updateFile(item.key, { status: "done" });
      } catch (err) {
        updateFile(item.key, { status: "error", error: errorText(err, "Tải lên thất bại") });
      }
    }
    setUploading(false);
    if (ok > 0) onUploaded();
    if (ok === queue.length) {
      onFinished();
    } else {
      setError(`Tải lên ${ok}/${queue.length} tệp. Kiểm tra các tệp lỗi bên dưới.`);
    }
  };

  const hasFiles = files.length > 0;

  return (
    <>
      <div className="border-b px-5 py-4 pr-12">
        <DialogTitle className="text-base font-semibold">{t("knowledge.upload.title")}</DialogTitle>
        <DialogDescription className="mt-1 text-xs">
          Tài liệu được trích xuất nội dung, tách điều khoản và biên soạn vào Kho tri thức.
        </DialogDescription>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        <StepSection n={1} title="Nguồn tài liệu">
          <div
            role="button"
            tabIndex={0}
            onClick={() => !uploading && inputRef.current?.click()}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === " ") && !uploading) {
                e.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              if (!uploading) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={cn(
              "flex cursor-pointer rounded-xl border-2 border-dashed transition-colors",
              hasFiles ? "flex-row items-center gap-3 px-4 py-3" : "flex-col items-center justify-center gap-2 px-6 py-10 text-center",
              dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/40",
              uploading && "cursor-not-allowed opacity-60"
            )}
          >
            <span
              className={cn(
                "flex shrink-0 items-center justify-center rounded-full",
                hasFiles ? "size-8" : "size-11",
                dragging ? "bg-primary text-primary-foreground" : "bg-primary/10 text-primary"
              )}
            >
              <Icon name="upload_file" size={hasFiles ? 18 : 22} />
            </span>
            <div className={cn(hasFiles && "text-left")}>
              <p className="text-sm font-medium">
                {dragging ? "Thả tài liệu vào đây" : hasFiles ? "Thêm tệp khác" : "Kéo thả tài liệu hoặc nhấp để chọn"}
              </p>
              <p className="text-[11px] text-muted-foreground">
                PDF, DOCX, DOC, RTF, XLSX, XLS, CSV, TXT, MD, PPTX · tối đa 50 MB/tệp
              </p>
            </div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT_ATTR}
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {hasFiles && (
            <ul className="max-h-56 divide-y overflow-y-auto rounded-lg border">
              {files.map((f) => {
                const ext = extOf(f.file.name);
                const tone = fileTone(ext);
                const st = STATUS_ICON[f.status];
                return (
                  <li key={f.key} className="flex items-center gap-3 px-3 py-2">
                    <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-md", tone.cls)}>
                      <Icon name={tone.icon} size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium" title={f.file.name}>
                        {f.file.name}
                      </p>
                      {f.error ? (
                        <p className="truncate text-[11px] text-destructive" title={f.error}>
                          {f.error}
                        </p>
                      ) : (
                        <p className="text-[11px] text-muted-foreground">
                          {formatSize(f.file.size)} · .{ext.toUpperCase()}
                        </p>
                      )}
                    </div>
                    <Icon name={st.icon} size={18} className={st.cls} />
                    {!uploading && f.status !== "done" && (
                      <button
                        type="button"
                        title="Bỏ tệp này"
                        aria-label="Bỏ tệp này"
                        onClick={() => setFiles((prev) => prev.filter((x) => x.key !== f.key))}
                        className="flex text-muted-foreground hover:text-destructive"
                      >
                        <Icon name="close" size={16} />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </StepSection>

        <StepSection n={2} title="Phân loại & phạm vi">
          <div className="grid gap-x-4 gap-y-3 sm:grid-cols-[7.5rem_1fr] sm:items-start">
            <span className="pt-2 text-xs text-muted-foreground">Danh mục</span>
            <KnowledgeTypeSelect types={types} value={typeId} onChange={setTypeId} disabled={uploading} />
            <span className="pt-2 text-xs text-muted-foreground">{t("knowledge.upload.visibility")}</span>
            <ScopePicker
              mode={mode}
              onModeChange={setMode}
              departments={departments}
              selected={deptIds}
              onSelectedChange={setDeptIds}
              disabled={uploading}
              allowPersonal
            />
          </div>
        </StepSection>

        <StepSection n={3} title="Cơ chế xử lý">
          <ProcessingModePicker
            value={effectiveMode}
            onChange={setProcMode}
            legal={legal}
            personal={mode === "personal"}
            disabled={uploading}
          />
        </StepSection>

        {error && (
          <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <Icon name="error" size={16} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t bg-muted/20 px-5 py-3">
        <span className="text-xs text-muted-foreground">
          {files.length === 0
            ? "Chưa chọn tệp nào"
            : `${pending.length} tệp · ${formatSize(pendingBytes)}${doneCount > 0 ? ` · đã xong ${doneCount}` : ""}`}
        </span>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={onCancel} disabled={uploading}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void upload()} disabled={!canUpload}>
            {uploading ? (
              <>
                <Icon name="progress_activity" size={16} className="animate-spin" />
                Đang tải lên...
              </>
            ) : (
              <>
                <Icon name="upload" size={16} />
                Tải lên{pending.length > 1 ? ` (${pending.length})` : ""}
              </>
            )}
          </Button>
        </div>
      </div>
    </>
  );
}
