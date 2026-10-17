"use client";

import { useState, type FormEvent } from "react";
import { TypePill } from "@/components/knowledge/type-pill";
import { errorText } from "@/components/knowledge/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Preset palette, in display order; the last entry (indigo) is the default for new types. */
export const TYPE_COLORS = [
  "#6b7280", // gray
  "#10b981", // emerald
  "#8b5cf6", // violet
  "#f59e0b", // amber
  "#3b82f6", // blue
  "#ef4444", // red
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
  "#6366f1", // indigo
];
const DEFAULT_COLOR = TYPE_COLORS[TYPE_COLORS.length - 1];

/** Vietnamese-aware slug: strip diacritics (đ → d), lower-case, non-alnum runs → "-". */
export function slugify(input: string): string {
  return input
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

type EditableType = { id: string; slug: string; name: string; color: string; description?: string | null };

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeType: EditableType | null;
  onSaved: () => void;
};

export function KnowledgeTypeDialog({ open, onOpenChange, knowledgeType, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <TypeForm
          key={knowledgeType?.id ?? "new"}
          knowledgeType={knowledgeType}
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

function TypeForm({
  knowledgeType,
  onCancel,
  onSaved,
}: {
  knowledgeType: EditableType | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const editing = !!knowledgeType;
  const [name, setName] = useState(knowledgeType?.name ?? "");
  const [slug, setSlug] = useState(knowledgeType?.slug ?? "");
  const [slugTouched, setSlugTouched] = useState(editing);
  const [color, setColor] = useState(knowledgeType?.color || DEFAULT_COLOR);
  const [description, setDescription] = useState(knowledgeType?.description ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const effectiveSlug = slugTouched ? slug : slugify(name);
  const slugChanged = editing && effectiveSlug !== knowledgeType.slug;
  const trimmedName = name.trim();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!trimmedName) return;
    setSaving(true);
    setError(null);
    const body: Record<string, unknown> = { name: trimmedName, color, description };
    if (effectiveSlug) body.slug = effectiveSlug;
    try {
      if (editing) {
        await api(`/api/knowledge-types/${knowledgeType.id}`, { method: "PUT", body });
      } else {
        await api("/api/knowledge-types", { method: "POST", body });
      }
      onSaved();
    } catch (err) {
      setError(errorText(err, "Không lưu được kiểu tri thức"));
      setSaving(false);
    }
  };

  const isPreset = TYPE_COLORS.some((c) => c.toLowerCase() === color.toLowerCase());

  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
      <DialogTitle className="text-lg font-semibold">{editing ? "Sửa kiểu tri thức" : "Thêm kiểu tri thức"}</DialogTitle>

      <div className="flex items-center gap-3 rounded-lg border border-dashed bg-muted/30 px-3 py-2.5">
        <span className="text-xs text-muted-foreground">Xem trước</span>
        <TypePill name={trimmedName || "Tên kiểu tri thức"} color={color} />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="kt-name">Tên kiểu tri thức</Label>
        <Input
          id="kt-name"
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="VD: Quy định nội bộ"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="kt-slug">
          Mã định danh <span className="text-[11px] font-normal text-muted-foreground">(dùng trong URL/bộ lọc)</span>
        </Label>
        <Input
          id="kt-slug"
          value={effectiveSlug}
          onChange={(e) => {
            setSlugTouched(true);
            setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""));
          }}
          placeholder="quy-dinh-noi-bo"
          className="font-mono text-xs"
        />
        {slugChanged && (
          <p className="text-[11px] text-amber-600 dark:text-amber-400">Đổi mã sẽ làm hỏng các liên kết cũ dùng mã này.</p>
        )}
      </div>

      <div className="space-y-1.5">
        <Label>Màu</Label>
        <div className="flex flex-wrap items-center gap-2">
          {TYPE_COLORS.map((c) => {
            const active = c.toLowerCase() === color.toLowerCase();
            return (
              <button
                key={c}
                type="button"
                aria-label={c}
                aria-pressed={active}
                onClick={() => setColor(c)}
                className={cn(
                  "size-7 rounded-full border-2 transition-transform",
                  active ? "scale-110 border-foreground" : "border-transparent hover:scale-105"
                )}
                style={{ backgroundColor: c }}
              />
            );
          })}
          <label
            title="Chọn màu khác"
            className={cn(
              "relative flex size-7 cursor-pointer items-center justify-center rounded-full border-2 bg-[conic-gradient(#ef4444,#f59e0b,#10b981,#3b82f6,#8b5cf6,#ec4899,#ef4444)] transition-transform hover:scale-105",
              !isPreset ? "scale-110 border-foreground" : "border-transparent"
            )}
          >
            <span className="flex size-4 items-center justify-center rounded-full bg-background">
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                add
              </span>
            </span>
            <input
              type="color"
              value={/^#[0-9a-fA-F]{6}$/.test(color) ? color : DEFAULT_COLOR}
              onChange={(e) => setColor(e.target.value)}
              className="absolute inset-0 cursor-pointer opacity-0"
              aria-label="Chọn màu khác"
            />
          </label>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="kt-desc">Mô tả</Label>
        <Textarea
          id="kt-desc"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Loại tài liệu nào thuộc kiểu tri thức này..."
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
          Hủy
        </Button>
        <Button type="submit" disabled={saving || !trimmedName}>
          {saving ? "Đang lưu..." : editing ? "Lưu thay đổi" : "Tạo kiểu tri thức"}
        </Button>
      </div>
    </form>
  );
}
