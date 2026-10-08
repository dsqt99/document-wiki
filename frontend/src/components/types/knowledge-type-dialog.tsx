"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeType: KnowledgeType | null;
  onSaved: () => void;
};

const PRESET_COLORS = [
  "#6B7280", "#10B981", "#8B5CF6", "#F59E0B",
  "#3B82F6", "#EF4444", "#EC4899", "#14B8A6",
  "#F97316", "#6366F1",
];

/** ASCII slug from a Vietnamese name — the server's own fallback drops accented letters. */
function slugify(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function KnowledgeTypeDialog({ open, onOpenChange, knowledgeType, onSaved }: Props) {
  const isEdit = !!knowledgeType;
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [color, setColor] = useState("#6366F1");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const colorInputRef = useRef<HTMLInputElement>(null);

  // Reset the form whenever the dialog opens or targets another type (state adjusted during render).
  const formKey = open ? knowledgeType?.id || "new" : "";
  const [prevKey, setPrevKey] = useState("");
  if (formKey !== prevKey) {
    setPrevKey(formKey);
    setName(knowledgeType?.name || "");
    setSlug(knowledgeType?.slug || "");
    setSlugTouched(!!knowledgeType);
    setColor(knowledgeType?.color || "#6366F1");
    setDescription(knowledgeType?.description || "");
    setError("");
  }

  const effectiveSlug = slugTouched ? slug : slugify(name);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      const body = { name: name.trim(), slug: effectiveSlug || undefined, color, description };
      if (isEdit) await api(`/api/knowledge-types/${knowledgeType.id}`, { method: "PUT", body });
      else await api("/api/knowledge-types", { method: "POST", body });
      onSaved();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không lưu được danh mục");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg">{isEdit ? "Sửa danh mục" : "Thêm danh mục"}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="mt-1 flex flex-col gap-4">
          {/* Live preview — how the pill appears in the document table */}
          <div className="flex items-center gap-2 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2.5">
            <span className="text-[11px] text-muted-foreground">Xem trước</span>
            <span
              className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium"
              style={{ borderColor: `${color}55`, color, backgroundColor: `${color}12` }}
            >
              {name.trim() || "Tên danh mục"}
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Tên danh mục</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Quy định nội bộ"
              required
              autoFocus
              className="bg-background"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="flex items-center gap-1">
              Mã định danh
              <span className="text-[11px] font-normal text-muted-foreground">(dùng trong URL/bộ lọc)</span>
            </Label>
            <Input
              value={effectiveSlug}
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""));
              }}
              placeholder="quy-dinh-noi-bo"
              className="bg-background font-mono text-xs"
            />
            {isEdit && slug !== knowledgeType.slug && (
              <p className="text-[11px] text-amber-600">Đổi mã sẽ làm hỏng các liên kết cũ dùng mã này.</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Màu</Label>
            <div className="flex flex-wrap gap-2">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={cn(
                    "size-7 rounded-full border-2 transition-all cursor-pointer",
                    color.toLowerCase() === c.toLowerCase() ? "border-foreground scale-110" : "border-transparent",
                  )}
                  style={{ backgroundColor: c }}
                  aria-label={c}
                />
              ))}
              <div className="relative size-7">
                <button
                  type="button"
                  onClick={() => colorInputRef.current?.click()}
                  className="size-7 rounded-full p-[2px] transition-all hover:scale-110 cursor-pointer"
                  style={{ background: "conic-gradient(#f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00)" }}
                  title="Chọn màu khác"
                >
                  <span className="flex size-full items-center justify-center rounded-full bg-background">
                    <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 14 }}>add</span>
                  </span>
                </button>
                <input
                  ref={colorInputRef}
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="pointer-events-none absolute inset-0 opacity-0"
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Mô tả</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Loại tài liệu nào thuộc danh mục này..."
              rows={2}
              className="bg-background"
            />
          </div>

          {error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Hủy
            </Button>
            <Button type="submit" size="sm" disabled={saving || !name.trim()}>
              {saving ? "Đang lưu..." : isEdit ? "Lưu thay đổi" : "Tạo danh mục"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
