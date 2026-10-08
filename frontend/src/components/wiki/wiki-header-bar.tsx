"use client";

import Link from "next/link";
import { WikiScope } from "@/types/wiki";
import { useAuth } from "@/lib/auth";

const BTN =
  "inline-flex h-9 items-center gap-1.5 px-3 rounded-lg text-sm font-medium border border-border bg-background hover:bg-muted transition-colors cursor-pointer";

/**
 * Wiki index header: title + subtitle on the left, actions on the right.
 */
export function WikiHeaderBar({
  scope,
  onSearch,
  createMode,
  onCreate,
}: {
  scope: WikiScope;
  onSearch: () => void;
  createMode: "direct" | "propose" | null;
  onCreate: () => void;
}) {
  const { user } = useAuth();

  return (
    <div className="flex items-start gap-4 flex-wrap">
      <div className="min-w-0 mr-auto">
        <Link href="/wiki" className="font-heading text-3xl tracking-tight text-foreground hover:text-primary transition-colors">
          Wiki
        </Link>
        <p className="text-sm text-muted-foreground mt-1">
          Kho tri thức tổng hợp từ các văn bản, tài liệu nội bộ — tra cứu, liên kết và đóng góp.
        </p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <button type="button" onClick={onSearch} className={BTN} title="Tìm kiếm (Ctrl+K)">
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>search</span>
          <span className="hidden sm:inline">Tìm kiếm</span>
          <kbd className="hidden lg:inline-block ml-0.5 px-1.5 py-px rounded border border-border text-[11px] font-mono text-muted-foreground">
            ⌘K
          </kbd>
        </button>
        {createMode && (
          <button
            type="button"
            onClick={onCreate}
            className={BTN}
            title={
              createMode === "direct"
                ? `Tạo trang mới trong ${scope.name}`
                : `Đề xuất trang mới trong ${scope.name} (cần duyệt)`
            }
          >
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>add</span>
            <span className="hidden sm:inline">{createMode === "direct" ? "Trang mới" : "Đề xuất trang"}</span>
          </button>
        )}
        {user && (
          <Link href="/wiki/review" className={BTN} title="Bản nháp của bạn và bản nháp chờ duyệt">
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>edit_note</span>
            <span className="hidden sm:inline">Đóng góp</span>
          </Link>
        )}
        <Link
          href="/wiki/graph"
          className="inline-flex h-9 items-center gap-1.5 px-3 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>hub</span>
          <span className="hidden sm:inline">Xem sơ đồ</span>
        </Link>
      </div>
    </div>
  );
}
