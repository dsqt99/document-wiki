"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Bộ lọc + thẻ dùng chung cho Thư viện kỹ năng và Kho prompt (giữ hai trang đồng bộ). */

export type ScopeFilter = "all" | "global" | "department" | "personal";

export const SCOPE_FILTERS: { value: ScopeFilter; label: string; icon: string }[] = [
  { value: "all", label: "Tất cả", icon: "apps" },
  { value: "global", label: "Toàn hệ thống", icon: "public" },
  { value: "department", label: "Phòng ban", icon: "apartment" },
  { value: "personal", label: "Cá nhân", icon: "person" },
];

export const SCOPE_STYLE: Record<string, { label: string; icon: string; cls: string }> = {
  personal: { label: "Cá nhân", icon: "person", cls: "bg-muted text-muted-foreground" },
  department: { label: "Phòng ban", icon: "apartment", cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  global: { label: "Toàn hệ thống", icon: "public", cls: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
};

type Scoped = { scope_type?: string | null; department_ids?: string[] | null };

const normScope = (s?: string | null) => (s === "department" || s === "personal" ? s : "global");

/** Lọc theo phạm vi hiển thị và phòng ban quản lý (mục gán cho ít nhất một phòng ban đã chọn). */
export function filterByScope<T extends Scoped>(items: T[], scope: ScopeFilter, departments: string[]): T[] {
  return items.filter(
    (it) =>
      (scope === "all" || normScope(it.scope_type) === scope) &&
      (departments.length === 0 ||
        (it.scope_type === "department" && (it.department_ids || []).some((id) => departments.includes(id)))),
  );
}

export function countByScope<T extends Scoped>(items: T[], departments: string[]): Record<ScopeFilter, number> {
  const base = filterByScope(items, "all", departments);
  const c: Record<ScopeFilter, number> = { all: base.length, global: 0, department: 0, personal: 0 };
  base.forEach((it) => (c[normScope(it.scope_type) as ScopeFilter] += 1));
  return c;
}

export function fmtDate(s: string) {
  const d = new Date(s);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}

type FilterBarProps = {
  search: string;
  onSearch: (q: string) => void;
  placeholder: string;
  scope: ScopeFilter;
  onScope: (s: ScopeFilter) => void;
  counts: Record<ScopeFilter, number>;
  /** Ẩn mục "Cá nhân" khi loại dữ liệu không có phạm vi cá nhân. */
  withPersonal?: boolean;
  departments: { id: string; name: string }[];
  department: string[];
  onDepartment: (ids: string[]) => void;
  total: string;
};

export function ScopeFilterBar({
  search,
  onSearch,
  placeholder,
  scope,
  onScope,
  counts,
  withPersonal = true,
  departments,
  department,
  onDepartment,
  total,
}: FilterBarProps) {
  const scopes = SCOPE_FILTERS.filter((f) => withPersonal || f.value !== "personal");
  const current = SCOPE_FILTERS.find((f) => f.value === scope) || SCOPE_FILTERS[0];
  const selectedNames = departments.filter((d) => department.includes(d.id)).map((d) => d.name);
  const deptLabel =
    selectedNames.length === 0 ? "Phòng ban quản lý: Tất cả" : selectedNames.length === 1 ? selectedNames[0] : `${selectedNames[0]} +${selectedNames.length - 1}`;
  const deptTitle = selectedNames.length ? `Phòng ban quản lý: ${selectedNames.join(", ")}` : "Phòng ban quản lý";
  return (
    <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
      <div className="relative lg:w-72">
        <span className="material-symbols-outlined pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" style={{ fontSize: 18 }}>
          search
        </span>
        <Input value={search} onChange={(e) => onSearch(e.target.value)} placeholder={placeholder} className="h-9 pl-8 pr-8 text-sm" />
        {search && (
          <button
            type="button"
            aria-label="Xóa tìm kiếm"
            onClick={() => onSearch("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger className={triggerCls(scope !== "all")} aria-label="Phạm vi hiển thị" title="Phạm vi hiển thị">
            <span className="material-symbols-outlined" style={{ fontSize: 15 }}>{current.icon}</span>
            <span className="truncate">{scope === "all" ? "Phạm vi: Tất cả" : current.label}</span>
            <span className="tabular-nums text-[10px] text-muted-foreground">{counts[scope]}</span>
            <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>expand_more</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56 rounded-xl">
            <DropdownMenuRadioGroup value={scope} onValueChange={(v) => onScope(v as ScopeFilter)}>
              {scopes.map((f) => (
                <DropdownMenuRadioItem key={f.value} value={f.value} closeOnClick className="gap-2 py-1.5 text-xs">
                  <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 15 }}>{f.icon}</span>
                  <span className="flex-1">{f.label}</span>
                  <span className="tabular-nums text-[10px] text-muted-foreground">{counts[f.value]}</span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>

        {departments.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger className={triggerCls(department.length > 0)} aria-label="Phòng ban quản lý" title={deptTitle}>
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>apartment</span>
              <span className="max-w-[12rem] truncate">{deptLabel}</span>
              {department.length > 1 && (
                <span className="rounded-full bg-primary/15 px-1.5 text-[10px] font-bold text-primary">{department.length}</span>
              )}
              <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 16 }}>expand_more</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-64 rounded-xl">
              <div className="max-h-72 overflow-y-auto">
                {departments.map((d) => (
                  <DropdownMenuCheckboxItem
                    key={d.id}
                    checked={department.includes(d.id)}
                    onCheckedChange={(on) =>
                      onDepartment(on ? [...department, d.id] : department.filter((x) => x !== d.id))
                    }
                    className="py-1.5 text-xs"
                  >
                    {d.name}
                  </DropdownMenuCheckboxItem>
                ))}
              </div>
              {department.length > 0 && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => onDepartment([])} className="gap-2 py-1.5 text-xs text-muted-foreground">
                    <span className="material-symbols-outlined" style={{ fontSize: 15 }}>filter_alt_off</span>
                    Bỏ chọn tất cả
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      <span className="text-xs text-muted-foreground tabular-nums lg:ml-auto">{total}</span>
    </div>
  );
}

function triggerCls(active: boolean) {
  return cn(
    "inline-flex h-9 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
    active ? "border-primary/40 bg-primary/5 text-foreground" : "border-input bg-background text-muted-foreground hover:text-foreground",
  );
}

export function ScopeChip({ scopeType, departmentNames }: { scopeType?: string | null; departmentNames?: string[] | null }) {
  const s = normScope(scopeType);
  const sc = SCOPE_STYLE[s];
  const names = departmentNames || [];
  const label =
    s === "department" && names.length
      ? names.length > 2
        ? `${names.slice(0, 2).join(", ")} +${names.length - 2}`
        : names.join(", ")
      : sc.label;
  return (
    <Chip icon={sc.icon} cls={sc.cls} title={s === "department" ? names.join(", ") : undefined}>
      {label}
    </Chip>
  );
}

export function Chip({ icon, cls, title, children }: { icon?: string; cls: string; title?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1 truncate rounded-md px-1.5 py-0.5 font-medium", cls)} title={title}>
      {icon && <span className="material-symbols-outlined shrink-0" style={{ fontSize: 12 }}>{icon}</span>}
      <span className="truncate">{children}</span>
    </span>
  );
}

export function IconBtn({ icon, title, onClick, danger }: { icon: string; title: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted",
        danger ? "hover:text-destructive" : "hover:text-foreground",
      )}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{icon}</span>
    </button>
  );
}

type CardProps = {
  icon: string;
  iconCls?: string;
  title: string;
  /** Nhãn nhỏ cạnh tiêu đề, vd: /lenh */
  badge?: string;
  description?: string | null;
  /** Khối nội dung phụ (xem trước prompt...). */
  children?: ReactNode;
  actions?: ReactNode;
  chips: ReactNode;
  meta: string;
  onOpen?: () => void;
};

/** Thẻ thống nhất: biểu tượng · tiêu đề · mô tả · thao tác (nhân bản, sửa, xóa) · nhãn phạm vi · người/ngày. */
export function LibraryCard({ icon, iconCls, title, badge, description, children, actions, chips, meta, onOpen }: CardProps) {
  return (
    <div
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onClick={onOpen}
      onKeyDown={onOpen ? (e) => { if (e.key === "Enter" && e.target === e.currentTarget) onOpen(); } : undefined}
      className={cn(
        "group flex flex-col gap-2 rounded-xl border border-border/60 bg-background/40 p-4 text-left transition-colors hover:border-border hover:bg-background/70",
        onOpen && "cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
      )}
    >
      <div className="flex items-start gap-2.5">
        <div className={cn("mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", iconCls || "bg-primary/10 text-primary")}>
          <span className="material-symbols-outlined" style={{ fontSize: 18 }}>{icon}</span>
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-2 break-words text-sm font-semibold leading-snug text-foreground group-hover:text-primary" title={title}>{title}</h3>
          {badge && <span className="mt-1 inline-block max-w-full truncate rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{badge}</span>}
          <p className="mt-0.5 line-clamp-2 min-h-[2rem] text-xs text-muted-foreground">{description || " "}</p>
        </div>
        {actions && (
          <div
            className="flex shrink-0 items-center opacity-70 transition-opacity group-hover:opacity-100"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            {actions}
          </div>
        )}
      </div>
      {children}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        {chips}
        <span className="ml-auto tabular-nums">{meta}</span>
      </div>
    </div>
  );
}
