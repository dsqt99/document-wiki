"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { LegalDocDetail } from "@/types/legal-doc";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { fileKindOf, splitLegalTitle } from "./law-utils";

type SourceInfo = {
  file_name?: string | null;
  title?: string | null;
  file_size?: number | null;
  contributed_by_name?: string | null;
  preview_url?: string | null;
  file_url?: string | null;
  download_url?: string | null;
  source_type?: string | null;
  url?: string | null;
  preserve_verbatim?: boolean | null;
};

const hoverPop = "transition-transform hover:scale-[1.03] active:scale-[0.97]";

function openInNewTab(url: string) {
  window.open(url, "_blank", "noopener,noreferrer");
}

function Placeholder({
  icon,
  iconClass,
  title,
  description,
  action,
}: {
  icon: string;
  iconClass?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center gap-3 p-8 text-center">
      <span className={iconClass ?? "material-symbols-outlined text-muted-foreground/50"} style={{ fontSize: 56 }}>
        {icon}
      </span>
      <p className="font-semibold">{title}</p>
      <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      {action}
    </div>
  );
}

/** "Tài liệu gốc": file info bar plus an inline viewer for the original file. */
export function LawSourceTab({ doc }: { doc: LegalDocDetail }) {
  const [res, setRes] = useState<{ id: string; info: SourceInfo | null } | null>(null);

  useEffect(() => {
    let stale = false;
    api<SourceInfo>(`/api/sources/${encodeURIComponent(doc.id)}`)
      .then((info) => info)
      .catch(() => null)
      .then((info) => {
        if (!stale) setRes({ id: doc.id, info });
      });
    return () => {
      stale = true;
    };
  }, [doc.id]);

  const src: SourceInfo = res?.id === doc.id && res.info ? res.info : {};

  const fileName = src.file_name || doc.file_name || null;
  const rawTitle = src.title || doc.title || fileName || "Tài liệu";
  const title = splitLegalTitle(rawTitle).main || rawTitle;
  const url = src.url || doc.url || null;
  const sourceType = src.source_type || doc.source_type || null;
  const isWeb = sourceType === "url" || (!fileName && !!url);
  const previewUrl = src.preview_url || doc.preview_url || src.file_url || doc.file_url || src.download_url || doc.download_url || null;
  const downloadUrl = src.download_url || doc.download_url || null;
  const fileSize = src.file_size ?? doc.file_size ?? null;
  const contributor = src.contributed_by_name || doc.contributed_by_name || null;
  const verbatim = !!src.preserve_verbatim;
  const hasFile = doc.has_file || !!previewUrl;
  const kind = fileKindOf(fileName);

  let subline: ReactNode;
  if (isWeb && url) {
    subline = (
      <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 break-all hover:text-primary">
        {url}
        <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
          open_in_new
        </span>
      </a>
    );
  } else if (fileSize) {
    subline = `Dung lượng: ${(fileSize / (1024 * 1024)).toFixed(2)} MB`;
  } else {
    subline = fileName || "Tài liệu số hóa";
  }

  const downloadButton = (variant: "default" | "outline") =>
    downloadUrl ? (
      <Button variant={variant} className={cn(hoverPop, "gap-2 text-xs")} onClick={() => openInNewTab(downloadUrl)}>
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          cloud_download
        </span>
        Tải tài liệu gốc
      </Button>
    ) : null;

  let viewer: ReactNode;
  if (hasFile && previewUrl && kind === "pdf") {
    viewer = <iframe src={`${previewUrl}#toolbar=1`} title={title} className="block h-[800px] w-full border-0" />;
  } else if (hasFile && kind === "image" && previewUrl) {
    viewer = (
      <div className="flex min-h-[400px] items-center justify-center p-4">
        {/* eslint-disable-next-line @next/next/no-img-element -- arbitrary backend URL */}
        <img src={previewUrl} alt={title} className="max-h-[700px] max-w-full rounded-lg border object-contain shadow-sm" />
      </div>
    );
  } else if (hasFile && kind === "office" && (src.preview_url || doc.preview_url || downloadUrl)) {
    viewer = (
      <iframe
        src={(src.preview_url || doc.preview_url || downloadUrl)!}
        title={title}
        className="block h-[800px] w-full border-0"
      />
    );
  } else if (hasFile) {
    viewer = (
      <Placeholder
        icon="draft"
        title="Không thể xem trước định dạng này trực tiếp"
        description={`Tài liệu "${fileName ?? title}" không hỗ trợ nhúng trực tiếp. Vui lòng bấm Tải tài liệu gốc để đọc.`}
        action={downloadButton("outline")}
      />
    );
  } else if (isWeb && url) {
    viewer = (
      <Placeholder
        icon="language"
        iconClass="material-symbols-outlined text-primary/50"
        title="Liên kết tài liệu gốc (Website Source)"
        description="Đây là một liên kết ngoài. Bạn có thể mở trực tiếp trang web để đọc toàn văn tài liệu."
        action={
          <Button variant="outline" className={hoverPop} onClick={() => openInNewTab(url)}>
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
              open_in_new
            </span>
            Mở trang Web gốc
          </Button>
        }
      />
    );
  } else {
    viewer = (
      <Placeholder
        icon="description"
        title="Văn bản không có tệp đính kèm gốc"
        description={'Văn bản này chỉ có nội dung đã số hóa. Bạn có thể chuyển sang tab "Toàn văn" để xem chi tiết các điều khoản.'}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-4 shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <span className="material-symbols-outlined shrink-0 text-primary" style={{ fontSize: 36 }}>
            {isWeb ? "language" : kind === "pdf" ? "picture_as_pdf" : "description"}
          </span>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className="max-w-[500px] truncate font-semibold" title={rawTitle}>
                {title}
              </span>
              {verbatim && (
                <span className="shrink-0 rounded bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-secondary-foreground">
                  Verbatim
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {subline}
              {contributor && ` • Đăng bởi: ${contributor}`}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {previewUrl && (
            <Button variant="outline" className={cn(hoverPop, "gap-2 text-xs")} onClick={() => openInNewTab(previewUrl)}>
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                open_in_new
              </span>
              Mở tab mới
            </Button>
          )}
          {downloadButton("default")}
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border bg-card/50">{viewer}</div>
    </div>
  );
}
