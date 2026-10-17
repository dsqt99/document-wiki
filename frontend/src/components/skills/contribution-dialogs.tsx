"use client";

import { useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { SkillEditor } from "./skill-editor";
import { errMessage } from "./skill-utils";

/** 98vw × 96vh frame shared by the proposal editor and reviewer. */
const frameCls =
  "flex h-[96vh] w-[98vw] max-w-[98vw] flex-col gap-0 overflow-hidden rounded-xl border p-0 shadow-2xl sm:max-w-[min(98vw,1800px)]";

function FrameHeader({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: string;
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex shrink-0 items-center gap-3 border-b bg-primary/5 px-5 py-3">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <span className="material-symbols-outlined" style={{ fontSize: 22 }}>{icon}</span>
      </div>
      <div className="min-w-0 flex-1">
        <DialogTitle className="truncate font-serif text-xl">{title}</DialogTitle>
        <DialogDescription className="text-xs">{subtitle}</DialogDescription>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">{children}</div>
    </div>
  );
}

function HeaderIconBtn({
  icon,
  title,
  onClick,
  danger,
  disabled,
}: {
  icon: string;
  title?: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title ?? icon}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:opacity-50",
        danger ? "hover:text-destructive" : "hover:text-foreground",
      )}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 18 }}>{icon}</span>
    </button>
  );
}

const accentBtn =
  "inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-bold tracking-wider text-primary-foreground uppercase shadow-md transition-colors hover:bg-primary/90 disabled:opacity-50";

export type EditorLabels = {
  title: string;
  subtitle: string;
  submit: string;
  submitConfirm: string;
  submitFail: string;
  deleteTip: string;
  deleteConfirm: string;
  deleteFail: string;
  closeTip: string;
  unknownError: string;
};

export const EDITOR_LABELS_VI: EditorLabels = {
  title: "Chỉnh sửa đề xuất",
  subtitle: "Bản nháp: gửi duyệt khi đã xong",
  submit: "Gửi duyệt",
  submitConfirm: "Gửi đề xuất này để duyệt?",
  submitFail: "Gửi thất bại",
  deleteTip: "Xóa bản nháp",
  deleteConfirm: "Xóa bản nháp này? Không thể hoàn tác.",
  deleteFail: "Xóa thất bại",
  closeTip: "Đóng",
  unknownError: "Lỗi không xác định",
};

export const EDITOR_LABELS_EN: EditorLabels = {
  title: "Editing Contribution",
  subtitle: "Draft Mode",
  submit: "Contribute",
  submitConfirm: "Are you sure you want to submit this contribution for review?",
  submitFail: "Submit failed",
  deleteTip: "Delete Draft",
  deleteConfirm: "Are you sure you want to delete this draft contribution? This action cannot be undone.",
  deleteFail: "Delete failed",
  closeTip: "Close Editor",
  unknownError: "Unknown error",
};

/** Full-screen editor for one of the caller's draft proposals. */
export function ContributionEditorDialog({
  contributionId,
  labels,
  onClose,
  onSubmitted,
  onDeleted,
}: {
  contributionId: string | null;
  labels: EditorLabels;
  onClose: () => void;
  onSubmitted: () => void;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const run = async (kind: "submit" | "delete") => {
    if (!contributionId) return;
    if (!confirm(kind === "submit" ? labels.submitConfirm : labels.deleteConfirm)) return;
    setBusy(true);
    try {
      if (kind === "submit") {
        await api(`/api/skill-contributions/${contributionId}/submit`, { method: "POST" });
        onSubmitted();
      } else {
        await api(`/api/skill-contributions/${contributionId}`, { method: "DELETE" });
        onDeleted();
      }
    } catch (err) {
      const prefix = kind === "submit" ? labels.submitFail : labels.deleteFail;
      alert(`${prefix}: ${errMessage(err, labels.unknownError)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={!!contributionId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent showCloseButton={false} className={frameCls}>
        <FrameHeader icon="edit_note" title={labels.title} subtitle={labels.subtitle}>
          <button type="button" className={accentBtn} disabled={busy} onClick={() => void run("submit")}>
            {labels.submit}
          </button>
          <HeaderIconBtn icon="delete" title={labels.deleteTip} danger disabled={busy} onClick={() => void run("delete")} />
          <HeaderIconBtn icon="close" title={labels.closeTip} onClick={onClose} />
        </FrameHeader>
        <div className="min-h-0 flex-1">
          {contributionId && <SkillEditor key={contributionId} contributionId={contributionId} mode="edit" />}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export type ReviewLabels = {
  title: string;
  submittedBy: string;
  unknownName: string;
  reject: string;
  approve: string;
  rejectConfirm: string;
  approveConfirm: string;
  rejectFail: string;
  approveFail: string;
  /** Omit for an icon-only close button. */
  closeTip?: string;
  unknownError: string;
};

export const REVIEW_LABELS_VI: ReviewLabels = {
  title: "Xem xét đề xuất",
  submittedBy: "Người gửi:",
  unknownName: "—",
  reject: "Từ chối",
  approve: "Duyệt & hợp nhất",
  rejectConfirm: "Từ chối đề xuất này?",
  approveConfirm: "Duyệt và hợp nhất đề xuất này vào thư viện?",
  rejectFail: "Từ chối thất bại",
  approveFail: "Duyệt thất bại",
  closeTip: "Đóng",
  unknownError: "Lỗi không xác định",
};

export const REVIEW_LABELS_EN: ReviewLabels = {
  title: "Review Contribution",
  submittedBy: "Submitted by",
  unknownName: "Unknown",
  reject: "Reject",
  approve: "Approve & Merge",
  rejectConfirm: "Are you sure you want to REJECT this contribution?",
  approveConfirm: "Are you sure you want to APPROVE and MERGE this contribution?",
  rejectFail: "Rejection failed",
  approveFail: "Approval failed",
  closeTip: "Close Reviewer",
  unknownError: "Unknown error",
};

export type ReviewOutcome = { action: "approve" | "reject"; ok: boolean };

/**
 * Full-screen reviewer. It asks for confirmation, calls the API and alerts on failure;
 * `onSettled` then lets each page decide whether to close, reload or toast.
 */
export function ContributionReviewDialog({
  contribution,
  labels,
  onClose,
  onSettled,
}: {
  contribution: { id: string; contributorName?: string | null } | null;
  labels: ReviewLabels;
  onClose: () => void;
  onSettled: (outcome: ReviewOutcome) => void;
}) {
  const [busy, setBusy] = useState(false);

  const run = async (action: "approve" | "reject") => {
    if (!contribution) return;
    if (!confirm(action === "approve" ? labels.approveConfirm : labels.rejectConfirm)) return;
    setBusy(true);
    let ok = true;
    try {
      await api(`/api/skill-contributions/${contribution.id}/${action}`, { method: "POST" });
    } catch (err) {
      ok = false;
      const prefix = action === "approve" ? labels.approveFail : labels.rejectFail;
      alert(`${prefix}: ${errMessage(err, labels.unknownError)}`);
    } finally {
      setBusy(false);
    }
    onSettled({ action, ok });
  };

  return (
    <Dialog open={!!contribution} onOpenChange={(o) => !o && onClose()}>
      <DialogContent showCloseButton={false} className={frameCls}>
        <FrameHeader
          icon="rate_review"
          title={labels.title}
          subtitle={
            <>
              {labels.submittedBy} <strong className="text-foreground">{contribution?.contributorName || labels.unknownName}</strong>
            </>
          }
        >
          <button
            type="button"
            disabled={busy}
            onClick={() => void run("reject")}
            className="inline-flex h-8 items-center gap-1 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
            {labels.reject}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void run("approve")}
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-sm font-bold text-primary-foreground shadow-md transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>check_circle</span>
            {labels.approve}
          </button>
          <span className="mx-1 h-6 w-px bg-border" />
          <HeaderIconBtn icon="close" title={labels.closeTip} onClick={onClose} />
        </FrameHeader>
        <div className="min-h-0 flex-1">
          {contribution && (
            <SkillEditor key={contribution.id} contributionId={contribution.id} mode="review" />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
