"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Chip, IconBtn, LibraryCard, ScopeChip, fmtDate } from "@/components/shared/library-list";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TONE } from "./skill-utils";
import type { Skill, SkillContent } from "./types";

const LAZY_BATCH = 60;
const LAZY_WORKERS = 4;

const STATUS_CHIP: Record<string, { label: string; cls: string; spin?: boolean }> = {
  processing: { label: "Đang xử lý", cls: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-300", spin: true },
  deleting: { label: "Đang xóa", cls: TONE.red, spin: true },
  error: { label: "Lỗi", cls: TONE.red },
  failed: { label: "Lỗi", cls: TONE.red },
};

/**
 * Card descriptions are not part of the list response; fetch them in the background for the
 * cards on screen (a bounded batch, a few requests in flight) and cache them by slug.
 */
function useLazyDescriptions(skills: Skill[]) {
  const [descs, setDescs] = useState<Record<string, string>>({});
  const requested = useRef<Set<string>>(new Set());
  const known = useRef<Record<string, string>>({});

  const visibleKey = skills.map((s) => s.slug).join("|");

  useEffect(() => {
    const queue = skills
      .filter((s) => !s.description && !(s.slug in known.current) && !requested.current.has(s.slug))
      .slice(0, LAZY_BATCH)
      .map((s) => s.slug);
    if (queue.length === 0) return;
    const asked = requested.current;
    queue.forEach((slug) => asked.add(slug));

    let cancelled = false;
    const pending = [...queue];
    const worker = async () => {
      while (!cancelled && pending.length) {
        const slug = pending.shift()!;
        try {
          const c = await api<SkillContent>(`/api/skills/${encodeURIComponent(slug)}/content`);
          const text = c?.description ?? "";
          known.current[slug] = text;
          if (!cancelled && text) setDescs((d) => ({ ...d, [slug]: text }));
        } catch {
          // a card simply stays without a description
          known.current[slug] = "";
        }
      }
    };
    for (let i = 0; i < LAZY_WORKERS; i++) void worker();

    return () => {
      cancelled = true;
      // Slugs never started may be asked for again by the next visible list.
      pending.forEach((slug) => asked.delete(slug));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the visible slugs only
  }, [visibleKey]);

  return descs;
}

export type SkillCardActions = {
  onClone: (s: Skill) => void;
  onEdit: (s: Skill) => void;
  onDelete: (s: Skill) => void;
  onRename: (s: Skill) => void;
  onReupload: (s: Skill) => void;
};

function MoreMenu({ skill, onRename, onReupload }: { skill: Skill } & Pick<SkillCardActions, "onRename" | "onReupload">) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        title="Thao tác khác"
        aria-label="Thao tác khác"
        className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>more_vert</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52 rounded-xl">
        <DropdownMenuItem onClick={() => onRename(skill)}>
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>tune</span>
          {skill.is_system ? "Đổi phạm vi" : "Đổi tên / phạm vi"}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => onReupload(skill)}>
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>upload_file</span>
          Tải phiên bản mới (ZIP)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Card grid of the skill library (1 / 2 / 3 columns). */
export function SkillGrid({ skills, ...actions }: { skills: Skill[] } & SkillCardActions) {
  const router = useRouter();
  const { user, canAccess } = useAuth();
  const isAdmin = user?.role === "admin";
  const canCreate = canAccess("skill", "create");
  const canEdit = canAccess("skill", "edit");
  const canDelete = canAccess("skill", "delete");
  const descs = useLazyDescriptions(skills);

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {skills.map((s) => {
        const editable = canEdit && (!s.is_system || isAdmin);
        const deletable = canDelete && (!s.is_system || isAdmin);
        const st = STATUS_CHIP[s.status];
        return (
          <LibraryCard
            key={s.id}
            icon={s.is_system ? "verified" : "auto_awesome"}
            iconCls={s.is_system ? "bg-amber-500/15 text-amber-700 dark:text-amber-300" : undefined}
            title={s.name}
            description={s.description || descs[s.slug]}
            onOpen={() => router.push(`/skills/${s.slug}`)}
            meta={fmtDate(s.updated_at)}
            actions={
              canCreate || editable || deletable ? (
                <>
                  {canCreate && <IconBtn icon="library_add" title="Nhân bản" onClick={() => actions.onClone(s)} />}
                  {editable && <IconBtn icon="edit" title="Sửa nội dung" onClick={() => actions.onEdit(s)} />}
                  {deletable && <IconBtn icon="delete" title="Xóa" danger onClick={() => actions.onDelete(s)} />}
                  {editable && <MoreMenu skill={s} onRename={actions.onRename} onReupload={actions.onReupload} />}
                </>
              ) : undefined
            }
            chips={
              <>
                <ScopeChip scopeType={s.scope_type} departmentNames={s.department_names} />
                {s.is_system && (
                  <Chip icon="verified" cls={TONE.amber}>
                    Hệ thống
                  </Chip>
                )}
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">v{s.current_version}</span>
                {st && (
                  <span className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5", st.cls)}>
                    {st.spin && (
                      <span className="material-symbols-outlined animate-spin" style={{ fontSize: 11 }}>
                        progress_activity
                      </span>
                    )}
                    {st.label}
                  </span>
                )}
              </>
            }
          />
        );
      })}
    </div>
  );
}
