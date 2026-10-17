"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/shared/page-header";
import { DocumentProcessingSettingsCard } from "@/components/settings/document-processing-settings-card";
import { EmbeddingSettingsCard } from "@/components/settings/embedding-settings-card";
import { ModelCatalogCard, type ModelSpec } from "@/components/settings/model-catalog-card";
import { OcrSettingsCard } from "@/components/settings/ocr-settings-card";
import { RolesPermissionsCard } from "@/components/settings/roles-permissions-card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { useIsEmbedded } from "@/lib/embed";

const TABS = ["config", "permissions"] as const;
type SettingsTab = (typeof TABS)[number];

function parseTab(raw: string | null): SettingsTab {
  return (TABS as readonly string[]).includes(raw ?? "") ? (raw as SettingsTab) : "config";
}

/** 0/missing → "—", then M / k suffixes. */
function formatTokens(n?: number | null): string {
  if (!n) return "—";
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return `${Number.isInteger(m) ? m : m.toFixed(1)}M`;
  }
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

function formatMoney(v?: number | null): string {
  return v == null ? "—" : `$${v.toFixed(2)}`;
}

function llmMeta(spec: ModelSpec) {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
      <span>Context: {formatTokens(spec.context_window_tokens)} tokens</span>
      <span>Out: {formatTokens(spec.max_output_tokens)}</span>
      {spec.supports_tools && <span className="text-emerald-600 dark:text-emerald-400">tools</span>}
      {spec.supports_vision && <span className="text-blue-600 dark:text-blue-400">vision</span>}
      <span>
        {formatMoney(spec.cost_per_1m_input_tokens)} in / {formatMoney(spec.cost_per_1m_output_tokens)} out per 1M
      </span>
    </span>
  );
}

function visionMeta(spec: ModelSpec) {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
      <span>Max image: {spec.max_image_size_mb ?? "—"} MB</span>
      <span>{formatMoney(spec.cost_per_1m_input_tokens)} per 1M input tokens</span>
      {spec.cost_per_image != null && <span>{formatMoney(spec.cost_per_image)} / image</span>}
    </span>
  );
}

function Spinner() {
  return (
    <div className="flex justify-center py-20">
      <span className="material-symbols-outlined animate-spin text-[30px] text-muted-foreground">progress_activity</span>
    </div>
  );
}

function SettingsContent() {
  const { user, hasPermission, logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const embedded = useIsEmbedded();
  const initialTab = parseTab(searchParams.get("tab"));

  if (!user) return <Spinner />;

  if (!hasPermission("org:settings:manage")) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 py-20 text-center">
        <p className="text-sm font-medium text-foreground">Tài khoản này không có quyền mở cài đặt Kho tri thức</p>
        <p className="text-xs text-muted-foreground">
          Đang đăng nhập Kho tri thức bằng <strong className="text-foreground">{user.email}</strong>. Đăng xuất rồi đăng
          nhập lại bằng tài khoản quản trị (SSO) để tiếp tục.
        </p>
        <Button
          type="button"
          onClick={() => {
            if (!logout()) router.push("/login?logged_out=1");
          }}
        >
          Đăng xuất
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Cài đặt" description="Nhà cung cấp AI cho embedding, LLM, xử lý ảnh và phân quyền theo vai trò." />

      {/* Keyed on the query value so a changed ?tab= re-initialises the tab state. */}
      <Tabs key={initialTab} defaultValue={initialTab} className="flex flex-col gap-6">
        {!embedded && (
          <TabsList variant="line">
            <TabsTrigger value="config">
              <span className="material-symbols-outlined text-[18px]">tune</span>
              Cấu hình
            </TabsTrigger>
            <TabsTrigger value="permissions">
              <span className="material-symbols-outlined text-[18px]">admin_panel_settings</span>
              Ma trận phân quyền
            </TabsTrigger>
          </TabsList>
        )}

        <TabsContent value="config" className="flex flex-col gap-6">
          <DocumentProcessingSettingsCard />
          <OcrSettingsCard />
          <EmbeddingSettingsCard />
          <ModelCatalogCard
            title="LLM Model"
            description="Used for entity extraction, planning, and wiki compilation."
            icon="psychology"
            catalogUrl="/api/settings/llm/catalog"
            switchUrl="/api/settings/llm/switch"
            kind="llm"
            renderMeta={llmMeta}
          />
          <ModelCatalogCard
            title="Vision Model"
            description="Used for image analysis during document ingestion."
            icon="visibility"
            catalogUrl="/api/settings/vision/catalog"
            switchUrl="/api/settings/vision/switch"
            kind="vision"
            renderMeta={visionMeta}
          />
        </TabsContent>

        <TabsContent value="permissions">
          <RolesPermissionsCard />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <SettingsContent />
    </Suspense>
  );
}
