"use client";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { displaySourceTitle } from "@/lib/wiki-store";

/** Fields of `GET /api/sources/{id}` that the wiki screens read. */
export type SourceDetail = {
  id: string;
  title?: string | null;
  file_name?: string | null;
  source_type?: string | null;
  url?: string | null;
  file_size?: number | null;
  preserve_verbatim?: boolean;
  contributed_by_name?: string | null;
  download_url?: string | null;
  preview_url?: string | null;
  file_url?: string | null;
  updated_at?: string;
  created_at?: string;
};

const IMAGE_EXT = new Set(["jpg", "jpeg", "png", "gif", "webp", "svg"]);
const OFFICE_EXT = new Set(["docx", "doc", "xlsx", "xls", "pptx", "ppt", "txt", "md", "csv", "json"]);

export const formatMb = (bytes: number | null | undefined) => `${((bytes ?? 0) / (1024 * 1024)).toFixed(2)} MB`;

export function sourceTitle(s: SourceDetail): string {
  return displaySourceTitle({ title: s.title ?? undefined, file_name: s.file_name ?? undefined });
}

function extensionOf(s: SourceDetail): string {
  const name = s.file_name || s.title || "";
  const m = /\.([a-z0-9]+)$/i.exec(name.trim());
  return m ? m[1].toLowerCase() : "";
}

export function SourceView({ source }: { source: SourceDetail }) {
  const isUrl = source.source_type === "url";
  const title = sourceTitle(source);
  const openUrl = source.preview_url || source.file_url || source.download_url || null;
  const ext = extensionOf(source);
  const hasFile = !!(source.preview_url || source.file_url || source.download_url);

  let viewer: React.ReactNode;
  if (isUrl) {
    viewer = (
      <CenterBlock
        icon="language"
        title="Liên kết tài liệu gốc (Website Source)"
        description="Đây là một liên kết ngoài. Bạn có thể mở trực tiếp trang web để đọc toàn văn tài liệu."
        action={
          source.url ? (
            <Button nativeButton={false} render={<a href={source.url} target="_blank" rel="noopener noreferrer" />}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                open_in_new
              </span>
              Mở trang Web gốc
            </Button>
          ) : null
        }
      />
    );
  } else if (ext === "pdf" && openUrl) {
    viewer = (
      <iframe
        title={title}
        src={`${source.preview_url || openUrl}#toolbar=1`}
        className="h-[780px] w-full rounded-lg border bg-background"
      />
    );
  } else if (IMAGE_EXT.has(ext) && openUrl) {
    viewer = (
      <div className="flex justify-center rounded-lg border bg-muted/30 p-4">
        {/* eslint-disable-next-line @next/next/no-img-element -- signed URL from the API */}
        <img src={openUrl} alt={title} className="max-h-[700px] max-w-full object-contain" />
      </div>
    );
  } else if (OFFICE_EXT.has(ext) && (source.preview_url || source.download_url)) {
    viewer = (
      <iframe
        title={title}
        src={source.preview_url || source.download_url || undefined}
        className="h-[780px] w-full rounded-lg border bg-background"
      />
    );
  } else if (hasFile) {
    viewer = (
      <CenterBlock
        icon="draft"
        title="Không thể xem trước định dạng này trực tiếp"
        description={`Tài liệu "${title}" không hỗ trợ nhúng trực tiếp. Vui lòng bấm Tải tài liệu gốc để đọc.`}
        action={
          source.download_url ? (
            <Button nativeButton={false} render={<a href={source.download_url} target="_blank" rel="noopener noreferrer" />}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                cloud_download
              </span>
              Tải tài liệu gốc
            </Button>
          ) : null
        }
      />
    );
  } else {
    viewer = <CenterBlock icon="hourglass_empty" title="Tài liệu không có tệp đính kèm hoặc đang xử lý." />;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border p-4">
        <span
          className="material-symbols-outlined flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
          style={{ fontSize: 22 }}
        >
          {isUrl ? "language" : "description"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-semibold" title={title}>
              {title}
            </span>
            {source.preserve_verbatim && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <span className="cursor-default rounded-full bg-secondary px-2 py-0.5 text-[11px] font-medium text-secondary-foreground" />
                  }
                >
                  Verbatim
                </TooltipTrigger>
                <TooltipContent>
                  This document is kept word-for-word (not rewritten into wiki pages) so searches can match its exact text.
                </TooltipContent>
              </Tooltip>
            )}
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {isUrl && source.url ? (
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 break-all hover:text-primary hover:underline"
              >
                {source.url}
                <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
                  open_in_new
                </span>
              </a>
            ) : (
              <span>
                Dung lượng: {formatMb(source.file_size)}
                {source.contributed_by_name ? ` • Đăng bởi: ${source.contributed_by_name}` : ""}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {openUrl && (
            <Button variant="outline" size="sm" onClick={() => window.open(openUrl, "_blank", "noopener,noreferrer")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                open_in_new
              </span>
              Mở tab mới
            </Button>
          )}
          {source.download_url && (
            <Button size="sm" nativeButton={false} render={<a href={source.download_url} target="_blank" rel="noopener noreferrer" />}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                cloud_download
              </span>
              Tải tài liệu gốc
            </Button>
          )}
        </div>
      </div>
      {viewer}
    </div>
  );
}

function CenterBlock({
  icon,
  title,
  description,
  action,
}: {
  icon: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-16 text-center">
      <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 44 }}>
        {icon}
      </span>
      <p className="font-medium">{title}</p>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}
