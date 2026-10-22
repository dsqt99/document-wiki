"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/lib/auth";
import type { Department } from "./types";

export function ManagingDepartmentSelect({ departments, value, onChange, disabled, action = "edit", currentName }: {
  departments: Department[]; value: string; onChange: (value: string) => void; disabled?: boolean;
  action?: "create" | "edit"; currentName?: string | null;
}) {
  const { user, hasPermission } = useAuth();
  const options = user?.role === "admin" || hasPermission(`doc:${action}:all`) ? departments : departments.filter((department) => (user?.scope_department_ids ?? user?.department_ids)?.includes(department.id));
  const selected = departments.find((department) => department.id === value)?.name || currentName;
  return <div className="space-y-1.5">
    <Select value={value || "__none__"} onValueChange={(next) => onChange(next === "__none__" ? "" : next || "")} disabled={disabled}>
      <SelectTrigger aria-label="Phòng ban quản lý tài liệu" className="h-9 w-full text-sm"><SelectValue>{() => selected && value ? selected : "Chưa chỉ định"}</SelectValue></SelectTrigger>
      <SelectContent><SelectItem value="__none__">Chưa chỉ định</SelectItem>{value && !options.some((department) => department.id === value) && <SelectItem value={value} disabled>{selected || "Phòng ban hiện tại"}</SelectItem>}{options.map((department) => <SelectItem key={department.id} value={department.id}>{department.name}</SelectItem>)}</SelectContent>
    </Select>
    <p className="text-[11px] text-muted-foreground">Đơn vị phụ trách tài liệu; không thay đổi phạm vi người được xem.</p>
  </div>;
}
