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
import { ScopePicker, ScopeMode } from "../scope-picker";
import { Source, KnowledgeType, Department } from "./types";
import { useI18n } from "@/lib/i18n";

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

const DOC_TYPES = ["Luật", "Bộ luật", "Nghị định", "Nghị quyết", "Thông tư", "Quyết định", "Chỉ thị", "Công văn", "Hướng dẫn", "Kế hoạch", "Quy chế"];

function Section({ icon, title, hint, children }: { icon: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: 17 }}>{icon}</span>
          {title}
        </h3>
        {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children, manual }: { label: string; children: React.ReactNode; manual?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <Label className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
        {label}
        {manual && (
          <span className="rounded bg-primary/10 px-1 text-[10px] font-medium text-primary" title="Đã chỉnh sửa thủ công — giữ nguyên khi trích xuất lại">
            thủ công
          </span>
        )}
      </Label>
      {children}
    </div>
  );
}

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
  const selectedType = types.find((x) => x.id === typeId);

  const initialMeta = React.useMemo(() => {
    const m = source.doc_meta || {};
    return Object.fromEntries(META_KEYS.map((k) => [k, (m[k] as string | null | undefined) || ""])) as Record<MetaKey, string>;
  }, [source.doc_meta]);
  const [meta, setMeta] = React.useState<Record<MetaKey, string>>(initialMeta);
  const manual = new Set(source.doc_meta?.manual_fields || []);
  const setMetaField = (k: MetaKey, v: string) => setMeta((prev) => ({ ...prev, [k]: v }));

  const [fields, setFields] = React.useState<string[]>([]);
  React.useEffect(() => {
    let alive = true;
    api<{ fields: string[] }>("/api/wiki/legal-doc-fields")
      .then((r) => { if (alive) setFields(r.fields || []); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  const fieldOptions = meta.field && !fields.includes(meta.field) ? [meta.field, ...fields] : fields;

  const initialMode: ScopeMode =
    source.scope_type === "department" || (source.department_ids && source.department_ids.length > 0) ? "department" : "global";
  const [scopeMode, setScopeMode] = React.useState<ScopeMode>(initialMode);
  const [selectedDepts, setSelectedDepts] = React.useState<string[]>(source.department_ids || []);

  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [pendingConfirm, setPendingConfirm] = React.useState(false);

  const scopeChanged = () => {
    if (scopeMode !== initialMode) return true;
    if (scopeMode === "department") {
      const orig = new Set(source.department_ids || []);
      return orig.size !== selectedDepts.length || selectedDepts.some((d) => !orig.has(d));
    }
    return false;
  };

  const doSave = async () => {
    if (scopeMode === "department" && selectedDepts.length === 0) {
      setError(t("dept.selectAtLeastOne", "Vui lòng chọn ít nhất một phòng ban"));
      return;
    }
    if (meta.effective_date && meta.issued_date && meta.effective_date < meta.issued_date) {
      setError("Ngày hiệu lực không thể trước ngày ban hành");
      return;
    }

    setSaving(true);
    setError("");
    setPendingConfirm(false);
    try {
      const changedMeta = Object.fromEntries(
        META_KEYS.filter((k) => meta[k].trim() !== initialMeta[k]).map((k) => [k, meta[k].trim() || null]),
      );
      const body: Record<string, unknown> = {
        title: title.trim() || undefined,
        knowledge_type_id: typeId || null,
        scope_type: scopeMode,
        scope_id: null,
        department_ids: scopeMode === "department" ? selectedDepts : [],
      };
      if (Object.keys(changedMeta).length) body.doc_meta = changedMeta;

      await api(`/api/sources/${source.id}`, { method: "PATCH", body });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không lưu được thay đổi");
    } finally {
      setSaving(false);
    }
  };

  const handleSave = () => {
    if (source.status === "ready" && scopeChanged()) setPendingConfirm(true);
    else doSave();
  };

  const inputCls = "h-9 bg-background text-sm";

  return (
    <Dialog open onOpenChange={() => { if (!saving) onClose(); }}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col p-0 overflow-hidden gap-0">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60 shrink-0 pr-12">
          <DialogTitle className="text-lg font-semibold">{t("knowledge.edit.title", "Chỉnh sửa tài liệu")}</DialogTitle>
          <p className="text-xs text-muted-foreground mt-0.5 truncate" title={source.file_name || source.title}>
            {source.file_name || source.title}
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
          <Section icon="info" title="Thông tin chung">
            <div className="grid gap-3 sm:grid-cols-[1fr_14rem]">
              <Field label="Tiêu đề hiển thị">
                <Input value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} />
              </Field>
              <Field label="Danh mục">
                <Select value={typeId} onValueChange={(v) => setTypeId(v ?? "")}>
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
              </Field>
            </div>
          </Section>

          <Section
            icon="gavel"
            title="Thuộc tính văn bản"
            hint="Tự động trích xuất khi xử lý. Trường bạn sửa sẽ được giữ nguyên khi trích xuất lại."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Số hiệu" manual={manual.has("doc_number")}>
                <Input value={meta.doc_number} onChange={(e) => setMetaField("doc_number", e.target.value)} placeholder="VD: 59/2020/QH14" className={inputCls} />
              </Field>
              <Field label="Loại văn bản" manual={manual.has("doc_type")}>
                <Input value={meta.doc_type} onChange={(e) => setMetaField("doc_type", e.target.value)} list="doc-type-options" placeholder="VD: Luật" className={inputCls} />
                <datalist id="doc-type-options">
                  {DOC_TYPES.map((d) => <option key={d} value={d} />)}
                </datalist>
              </Field>
              <Field label="Lĩnh vực" manual={manual.has("field")}>
                <Select value={meta.field} onValueChange={(v) => setMetaField("field", v ?? "")}>
                  <SelectTrigger className="bg-background w-full h-9 text-sm">
                    <SelectValue placeholder="Chưa xác định" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Chưa xác định</SelectItem>
                    {fieldOptions.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <Field label="Cơ quan ban hành" manual={manual.has("issuing_authority")}>
              <Input value={meta.issuing_authority} onChange={(e) => setMetaField("issuing_authority", e.target.value)} placeholder="VD: Quốc hội" className={inputCls} />
            </Field>
            <Field label="Trích yếu / tên chính thức" manual={manual.has("official_title")}>
              <Input value={meta.official_title} onChange={(e) => setMetaField("official_title", e.target.value)} className={inputCls} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Ngày ban hành" manual={manual.has("issued_date")}>
                <Input type="date" value={meta.issued_date} onChange={(e) => setMetaField("issued_date", e.target.value)} className={inputCls} />
              </Field>
              <Field label="Ngày hiệu lực" manual={manual.has("effective_date")}>
                <Input type="date" value={meta.effective_date} onChange={(e) => setMetaField("effective_date", e.target.value)} className={inputCls} />
              </Field>
              <Field label="Hết hiệu lực" manual={manual.has("expiry_date")}>
                <Input type="date" value={meta.expiry_date} onChange={(e) => setMetaField("expiry_date", e.target.value)} className={inputCls} />
              </Field>
            </div>
          </Section>

          <Section icon="visibility" title={t("knowledge.upload.visibility", "Phạm vi hiển thị")}>
            <ScopePicker
              mode={scopeMode}
              onModeChange={setScopeMode}
              departments={departments}
              selected={selectedDepts}
              onSelectedChange={setSelectedDepts}
              disabled={saving}
            />
          </Section>

          {pendingConfirm && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30 p-3 flex flex-col gap-2.5">
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" style={{ fontSize: 16 }}>warning</span>
                <p className="text-xs text-amber-800 dark:text-amber-300">
                  {t("knowledge.edit.scopeChangeConfirm", "Việc thay đổi phạm vi hiển thị sẽ kích hoạt biên soạn lại tri thức bằng AI. Bạn có muốn tiếp tục?")}
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setPendingConfirm(false)}>{t("common.cancel", "Hủy")}</Button>
                <Button size="sm" onClick={doSave} className="bg-amber-600 hover:bg-amber-700 text-white">{t("common.confirm", "Xác nhận")}</Button>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>error</span>
              <span className="font-medium">{error}</span>
            </div>
          )}
        </div>

        <div className="px-6 py-3 border-t border-border/60 bg-muted/20 shrink-0 flex justify-end gap-2">
          <Button variant="outline" size="sm" className="h-8" onClick={onClose} disabled={saving}>{t("common.cancel", "Hủy")}</Button>
          <Button size="sm" className="h-8 gap-1.5" disabled={saving || pendingConfirm} onClick={handleSave}>
            {saving ? (
              <>
                <span className="material-symbols-outlined animate-spin" style={{ fontSize: 16 }}>progress_activity</span>
                Đang lưu...
              </>
            ) : (
              <>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>save</span>
                Lưu thay đổi
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
