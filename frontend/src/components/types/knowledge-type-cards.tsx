"use client";

import { useState } from "react";
import { errorText, hexAlpha, type KnowledgeType } from "@/components/knowledge/types";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

type Props = {
  types: KnowledgeType[];
  loading: boolean;
  onEdit: (type: KnowledgeType) => void;
  onRefresh: () => void;
  onCreate: () => void;
  onViewDocuments: (typeId: string) => void;
};

function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <span className="material-symbols-outlined" style={{ fontSize: size }}>
      {name}
    </span>
  );
}

/** Card grid for the "Kiểu tri thức" tab of /knowledge. */
export function KnowledgeTypeCards({ types, loading, onEdit, onRefresh, onCreate, onViewDocuments }: Props) {
  const [error, setError] = useState<string | null>(null);

  const remove = async (kt: KnowledgeType) => {
    const n = kt.source_count ?? 0;
    const msg =
      n > 0
        ? `Xóa kiểu tri thức "${kt.name}"? ${n} tài liệu sẽ chuyển về "Chưa phân loại".`
        : `Xóa kiểu tri thức "${kt.name}"?`;
    if (!confirm(msg)) return;
    setError(null);
    try {
      await api(`/api/knowledge-types/${kt.id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      setError(errorText(err, "Không xóa được kiểu tri thức"));
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <span className="material-symbols-outlined animate-spin" style={{ fontSize: 30 }}>
          progress_activity
        </span>
      </div>
    );
  }

  if (types.length === 0) {
    return (
      <div className="rounded-xl border bg-card">
        <EmptyState
          icon="category"
          title="Chưa có kiểu tri thức"
          description="Tạo kiểu tri thức để phân loại tài liệu, ví dụ: Văn bản luật, Quy định nội bộ."
          action={
            <Button size="sm" onClick={onCreate}>
              Thêm kiểu tri thức
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <span className="material-symbols-outlined shrink-0" style={{ fontSize: 16 }}>
            error
          </span>
          <span className="flex-1">{error}</span>
          <button type="button" aria-label="Đóng" onClick={() => setError(null)} className="opacity-70 hover:opacity-100">
            <Icon name="close" />
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {types.map((kt) => {
          const count = kt.source_count ?? 0;
          return (
            <div
              key={kt.id}
              className="flex flex-col gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-primary/30"
            >
              <div className="flex items-start gap-3">
                <span
                  className="flex size-9 shrink-0 items-center justify-center rounded-lg"
                  style={{ backgroundColor: hexAlpha(kt.color, 0.1), color: kt.color }}
                >
                  <Icon name="folder" size={20} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold" title={kt.name}>
                    {kt.name}
                  </p>
                  <p className="truncate font-mono text-[11px] text-muted-foreground">{kt.slug}</p>
                </div>
                <span className="shrink-0 rounded-full bg-secondary px-2 py-0.5 text-[11px] text-secondary-foreground tabular-nums">
                  {count} tài liệu
                </span>
              </div>
              <p className="line-clamp-2 min-h-8 text-xs text-muted-foreground">
                {kt.description ? kt.description : <span className="italic opacity-60">Chưa có mô tả</span>}
              </p>
              <div className="flex items-center gap-1 border-t pt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-primary hover:text-primary"
                  disabled={count === 0}
                  onClick={() => onViewDocuments(kt.id)}
                >
                  Xem tài liệu
                  <Icon name="arrow_forward" size={14} />
                </Button>
                <div className="ml-auto flex items-center gap-0.5">
                  <Button variant="ghost" size="icon-sm" title="Sửa" aria-label="Sửa" onClick={() => onEdit(kt)}>
                    <Icon name="edit" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title="Xóa"
                    aria-label="Xóa"
                    className="text-destructive hover:text-destructive"
                    onClick={() => void remove(kt)}
                  >
                    <Icon name="delete" />
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
