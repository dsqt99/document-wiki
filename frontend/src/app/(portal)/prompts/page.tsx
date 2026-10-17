"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import {
  Chip,
  IconBtn,
  LibraryCard,
  ScopeChip,
  ScopeFilterBar,
  countByScope,
  filterByScope,
  fmtDate,
  type ScopeFilter,
} from "@/components/shared/library-list";
import { PromptDialog, type PromptInitial, type PromptTemplate } from "@/components/prompts/prompt-dialog";
import { errMessage, TONE } from "@/components/skills/skill-utils";
import { Toast, useToast } from "@/components/skills/toast";

type DialogState = { key: number; prompt?: PromptTemplate; initial?: PromptInitial };

export default function PromptsPage() {
  const { user } = useAuth();
  const toast = useToast(3000);

  const [departments, setDepartments] = useState<{ id: string; name: string }[]>([]);
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState<ScopeFilter>("all");
  const [deptFilter, setDeptFilter] = useState<string[]>([]);
  const [tag, setTag] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogState | null>(null);

  useEffect(() => {
    let alive = true;
    api<{ id: string; name: string }[]>("/api/departments")
      .then((d) => alive && setDepartments(Array.isArray(d) ? d : []))
      .catch(() => alive && setDepartments([]));
    return () => {
      alive = false;
    };
  }, []);

  // Server-side search, 200ms after the last keystroke.
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      const qs = new URLSearchParams({ limit: "500" });
      const q = search.trim();
      if (q) qs.set("q", q);
      api<{ items: PromptTemplate[] }>(`/api/prompts?${qs.toString()}`)
        .then((r) => alive && setPrompts(r?.items ?? []))
        .catch(() => alive && setPrompts([]))
        .finally(() => alive && setLoaded(true));
    }, 200);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [search]);

  const allTags = [...new Set(prompts.flatMap((p) => p.tags ?? []))].sort((a, b) => a.localeCompare(b));
  const byTag = tag ? prompts.filter((p) => p.tags?.includes(tag)) : prompts;
  const counts = countByScope(byTag, deptFilter);
  const visible = filterByScope(byTag, scope, deptFilter);
  const filtering = !!search.trim() || !!tag || scope !== "all" || deptFilter.length > 0;

  const openDialog = (next: Omit<DialogState, "key">) => setDialog({ ...next, key: Date.now() });

  const copy = async (p: PromptTemplate) => {
    try {
      await navigator.clipboard.writeText(p.content);
      toast.show("Đã sao chép nội dung");
    } catch {
      // clipboard blocked: stay silent
    }
  };

  const remove = async (p: PromptTemplate) => {
    if (!confirm(`Xóa prompt "${p.title}" (/${p.command})?`)) return;
    try {
      await api(`/api/prompts/${p.id}`, { method: "DELETE" });
      setPrompts((list) => list.filter((x) => x.id !== p.id));
      toast.show("Đã xóa prompt");
    } catch (err) {
      alert(`Xóa thất bại: ${errMessage(err, "Lỗi không xác định")}`);
    }
  };

  const onSaved = (saved: PromptTemplate, wasEdit: boolean) => {
    setPrompts((list) => [saved, ...list.filter((x) => x.id !== saved.id)]);
    toast.show(wasEdit ? "Đã lưu prompt" : "Đã tạo prompt");
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Kho prompt"
        description="Mẫu yêu cầu dùng chung cho chatbot: trong ô chat gõ / rồi chọn lệnh để chèn. Mỗi cán bộ thấy prompt cá nhân, của đơn vị mình và toàn hệ thống."
        action={
          <Button size="sm" onClick={() => openDialog({})}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
            Tạo prompt
          </Button>
        }
      />

      <div className="flex flex-col gap-2">
        <ScopeFilterBar
          search={search}
          onSearch={setSearch}
          placeholder="Tìm theo tiêu đề, lệnh, nội dung..."
          scope={scope}
          onScope={setScope}
          counts={counts}
          departments={departments}
          department={deptFilter}
          onDepartment={setDeptFilter}
          total={`${visible.length} prompt`}
        />
        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {allTags.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTag((cur) => (cur === t ? null : t))}
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                  tag === t
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                #{t}
              </button>
            ))}
          </div>
        )}
      </div>

      {!loaded ? (
        <div className="flex justify-center py-16">
          <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: 36 }}>
            progress_activity
          </span>
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          icon="chat_paste_go"
          title={filtering ? "Không có prompt phù hợp" : "Chưa có prompt nào"}
          description="Tạo mẫu yêu cầu dùng lại cho các việc thường gặp: tóm tắt, soạn báo cáo, kiểm tra thể thức..."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((p) => {
            const owner = p.owner_id && p.owner_id === user?.id ? "Bạn" : p.owner_name || "—";
            const open = expanded === p.id;
            return (
              <LibraryCard
                key={p.id}
                icon="chat_paste_go"
                title={p.title}
                badge={`/${p.command}`}
                description={p.description}
                meta={`${owner} · ${fmtDate(p.updated_at)}`}
                actions={
                  <>
                    <IconBtn icon="content_copy" title="Sao chép nội dung" onClick={() => void copy(p)} />
                    <IconBtn
                      icon="library_add"
                      title="Nhân bản"
                      onClick={() =>
                        openDialog({
                          initial: {
                            title: `${p.title} (bản sao)`,
                            command: `${p.command}-2`,
                            description: p.description,
                            content: p.content,
                            tags: p.tags,
                            scope_type: "personal",
                            department_ids: [],
                          },
                        })
                      }
                    />
                    {p.can_edit && <IconBtn icon="edit" title="Sửa" onClick={() => openDialog({ prompt: p })} />}
                    {p.can_edit && <IconBtn icon="delete" title="Xóa" danger onClick={() => void remove(p)} />}
                  </>
                }
                chips={
                  <>
                    <ScopeChip scopeType={p.scope_type} departmentNames={p.department_names} />
                    {p.source === "chatbot" && (
                      <Chip icon="smart_toy" cls={TONE.violet}>
                        Từ chatbot
                      </Chip>
                    )}
                    {(p.tags ?? []).map((t) => (
                      <span key={t}>#{t}</span>
                    ))}
                  </>
                }
              >
                <button
                  type="button"
                  title={open ? "Thu gọn" : "Xem đầy đủ"}
                  onClick={() => setExpanded(open ? null : p.id)}
                  className={cn(
                    "rounded-lg bg-muted/50 px-3 py-2 text-left text-xs leading-[1.625] whitespace-pre-wrap text-foreground/80 transition-colors hover:bg-muted",
                    !open && "line-clamp-4",
                  )}
                >
                  {p.content}
                </button>
              </LibraryCard>
            );
          })}
        </div>
      )}

      <Toast message={toast.message} />

      {dialog && (
        <PromptDialog
          key={dialog.key}
          open
          onOpenChange={(o) => !o && setDialog(null)}
          prompt={dialog.prompt}
          initial={dialog.initial}
          departments={departments}
          onSaved={(saved) => onSaved(saved, !!dialog.prompt)}
        />
      )}
    </div>
  );
}
