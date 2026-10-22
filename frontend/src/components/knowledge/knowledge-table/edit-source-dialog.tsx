"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { KnowledgeTypeSelect } from "../knowledge-type-select";
import { ManagingDepartmentSelect } from "../managing-department-select";
import { ScopePicker, type ScopeMode } from "../scope-picker";
import { errorText, type Department, type KnowledgeType, type Source } from "../types";

type MetaKey =
  | "doc_number"
  | "doc_type"
  | "issuing_authority"
  | "official_title"
  | "issued_date"
  | "effective_date"
  | "expiry_date"
  | "field";

const META_KEYS: MetaKey[] = [
  "doc_number",
  "doc_type",
  "issuing_authority",
  "official_title",
  "issued_date",
  "effective_date",
  "expiry_date",
  "field",
];

const DOC_TYPE_SUGGESTIONS = [
  "Luật",
  "Bộ luật",
  "Nghị định",
  "Nghị quyết",
  "Thông tư",
  "Quyết định",
  "Chỉ thị",
  "Công văn",
  "Hướng dẫn",
  "Kế hoạch",
  "Quy chế",
];

const NO_FIELD = "__none__";

type Props = {
  source: Source;
  types: KnowledgeType[];
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
  reviewUpload?: boolean;
};

function initialMeta(source: Source): Record<MetaKey, string> {
  const meta = source.doc_meta ?? {};
  const out = {} as Record<MetaKey, string>;
  for (const k of META_KEYS) {
    const v = (meta as Record<string, unknown>)[k];
    out[k] = typeof v === "string" ? v : "";
  }
  return out;
}

function initialScope(source: Source): ScopeMode {
  if (source.scope_type === "personal") return "personal";
  if (source.scope_type === "department" || (source.department_ids?.length ?? 0) > 0) return "department";
  return "global";
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  return b.every((x) => s.has(x));
}

function Section({ icon, title, hint, children }: { icon: string; title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: 17 }}>
            {icon}
          </span>
          {title}
        </h3>
        {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

export function EditSourceDialog({ source, types, departments, onClose, onSaved, reviewUpload = false }: Props) {
  const { t } = useI18n();
  const manual = new Set(source.doc_meta?.manual_fields ?? []);

  const [title, setTitle] = useState(source.title ?? "");
  const [typeId, setTypeId] = useState(source.knowledge_type_id ?? "");
  const [meta, setMeta] = useState<Record<MetaKey, string>>(() => initialMeta(source));
  const [originalMeta] = useState<Record<MetaKey, string>>(() => initialMeta(source));
  const [originalMode] = useState<ScopeMode>(() => initialScope(source));
  const [originalDepts] = useState<string[]>(() => source.department_ids ?? []);
  const [mode, setMode] = useState<ScopeMode>(originalMode);
  const [deptIds, setDeptIds] = useState<string[]>(originalDepts);
  const [managerId, setManagerId] = useState(source.managing_department_id || "");
  const [fields, setFields] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let alive = true;
    api<{ fields?: string[] }>("/api/wiki/legal-doc-fields")
      .then((res) => {
        if (alive && Array.isArray(res?.fields)) setFields(res.fields);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const fieldOptions = meta.field && !fields.includes(meta.field) ? [meta.field, ...fields] : fields;

  const setMetaField = (key: MetaKey, value: string) => setMeta((m) => ({ ...m, [key]: value }));

  const scopeChanged =
    mode !== originalMode || (mode === "department" && !sameSet(deptIds, originalDepts));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        knowledge_type_id: typeId || null,
        scope_type: mode,
        scope_id: null,
        department_ids: mode === "department" ? deptIds : [],
      };
      const trimmedTitle = title.trim();
      if (managerId !== (source.managing_department_id || "")) body.managing_department_id = managerId || null;
      if (trimmedTitle) body.title = trimmedTitle;

      const changed: Record<string, string | null> = {};
      for (const k of META_KEYS) {
        const next = meta[k].trim();
        if (next !== originalMeta[k].trim()) changed[k] = next || null;
      }
      if (Object.keys(changed).length > 0) body.doc_meta = changed;

      await api(`/api/sources/${source.id}`, { method: "PATCH", body });
      if (reviewUpload) await api(`/api/sources/${source.id}/approve-upload`, { method: "POST" });
      onSaved();
    } catch (err) {
      setError(errorText(err, "Không lưu được thay đổi"));
      setConfirming(false);
    } finally {
      setSaving(false);
    }
  };

  const submit = () => {
    setError(null);
    if (mode === "department" && deptIds.length === 0) {
      setError(t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban"));
      return;
    }
    const issued = meta.issued_date.trim();
    const effective = meta.effective_date.trim();
    if (issued && effective && effective < issued) {
      setError("Ngày hiệu lực không thể trước ngày ban hành");
      return;
    }
    if (source.status === "ready" && scopeChanged) {
      setConfirming(true);
      return;
    }
    void save();
  };

  const label = (key: MetaKey | null, text: string) => (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      {text}
      {key && manual.has(key) && (
        <span
          title="Đã chỉnh sửa thủ công — giữ nguyên khi trích xuất lại"
          className="rounded bg-primary/10 px-1 py-px text-[10px] font-medium text-primary"
        >
          thủ công
        </span>
      )}
    </span>
  );

  const inputCls = "h-9 text-sm";

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose();
      }}
    >
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <div className="border-b px-5 py-4 pr-12">
          <DialogTitle className="text-base font-semibold">{reviewUpload ? "Duyệt thông tin trích xuất" : "Chỉnh sửa thông tin tài liệu"}</DialogTitle>
          <DialogDescription className="mt-1 truncate text-xs" title={source.file_name || source.title}>
            {source.file_name || source.title}
          </DialogDescription>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          {reviewUpload && (
            <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-sm dark:border-blue-500/30 dark:bg-blue-500/10">
              <p>Kiểm tra thông tin hệ thống nhận diện trước khi tạo Wiki và chỉ mục tìm kiếm. Bạn có thể sửa các trường bên dưới.</p>
              <p className="text-xs text-muted-foreground">{source.page_count ?? 0} trang · {source.image_count ?? 0} ảnh · {(source.extracted_token_count ?? 0).toLocaleString("vi-VN")} token</p>
              <a href={`/wiki/source/${source.id}?tab=extracted`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline underline-offset-4">Đối chiếu nội dung trích xuất<span className="material-symbols-outlined text-[15px]" aria-hidden>open_in_new</span></a>
              {source.upload_review_error && <p className="text-xs text-amber-700 dark:text-amber-300">{source.upload_review_error}</p>}
            </div>
          )}
          <Section icon="info" title="Thông tin chung">
            <div className="grid gap-3 sm:grid-cols-[1fr_14rem]">
              <label className="flex flex-col gap-1.5">
                {label(null, "Tiêu đề hiển thị")}
                <Input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} disabled={saving} />
              </label>
              <div className="flex flex-col gap-1.5">
                {label(null, "Phân loại văn bản")}
                <KnowledgeTypeSelect types={types} value={typeId} onChange={setTypeId} disabled={saving} />
              </div>
            </div>
            <div className="space-y-1.5"><span className="text-xs text-muted-foreground">Phòng ban quản lý</span><ManagingDepartmentSelect departments={departments} value={managerId} onChange={setManagerId} disabled={saving} currentName={source.managing_department_name} /></div>
          </Section>

          <Section
            icon="gavel"
            title="Thuộc tính văn bản"
            hint="Tự động trích xuất khi xử lý. Trường bạn sửa sẽ được giữ nguyên khi trích xuất lại."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="flex flex-col gap-1.5">
                {label("doc_number", "Số hiệu")}
                <Input
                  className={inputCls}
                  placeholder="VD: 59/2020/QH14"
                  value={meta.doc_number}
                  onChange={(e) => setMetaField("doc_number", e.target.value)}
                  disabled={saving}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                {label("doc_type", "Loại văn bản")}
                <Input
                  className={inputCls}
                  placeholder="VD: Luật"
                  list={`doc-type-options-${source.id}`}
                  value={meta.doc_type}
                  onChange={(e) => setMetaField("doc_type", e.target.value)}
                  disabled={saving}
                />
                <datalist id={`doc-type-options-${source.id}`}>
                  {DOC_TYPE_SUGGESTIONS.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              </label>
              <div className="flex flex-col gap-1.5">
                {label("field", "Lĩnh vực")}
                <Select
                  value={meta.field || NO_FIELD}
                  onValueChange={(v) => setMetaField("field", !v || v === NO_FIELD ? "" : String(v))}
                  disabled={saving}
                >
                  <SelectTrigger className="h-9 w-full text-sm">
                    <SelectValue>
                      {(v: string | null) =>
                        v && v !== NO_FIELD ? (
                          <span className="truncate">{v}</span>
                        ) : (
                          <span className="text-muted-foreground">Chưa xác định</span>
                        )
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_FIELD}>
                      <span className="text-muted-foreground">Chưa xác định</span>
                    </SelectItem>
                    {fieldOptions.map((f) => (
                      <SelectItem key={f} value={f}>
                        {f}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <label className="flex flex-col gap-1.5">
              {label("issuing_authority", "Cơ quan ban hành")}
              <Input
                className={inputCls}
                placeholder="VD: Quốc hội"
                value={meta.issuing_authority}
                onChange={(e) => setMetaField("issuing_authority", e.target.value)}
                disabled={saving}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              {label("official_title", "Trích yếu / tên chính thức")}
              <Input
                className={inputCls}
                value={meta.official_title}
                onChange={(e) => setMetaField("official_title", e.target.value)}
                disabled={saving}
              />
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              {(
                [
                  ["issued_date", "Ngày ban hành"],
                  ["effective_date", "Ngày hiệu lực"],
                  ["expiry_date", "Hết hiệu lực"],
                ] as [MetaKey, string][]
              ).map(([key, text]) => (
                <label key={key} className="flex flex-col gap-1.5">
                  {label(key, text)}
                  <Input
                    type="date"
                    className={inputCls}
                    value={meta[key]}
                    onChange={(e) => setMetaField(key, e.target.value)}
                    disabled={saving}
                  />
                </label>
              ))}
            </div>
          </Section>

          <Section icon="visibility" title={t("knowledge.upload.visibility")}>
            <ScopePicker
              mode={mode}
              onModeChange={setMode}
              departments={departments}
              selected={deptIds}
              onSelectedChange={setDeptIds}
              disabled={saving}
              allowPersonal
            />
          </Section>

          {confirming && (
            <div className="flex flex-col gap-3 rounded-lg border border-amber-500/40 bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined shrink-0" style={{ fontSize: 18 }}>
                  warning
                </span>
                <p>
                  {mode === "personal"
                    ? "Wiki và chỉ mục của tài liệu sẽ được chuyển sang phạm vi cá nhân; chỉ chủ tài liệu xem được. Bạn có muốn tiếp tục?"
                    : t("knowledge.edit.scopeChangeConfirm")}
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setConfirming(false)} disabled={saving}>
                  {t("common.cancel")}
                </Button>
                <Button
                  size="sm"
                  className="bg-amber-600 text-white hover:bg-amber-600/90"
                  onClick={() => void save()}
                  disabled={saving}
                >
                  {t("common.confirm")}
                </Button>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
                error
              </span>
              <span>{error}</span>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t bg-muted/20 px-5 py-3">
          <Button variant="outline" onClick={onClose} disabled={saving}>
            {reviewUpload ? "Duyệt sau" : t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={saving || confirming}>
            <span
              className={cn("material-symbols-outlined", saving && "animate-spin")}
              style={{ fontSize: 16 }}
            >
              {saving ? "progress_activity" : "save"}
            </span>
            {saving ? "Đang lưu..." : reviewUpload ? "Xác nhận & tiếp tục xử lý" : "Lưu thay đổi"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
