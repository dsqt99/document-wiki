"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { EmptyState } from "@/components/shared/empty-state";
import { ContributeDialog } from "@/components/skills/contribute-dialog";
import {
  ContributionEditorDialog,
  ContributionReviewDialog,
  EDITOR_LABELS_EN,
  REVIEW_LABELS_EN,
  type ReviewOutcome,
} from "@/components/skills/contribution-dialogs";
import { PendingReviews } from "@/components/skills/pending-reviews";
import { SkillFileExplorer } from "@/components/skills/skill-file-explorer";
import { TONE, errDetail } from "@/components/skills/skill-utils";
import type { PendingContribution, Skill, SkillVersion } from "@/components/skills/types";

const sectionTitle = "text-[11px] font-bold tracking-[0.15em] text-muted-foreground uppercase";

function BackLink() {
  return (
    <Link
      href="/skills"
      className="inline-flex h-6 w-fit items-center text-sm text-muted-foreground transition-colors hover:text-primary"
    >
      <span className="material-symbols-outlined" style={{ fontSize: 20, width: 24 }}>arrow_back</span>
      Back to Skills
    </Link>
  );
}

export default function SkillDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = decodeURIComponent(String(params?.slug ?? ""));
  const router = useRouter();
  const { canAccess } = useAuth();

  const [skill, setSkill] = useState<Skill | null>(null);
  const [failure, setFailure] = useState<"notfound" | "other" | null>(null);
  const [viewVersion, setViewVersion] = useState<number | null>(null);
  const [versions, setVersions] = useState<SkillVersion[]>([]);
  const [uploading, setUploading] = useState(false);
  const [settingLatest, setSettingLatest] = useState(false);
  const [editorId, setEditorId] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<PendingContribution | null>(null);
  const zipInput = useRef<HTMLInputElement>(null);

  const enc = encodeURIComponent(slug);

  // Skill record for the version on screen. The first answer pins the viewed version to the
  // current one, which triggers one more load with an explicit `version`.
  useEffect(() => {
    if (!slug) return;
    let alive = true;
    const qs = viewVersion != null ? `?version=${viewVersion}` : "";
    api<Skill>(`/api/skills/${enc}${qs}`)
      .then((s) => {
        if (!alive) return;
        setSkill(s);
        setFailure(null);
        if (viewVersion == null) setViewVersion(s.current_version);
      })
      .catch((err) => {
        if (!alive) return;
        setFailure(err instanceof ApiError && err.status === 404 ? "notfound" : "other");
      });
    return () => {
      alive = false;
    };
  }, [slug, enc, viewVersion]);

  useEffect(() => {
    if (!slug) return;
    let alive = true;
    api<SkillVersion[]>(`/api/skills/${enc}/versions`)
      .then((v) => alive && setVersions(Array.isArray(v) ? v : []))
      .catch(() => alive && setVersions([]));
    return () => {
      alive = false;
    };
  }, [slug, enc]);

  if (failure === "notfound") {
    return (
      <div className="flex flex-col gap-6">
        <BackLink />
        <EmptyState
          icon="search_off"
          title="Skill Not Found"
          description={`We couldn't find a skill with the identifier "${slug}". It might have been deleted or moved.`}
          action={
            <Button variant="outline" className="h-11 tracking-wider uppercase" onClick={() => router.push("/skills")}>
              Return to Library
            </Button>
          }
        />
      </div>
    );
  }
  if (failure === "other" && !skill) return null;
  if (!skill) {
    return (
      <div className="flex justify-center py-24">
        <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: 48 }}>
          progress_activity
        </span>
      </div>
    );
  }

  const system = skill.is_system;
  const canCreate = canAccess("skill", "create");
  const canDelete = canAccess("skill", "delete");
  const canEdit = canAccess("skill", "edit");
  const previewingOld = viewVersion != null && viewVersion !== skill.current_version;

  const onZip = async (file: File | undefined) => {
    const reset = () => {
      if (zipInput.current) zipInput.current.value = "";
    };
    if (!file) return;
    if (file.name !== `${skill.name}.zip`) {
      alert(`Filename mismatch! You must upload a file named exactly "${skill.name}.zip".`);
      reset();
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiUpload<{ status?: string; message?: string }>(`/api/skills/${enc}/reupload`, fd);
      if (res?.status === "skipped") alert(res.message ?? "");
      else window.location.reload();
    } catch (err) {
      const detail = errDetail(err);
      alert(detail ? `Error: ${detail}` : "Upload failed");
    } finally {
      setUploading(false);
      reset();
    }
  };

  const removeSkill = async () => {
    if (!confirm(`Are you sure you want to delete ${skill.name}?`)) return;
    try {
      await api(`/api/skills/${enc}`, { method: "DELETE" });
      router.push("/skills");
    } catch {
      alert("Failed to delete skill");
    }
  };

  const setLatest = async () => {
    if (viewVersion == null) return;
    if (!confirm(`Are you sure you want to set Version ${viewVersion} as the official latest version?`)) return;
    setSettingLatest(true);
    try {
      await api(`/api/skills/${enc}/set-latest?version=${viewVersion}`, { method: "POST" });
      alert(`Version ${viewVersion} is now the latest.`);
      window.location.reload();
    } catch {
      alert("Failed to set latest version");
    } finally {
      setSettingLatest(false);
    }
  };

  const onReviewSettled = ({ action, ok }: ReviewOutcome) => {
    setReviewing(null);
    if (!ok) return;
    if (action === "approve") {
      alert("Contribution approved and merged successfully!");
      window.location.reload();
    } else {
      alert("Contribution rejected.");
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <BackLink />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-4">
        <div className="min-w-0 lg:col-span-3">
          <SkillFileExplorer skillId={skill.id} version={viewVersion} />
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-end gap-2 animate-in fade-in-0 slide-in-from-right-4">
            {!system && canCreate && (
              <>
                <ContributeDialog
                  key={versions.length}
                  skillId={skill.id}
                  skillName={skill.name}
                  versions={versions}
                  onContributionCreated={setEditorId}
                />
                <input
                  ref={zipInput}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => void onZip(e.target.files?.[0])}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9"
                  title="Upload ZIP"
                  disabled={uploading}
                  onClick={() => zipInput.current?.click()}
                >
                  <span className={cn("material-symbols-outlined", uploading && "animate-spin")} style={{ fontSize: 16 }}>
                    {uploading ? "progress_activity" : "publish"}
                  </span>
                  ZIP
                </Button>
              </>
            )}
            {!system && canDelete && (
              <Button
                variant="destructive"
                size="icon"
                className="size-9"
                title="Delete Skill"
                aria-label="Delete Skill"
                onClick={() => void removeSkill()}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>delete</span>
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-8 rounded-xl border bg-card p-8">
            <div className="flex flex-col gap-4">
              <h3 className={sectionTitle}>Status</h3>
              <span
                className={cn(
                  "inline-flex h-5 w-fit items-center gap-1 rounded-full px-3 text-xs font-bold tracking-[0.1em] uppercase",
                  skill.status === "active" ? TONE.green : "bg-yellow-500/10 text-yellow-700 dark:text-yellow-300",
                )}
              >
                {skill.status}
              </span>
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className={sectionTitle}>Version History</h3>
                {previewingOld && (
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider", TONE.amber)}>
                    PREVIEWING OLD
                  </span>
                )}
              </div>
              <Select
                value={viewVersion != null ? String(viewVersion) : null}
                onValueChange={(v) => v != null && setViewVersion(Number(v))}
              >
                <SelectTrigger className="h-8! w-full">
                  <SelectValue placeholder="Select version">
                    {(v: string | null) => v ?? "Select version"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {versions.map((v) => (
                    <SelectItem key={v.version_number} value={String(v.version_number)}>
                      {v.version_number}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!system && canEdit && previewingOld && (
                <Button className="h-10 w-full" disabled={settingLatest} onClick={() => void setLatest()}>
                  {settingLatest ? "Setting..." : "Set as Official Latest"}
                </Button>
              )}
            </div>
          </div>

          <PendingReviews skillId={skill.id} onOpen={setReviewing} />
        </div>
      </div>

      <ContributionEditorDialog
        contributionId={editorId}
        labels={EDITOR_LABELS_EN}
        onClose={() => setEditorId(null)}
        onSubmitted={() => {
          alert("Contribution submitted successfully!");
          setEditorId(null);
          window.location.reload();
        }}
        onDeleted={() => window.location.reload()}
      />

      <ContributionReviewDialog
        contribution={reviewing ? { id: reviewing.id, contributorName: reviewing.contributor_name } : null}
        labels={REVIEW_LABELS_EN}
        onClose={() => setReviewing(null)}
        onSettled={onReviewSettled}
      />
    </div>
  );
}
