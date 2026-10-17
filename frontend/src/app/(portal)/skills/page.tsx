"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { ScopeFilterBar, countByScope, filterByScope, type ScopeFilter } from "@/components/shared/library-list";
import { ContributeDialog } from "@/components/skills/contribute-dialog";
import {
  ContributionEditorDialog,
  ContributionReviewDialog,
  EDITOR_LABELS_VI,
  REVIEW_LABELS_VI,
  type ReviewOutcome,
} from "@/components/skills/contribution-dialogs";
import { MyContributions } from "@/components/skills/my-contributions";
import { PendingReviews } from "@/components/skills/pending-reviews";
import { SkillComposeDialog, type SkillComposeInitial } from "@/components/skills/skill-compose-dialog";
import { SkillGrid } from "@/components/skills/skill-grid";
import { SkillRenameDialog } from "@/components/skills/skill-rename-dialog";
import { SkillReuploadDialog } from "@/components/skills/skill-reupload-dialog";
import { SkillUploadDialog } from "@/components/skills/skill-upload-dialog";
import { errMessage } from "@/components/skills/skill-utils";
import { Toast, useToast } from "@/components/skills/toast";
import type { Department, PendingContribution, Skill, SkillContent, SkillListResponse } from "@/components/skills/types";

const POLL_MS = 3000;
const isBusy = (s: Skill) => s.status === "processing" || s.status === "deleting";

type ComposeState = {
  key: number;
  mode: "create" | "edit";
  slug?: string;
  initial?: SkillComposeInitial;
};

export default function SkillsPage() {
  const { canAccess } = useAuth();
  const canCreate = canAccess("skill", "create");
  const toast = useToast(4000);

  const [departments, setDepartments] = useState<Department[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState<ScopeFilter>("all");
  const [deptFilter, setDeptFilter] = useState<string[]>([]);

  const [compose, setCompose] = useState<ComposeState | null>(null);
  const [contributeOpen, setContributeOpen] = useState(false);
  const [editorId, setEditorId] = useState<string | null>(null);
  const [myKey, setMyKey] = useState(0);
  const [pending, setPending] = useState<PendingContribution[] | undefined>(undefined);
  const [reviewing, setReviewing] = useState<PendingContribution | null>(null);
  const [renaming, setRenaming] = useState<Skill | null>(null);
  const [reuploading, setReuploading] = useState<Skill | null>(null);

  useEffect(() => {
    let alive = true;
    api<Department[]>("/api/departments")
      .then((d) => alive && setDepartments(Array.isArray(d) ? d : []))
      .catch(() => alive && setDepartments([]));
    return () => {
      alive = false;
    };
  }, []);

  const load = useCallback((q: string) => {
    const qs = new URLSearchParams({ limit: "2000" });
    if (q) qs.set("q", q);
    return api<SkillListResponse>(`/api/skills?${qs.toString()}`)
      .then((r) => {
        setSkills(r?.items ?? []);
        setTotal(r?.total ?? 0);
      })
      .catch(() => {
        setSkills([]);
        setTotal(0);
      });
  }, []);

  const reload = useCallback(() => void load(query), [load, query]);

  // Server-side search, 200ms after the last keystroke (and once on entry).
  useEffect(() => {
    const timer = setTimeout(() => void load(query), 200);
    return () => clearTimeout(timer);
  }, [query, load]);

  // Poll skills that are still being processed or deleted.
  const watchKey = skills
    .filter(isBusy)
    .map((s) => `${s.id}:${s.status}`)
    .join(",");
  useEffect(() => {
    if (!watchKey) return;
    const ids = watchKey.split(",").map((p) => p.split(":")[0]);
    const timer = setInterval(() => {
      const qs = new URLSearchParams({ limit: "2000" });
      ids.forEach((id) => qs.append("ids", id));
      api<SkillListResponse>(`/api/skills?${qs.toString()}`)
        .then((r) => {
          const fresh = new Map((r?.items ?? []).map((s) => [s.id, s]));
          const gone = ids.filter((id) => !fresh.has(id));
          setSkills((list) =>
            list
              .filter((s) => !gone.includes(s.id))
              .map((s) => {
                const next = fresh.get(s.id);
                return next && JSON.stringify(next) !== JSON.stringify(s) ? next : s;
              }),
          );
          if (gone.length) setTotal((t) => Math.max(0, t - gone.length));
        })
        .catch((err) => console.error("Skill status poll failed", err));
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [watchKey]);

  const scoped = filterByScope(skills, scope, deptFilter);
  const counts = countByScope(skills, deptFilter);

  const openCompose = (next: Omit<ComposeState, "key">) => setCompose({ ...next, key: Date.now() });

  const clone = async (s: Skill) => {
    try {
      const c = await api<SkillContent>(`/api/skills/${encodeURIComponent(s.slug)}/content`);
      openCompose({
        mode: "create",
        initial: { name: `${c.name || s.name}-tuy-chinh`.slice(0, 80), description: c.description, body: c.body },
      });
    } catch (err) {
      alert(`Không tải được nội dung: ${errMessage(err, "Lỗi không xác định")}`);
    }
  };

  const remove = async (s: Skill) => {
    const question = s.is_system
      ? `Gỡ kỹ năng hệ thống "${s.name}" khỏi thư viện? Trợ lý sẽ không dùng kỹ năng này nữa và lần khởi động sau không tự nạp lại.`
      : `Xóa kỹ năng "${s.name}"? Trợ lý sẽ không dùng được kỹ năng này nữa.`;
    if (!confirm(question)) return;
    try {
      await api(`/api/skills/${s.id}`, { method: "DELETE" });
      toast.show(s.is_system ? "Đã gỡ kỹ năng hệ thống" : "Đang xóa kỹ năng");
      reload();
    } catch (err) {
      alert(`Xóa thất bại: ${errMessage(err, "Lỗi không xác định")}`);
    }
  };

  const openEditor = (id: string | null) => {
    setEditorId(id);
    setMyKey((k) => k + 1);
  };

  const onReviewSettled = ({ action, ok }: ReviewOutcome) => {
    if (ok) toast.show(action === "approve" ? "Đã duyệt và hợp nhất đề xuất" : "Đã từ chối đề xuất");
    const id = reviewing?.id;
    setReviewing(null);
    if (id) setPending((list) => (list ?? []).filter((c) => c.id !== id));
    reload();
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Thư viện kỹ năng"
        description="Bộ hướng dẫn trợ lý AI tự đọc khi gặp đúng loại yêu cầu. Bấm vào thẻ để xem chi tiết, sửa hoặc nhân bản."
        action={
          canCreate ? (
            <>
              <ContributeDialog
                open={contributeOpen}
                onOpenChange={setContributeOpen}
                allDepartments={departments}
                onContributionCreated={(id) => {
                  setContributeOpen(false);
                  openEditor(id);
                }}
                trigger={
                  <Button variant="ghost" size="sm" className="text-muted-foreground" title="Soạn kỹ năng nhiều tệp và gửi duyệt">
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>edit_square</span>
                    Soạn nhiều tệp
                  </Button>
                }
              />
              <SkillUploadDialog departments={departments} onUploaded={reload} />
              <Button size="sm" onClick={() => openCompose({ mode: "create" })}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
                Tạo kỹ năng
              </Button>
            </>
          ) : undefined
        }
      />

      <div className="grid grid-cols-1 gap-3 empty:hidden lg:grid-cols-2">
        <MyContributions key={myKey} departments={departments} onOpen={openEditor} onChanged={reload} />
        <PendingReviews items={pending} onLoaded={setPending} onOpen={setReviewing} />
      </div>

      <div className="flex flex-col gap-4">
        <ScopeFilterBar
          search={search}
          onSearch={(q) => {
            setSearch(q);
            setQuery(q);
          }}
          placeholder="Tìm theo tên, mô tả..."
          scope={scope}
          onScope={setScope}
          counts={counts}
          withPersonal={false}
          departments={departments}
          department={deptFilter}
          onDepartment={setDeptFilter}
          total={`${scoped.length} kỹ năng`}
        />
        <SkillGrid
          skills={scoped}
          onClone={(s) => void clone(s)}
          onEdit={(s) => openCompose({ mode: "edit", slug: s.slug })}
          onDelete={(s) => void remove(s)}
          onRename={setRenaming}
          onReupload={setReuploading}
        />
      </div>

      <Toast message={toast.message} />

      {compose && (
        <SkillComposeDialog
          key={compose.key}
          open
          onOpenChange={(o) => !o && setCompose(null)}
          mode={compose.mode}
          slug={compose.slug}
          initial={compose.initial}
          departments={departments}
          onSaved={(msg) => {
            toast.show(msg);
            reload();
          }}
        />
      )}

      {renaming && (
        <SkillRenameDialog
          key={renaming.id}
          skill={renaming}
          departments={departments}
          onClose={() => setRenaming(null)}
          onSaved={reload}
        />
      )}

      <SkillReuploadDialog
        skill={reuploading}
        onClose={() => setReuploading(null)}
        onUploaded={reload}
      />

      <ContributionEditorDialog
        contributionId={editorId}
        labels={EDITOR_LABELS_VI}
        onClose={() => openEditor(null)}
        onSubmitted={() => {
          toast.show("Đã gửi đề xuất để duyệt");
          openEditor(null);
          reload();
        }}
        onDeleted={() => {
          openEditor(null);
          reload();
        }}
      />

      <ContributionReviewDialog
        contribution={reviewing ? { id: reviewing.id, contributorName: reviewing.contributor_name } : null}
        labels={REVIEW_LABELS_VI}
        onClose={() => setReviewing(null)}
        onSettled={onReviewSettled}
      />
    </div>
  );
}
