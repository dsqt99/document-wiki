"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

type WikiImageProps = {
  src?: string;
  alt?: string;
  status: "ok" | "loading" | "denied" | "missing";
};

/** Lightbox width: up to 95% of the viewport, capped at 1400px, on every breakpoint. */
const LIGHTBOX_WIDTH = ["max-w-[min(95vw,1400px)]", "sm:max-w-[min(95vw,1400px)]"].join(" ");

/** Renders an `image://` wiki picture according to its resolution state, with a zoom dialog. */
export function WikiImage({ src, alt, status }: WikiImageProps) {
  const [open, setOpen] = useState(false);
  const caption = alt || "Hình ảnh wiki";

  if (status === "loading") {
    return (
      <span className="my-3 flex h-32 items-center justify-center rounded-lg bg-muted/60 text-xs text-muted-foreground">
        Đang tải hình ảnh…
      </span>
    );
  }

  if (status === "denied") {
    return (
      <span className="my-3 flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
        <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
          lock
        </span>
        <span>Hình ảnh bị giới hạn quyền truy cập</span>
        {alt && <em className="text-[11px]">{alt}</em>}
      </span>
    );
  }

  if (status === "missing" || !src) {
    return (
      <span className="my-3 flex flex-col items-center justify-center gap-1 rounded-lg bg-muted/50 p-6 text-center text-xs text-muted-foreground">
        <span className="material-symbols-outlined" style={{ fontSize: 24 }}>
          broken_image
        </span>
        <span>Không tìm thấy hình ảnh</span>
        {alt && <em className="text-[11px]">{alt}</em>}
      </span>
    );
  }

  return (
    <>
      <button
        type="button"
        aria-label={caption}
        onClick={() => setOpen(true)}
        className="my-3 flex cursor-zoom-in flex-col items-center gap-1"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt ?? ""} className="max-h-[480px] max-w-full rounded-lg object-contain" />
        {alt && <span className="text-xs text-muted-foreground">{alt}</span>}
      </button>
      <Dialog onOpenChange={setOpen} open={open}>
        <DialogContent className={LIGHTBOX_WIDTH}>
          <DialogTitle className="sr-only">{caption}</DialogTitle>
          <div className="flex flex-col items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="max-h-[80vh] max-w-full object-contain" alt={alt ?? ""} src={src} />
            <div className="flex w-full items-center justify-between gap-3 text-xs text-muted-foreground">
              <span className="min-w-0 truncate">{alt}</span>
              <a
                href={src}
                download
                className="inline-flex shrink-0 items-center gap-1 font-medium text-primary hover:underline"
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  download
                </span>
                Tải xuống
              </a>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
