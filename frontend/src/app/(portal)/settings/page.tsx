"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "@/components/shared/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmbeddingSettingsCard } from "@/components/settings/embedding-settings-card";
import { DocumentProcessingSettingsCard } from "@/components/settings/document-processing-settings-card";
import { OcrSettingsCard } from "@/components/settings/ocr-settings-card";
import { RolesPermissionsCard } from "@/components/settings/roles-permissions-card";
import {
  ModelCatalogCard,
  type ModelSpec,
} from "@/components/settings/model-catalog-card";

function fmtTokens(n: number | undefined): string {
  if (!n) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

function fmtUSD(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toFixed(n < 1 ? 2 : 2)}`;
}

function llmMeta(s: ModelSpec) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
      <span>Context: {fmtTokens(s.context_window_tokens)} tokens</span>
      <span>Out: {fmtTokens(s.max_output_tokens)}</span>
      {s.supports_tools && <span className="text-green-600 dark:text-green-400">tools</span>}
      {s.supports_vision && <span className="text-blue-600 dark:text-blue-400">vision</span>}
      <span>
        {fmtUSD(s.cost_per_1m_input_tokens)} in / {fmtUSD(s.cost_per_1m_output_tokens)} out per 1M
      </span>
    </div>
  );
}

function visionMeta(s: ModelSpec) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5">
      <span>Max image: {s.max_image_size_mb} MB</span>
      <span>{fmtUSD(s.cost_per_1m_input_tokens)} per 1M input tokens</span>
      {s.cost_per_image != null && <span>{fmtUSD(s.cost_per_image)} / image</span>}
    </div>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, router]);

  if (!user || user.role !== "admin") {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Settings"
        description="Configure AI providers for embedding, LLM, and vision processing."
      />

      <Tabs defaultValue="config" className="gap-6">
        <TabsList variant="line">
          <TabsTrigger value="config">
            <span className="material-symbols-outlined text-base">tune</span>
            Cấu hình
          </TabsTrigger>
          <TabsTrigger value="permissions">
            <span className="material-symbols-outlined text-base">admin_panel_settings</span>
            Ma trận phân quyền
          </TabsTrigger>
        </TabsList>

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
    </>
  );
}
