"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export type WikiStatus = "seed" | "developing" | "mature" | "evergreen";

const STATUS_CONFIGS: Record<
  WikiStatus,
  {
    label: string;
    description: string;
    classes: string;
  }
> = {
  seed: {
    label: "Seed",
    description: "Tri thức sơ khởi vừa được nạp vào hệ thống.",
    classes: "border-[#a8977e]/40 text-[#8a7a62] bg-[#a8977e]/8 hover:bg-[#a8977e]/15",
  },
  developing: {
    label: "Developing",
    description: "Đang phát triển và bổ sung thêm tài liệu.",
    classes: "border-[#d4872e]/40 text-[#c07522] bg-[#d4872e]/8 hover:bg-[#d4872e]/15",
  },
  mature: {
    label: "Mature",
    description: "Tri thức đã được củng cố tương đối đầy đủ.",
    classes: "border-[#2e8b8b]/40 text-[#1f7a7a] bg-[#2e8b8b]/8 hover:bg-[#2e8b8b]/15",
  },
  evergreen: {
    label: "Evergreen",
    description: "Tri thức cốt lõi, bền vững và tin cậy cao.",
    classes: "border-[#3a8a3f]/40 text-[#2d7a32] bg-[#3a8a3f]/10 hover:bg-[#3a8a3f]/18",
  },
};

export function WikiStatusBadge({
  status,
  className,
}: {
  status: WikiStatus | string;
  className?: string;
}) {
  const { t } = useI18n();
  const normStatus = (status?.toLowerCase() || "seed") as WikiStatus;

  const getDesc = (st: WikiStatus) => {
    switch (st) {
      case "developing":
        return t("wiki.status.developing", "In active development with additional documents.");
      case "mature":
        return t("wiki.status.mature", "Knowledge is well-consolidated and comprehensive.");
      case "evergreen":
        return t("wiki.status.evergreen", "Core, sustainable, and highly reliable knowledge.");
      case "seed":
      default:
        return t("wiki.status.seed", "Initial knowledge just added to the system.");
    }
  };

  const config = STATUS_CONFIGS[normStatus] || STATUS_CONFIGS.seed;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-medium tracking-wide select-none transition-colors cursor-help",
        config.classes,
        className
      )}
      title={getDesc(normStatus)}
    >
      <span className="w-1 h-1 rounded-full bg-current" />
      {config.label}
    </div>
  );
}
