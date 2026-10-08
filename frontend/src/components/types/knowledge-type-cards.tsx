import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
  description?: string;
  sort_order: number;
  source_count?: number;
};

type Props = {
  types: KnowledgeType[];
  loading: boolean;
  onEdit: (type: KnowledgeType) => void;
  onRefresh: () => void;
  onCreate: () => void;
  onViewDocuments: (typeId: string) => void;
};

export function KnowledgeTypeCards({ types, loading, onEdit, onRefresh, onCreate, onViewDocuments }: Props) {
  const [error, setError] = useState("");

  const handleDelete = async (type: KnowledgeType) => {
    const n = type.source_count ?? 0;
    const msg = n
      ? `Xóa danh mục "${type.name}"? ${n} tài liệu sẽ chuyển về "Chưa phân loại".`
      : `Xóa danh mục "${type.name}"?`;
    if (!confirm(msg)) return;
    setError("");
    try {
      await api(`/api/knowledge-types/${type.id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xóa được danh mục");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined animate-spin text-3xl text-muted-foreground">progress_activity</span>
      </div>
    );
  }

  if (types.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card">
        <EmptyState
          icon="category"
          title="Chưa có danh mục"
          description="Tạo danh mục để phân loại tài liệu, ví dụ: Văn bản luật, Quy định nội bộ."
          action={<Button size="sm" onClick={onCreate}>Thêm danh mục</Button>}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {types.map((type) => {
          const n = type.source_count ?? 0;
          return (
            <div
              key={type.id}
              className="group flex flex-col rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/30"
            >
              <div className="flex items-start gap-3">
                <span
                  className="flex size-9 shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${type.color}1a`, color: type.color }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 20 }}>folder</span>
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="truncate text-sm font-semibold text-foreground">{type.name}</h3>
                  <p className="font-mono text-[11px] text-muted-foreground">{type.slug}</p>
                </div>
                <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium tabular-nums text-secondary-foreground">
                  {n} tài liệu
                </span>
              </div>

              <p className="mt-2 line-clamp-2 min-h-[2lh] text-xs text-muted-foreground">
                {type.description || <span className="italic opacity-60">Chưa có mô tả</span>}
              </p>

              <div className="mt-3 flex items-center gap-1 border-t border-border pt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs text-primary hover:text-primary"
                  disabled={n === 0}
                  onClick={() => onViewDocuments(type.id)}
                >
                  Xem tài liệu
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>arrow_forward</span>
                </Button>
                <div className="ml-auto flex items-center">
                  <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => onEdit(type)} title="Sửa">
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>edit</span>
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                    onClick={() => handleDelete(type)}
                    title="Xóa"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
                  </Button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
