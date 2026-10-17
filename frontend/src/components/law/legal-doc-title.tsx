"use client";

import { useState } from "react";
import { FormattedInlineText } from "@/components/wiki/formatted-inline-text";
import { splitLegalTitle } from "./law-utils";

/** Document heading; the amendment trailer of consolidated titles is collapsible. */
export function LegalDocTitle({ title }: { title: string }) {
  const [open, setOpen] = useState(false);
  const { main, tail } = splitLegalTitle(title);

  return (
    <div className="flex flex-col gap-1.5">
      <h1 className="text-xl leading-[1.375] font-bold tracking-[-0.025em] break-words" title={title}>
        <FormattedInlineText text={main} />
      </h1>
      {tail && (
        <>
          {open && (
            <p className="text-sm text-muted-foreground">
              <FormattedInlineText text={tail} />
            </p>
          )}
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="self-start text-xs font-medium text-primary hover:underline"
          >
            {open ? "Thu gọn" : "Xem thông tin sửa đổi, bổ sung"}
          </button>
        </>
      )}
    </div>
  );
}
