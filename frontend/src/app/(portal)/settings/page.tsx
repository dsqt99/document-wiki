"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/shared/page-header";
import { DocumentProcessingSettingsCard } from "@/components/settings/document-processing-settings-card";
import { EmbeddingSettingsCard } from "@/components/settings/embedding-settings-card";
import { ModelCatalogCard, type ModelSpec } from "@/components/settings/model-catalog-card";
import { OcrSettingsCard } from "@/components/settings/ocr-settings-card";
import { RerankSettingsCard } from "@/components/settings/rerank-settings-card";
import { RolesPermissionsCard } from "@/components/settings/roles-permissions-card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/lib/auth";
import { useIsEmbedded } from "@/lib/embed";
import { cn } from "@/lib/utils";

const TABS = ["config", "permissions"] as const;
type SettingsTab = (typeof TABS)[number];

type ConfigCategory = "all" | "models" | "documents" | "retrieval";

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
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="inline-flex items-center gap-1">
        <span className="text-muted-foreground">Ngữ cảnh:</span>
        <strong className="font-mono text-foreground">{formatTokens(spec.context_window_tokens)}</strong> tokens
      </span>
      <span className="inline-flex items-center gap-1">
        <span className="text-muted-foreground">Đầu ra tối đa:</span>
        <strong className="font-mono text-foreground">{formatTokens(spec.max_output_tokens)}</strong>
      </span>
      {spec.supports_tools && (
        <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 font-medium text-emerald-600 dark:text-emerald-400">
          <span className="material-symbols-outlined text-[13px]">handyman</span>
          Hỗ trợ công cụ
        </span>
      )}
      {spec.supports_vision && (
        <span className="inline-flex items-center gap-1 rounded bg-blue-500/10 px-1.5 py-0.5 font-medium text-blue-600 dark:text-blue-400">
          <span className="material-symbols-outlined text-[13px]">visibility</span>
          Hỗ trợ thị giác
        </span>
      )}
      {spec.cost_per_1m_input_tokens != null && spec.cost_per_1m_input_tokens > 0 ? (
        <span className="text-muted-foreground">
          {formatMoney(spec.cost_per_1m_input_tokens)} vào / {formatMoney(spec.cost_per_1m_output_tokens)} ra mỗi 1M token
        </span>
      ) : (
        <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          {spec.custom ? "vLLM Cục bộ / Intranet" : "Không tính phí token"}
        </span>
      )}
    </span>
  );
}

function visionMeta(spec: ModelSpec) {
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className="inline-flex items-center gap-1">
        <span className="text-muted-foreground">Ảnh tối đa:</span>
        <strong className="font-mono text-foreground">{spec.max_image_size_mb ?? "—"} MB</strong>
      </span>
      {spec.cost_per_1m_input_tokens != null && spec.cost_per_1m_input_tokens > 0 ? (
        <span className="text-muted-foreground">{formatMoney(spec.cost_per_1m_input_tokens)} / 1M token vào</span>
      ) : (
        <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          {spec.custom ? "vLLM Cục bộ / Intranet" : "Không tính phí"}
        </span>
      )}
      {spec.cost_per_image != null && spec.cost_per_image > 0 && (
        <span>{formatMoney(spec.cost_per_image)} / ảnh</span>
      )}
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

function scrollToSection(id: string) {
  const el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("ring-2", "ring-primary/40");
    setTimeout(() => {
      el.classList.remove("ring-2", "ring-primary/40");
    }, 2000);
  }
}

function SettingsContent() {
  const { user, hasPermission, logout } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const embedded = useIsEmbedded();
  const initialTab = parseTab(searchParams.get("tab"));
  const [activeCategory, setActiveCategory] = useState<ConfigCategory>("all");

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
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Cấu hình hệ thống"
        description="Quản trị cụm mô hình AI suy luận, bộ máy OCR, bóc tách văn bản, vector embedding và phân quyền cán bộ."
      />

      {/* Keyed on the query value so a changed ?tab= re-initialises the tab state. */}
      <Tabs key={initialTab} defaultValue={initialTab} className="flex flex-col gap-6">
        {!embedded && (
          <TabsList variant="line" className="h-9">
            <TabsTrigger value="config" className="gap-2">
              <span className="material-symbols-outlined text-[18px]">tune</span>
              Cấu hình AI &amp; Xử lý
            </TabsTrigger>
            <TabsTrigger value="permissions" className="gap-2">
              <span className="material-symbols-outlined text-[18px]">admin_panel_settings</span>
              Ma trận phân quyền cán bộ
            </TabsTrigger>
          </TabsList>
        )}

        <TabsContent value="config" className="flex flex-col gap-8">
          {/* Executive Telemetry & Quick Navigation Ribbon */}
          <div className="flex flex-col gap-3 rounded-2xl border border-border/80 bg-gradient-to-br from-card to-muted/30 p-5 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-3">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-[20px]">hub</span>
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Điều hướng nhanh các phân hệ AI &amp; Xử lý
                </span>
              </div>
              <span className="text-[11px] text-muted-foreground">
                Nhấp thẻ để cuộn nhanh đến phân hệ tương ứng
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {/* Telemetry 1: LLM */}
              <button
                type="button"
                onClick={() => {
                  setActiveCategory("all");
                  setTimeout(() => scrollToSection("llm-model-card"), 50);
                }}
                className="group flex flex-col justify-between rounded-xl border border-border/70 bg-card p-3.5 text-left transition-all hover:border-primary/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <span className="material-symbols-outlined text-[18px]">psychology</span>
                  </div>
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                    Cốt lõi
                  </span>
                </div>
                <div className="mt-2.5">
                  <span className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">
                    Mô hình LLM
                  </span>
                  <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-1">
                    Suy luận &amp; biên soạn wiki
                  </p>
                </div>
              </button>

              {/* Telemetry 2: Vision */}
              <button
                type="button"
                onClick={() => {
                  setActiveCategory("all");
                  setTimeout(() => scrollToSection("vision-model-card"), 50);
                }}
                className="group flex flex-col justify-between rounded-xl border border-border/70 bg-card p-3.5 text-left transition-all hover:border-blue-500/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400">
                    <span className="material-symbols-outlined text-[18px]">visibility</span>
                  </div>
                  <span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-blue-600 dark:text-blue-400">
                    Thị giác
                  </span>
                </div>
                <div className="mt-2.5">
                  <span className="text-xs font-semibold text-foreground group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                    Vision LLM
                  </span>
                  <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-1">
                    Đọc ảnh, bảng &amp; sơ đồ
                  </p>
                </div>
              </button>

              {/* Telemetry 3: OCR */}
              <button
                type="button"
                onClick={() => {
                  setActiveCategory("all");
                  setTimeout(() => scrollToSection("ocr-settings-card"), 50);
                }}
                className="group flex flex-col justify-between rounded-xl border border-border/70 bg-card p-3.5 text-left transition-all hover:border-emerald-500/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <span className="material-symbols-outlined text-[18px]">photo_camera</span>
                  </div>
                  <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                    Nhận dạng
                  </span>
                </div>
                <div className="mt-2.5">
                  <span className="text-xs font-semibold text-foreground group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                    Dịch vụ OCR
                  </span>
                  <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-1">
                    SenOCR-Vi &amp; hiệu đính
                  </p>
                </div>
              </button>

              {/* Telemetry 4: Documents */}
              <button
                type="button"
                onClick={() => {
                  setActiveCategory("all");
                  setTimeout(() => scrollToSection("doc-processing-settings-card"), 50);
                }}
                className="group flex flex-col justify-between rounded-xl border border-border/70 bg-card p-3.5 text-left transition-all hover:border-amber-500/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    <span className="material-symbols-outlined text-[18px]">document_scanner</span>
                  </div>
                  <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
                    Văn bản
                  </span>
                </div>
                <div className="mt-2.5">
                  <span className="text-xs font-semibold text-foreground group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                    Bóc tách tài liệu
                  </span>
                  <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-1">
                    PDF / Excel sang Markdown
                  </p>
                </div>
              </button>

              {/* Telemetry 5: Vector / Rerank */}
              <button
                type="button"
                onClick={() => {
                  setActiveCategory("all");
                  setTimeout(() => scrollToSection("embedding-settings-card"), 50);
                }}
                className="group flex flex-col justify-between rounded-xl border border-border/70 bg-card p-3.5 text-left transition-all hover:border-violet-500/50 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/40"
              >
                <div className="flex items-center justify-between">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400">
                    <span className="material-symbols-outlined text-[18px]">data_array</span>
                  </div>
                  <span className="rounded bg-violet-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600 dark:text-violet-400">
                    Truy xuất
                  </span>
                </div>
                <div className="mt-2.5">
                  <span className="text-xs font-semibold text-foreground group-hover:text-violet-600 dark:group-hover:text-violet-400 transition-colors">
                    Vector &amp; Rerank
                  </span>
                  <p className="mt-0.5 text-[11px] text-muted-foreground line-clamp-1">
                    Embedding &amp; lọc liên quan
                  </p>
                </div>
              </button>
            </div>
          </div>

          {/* Category Filter Pills */}
          <div className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-3">
            <span className="text-xs font-medium text-muted-foreground mr-1">Bộ lọc:</span>
            <Button
              type="button"
              variant={activeCategory === "all" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs gap-1.5 rounded-full px-3.5"
              onClick={() => setActiveCategory("all")}
            >
              <span className="material-symbols-outlined text-[16px]">apps</span>
              Tất cả cấu hình
            </Button>
            <Button
              type="button"
              variant={activeCategory === "models" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs gap-1.5 rounded-full px-3.5"
              onClick={() => setActiveCategory("models")}
            >
              <span className="material-symbols-outlined text-[16px]">psychology</span>
              Mô hình suy luận (LLM &amp; Vision)
            </Button>
            <Button
              type="button"
              variant={activeCategory === "documents" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs gap-1.5 rounded-full px-3.5"
              onClick={() => setActiveCategory("documents")}
            >
              <span className="material-symbols-outlined text-[16px]">photo_camera</span>
              Nhận dạng &amp; Xử lý tài liệu (OCR)
            </Button>
            <Button
              type="button"
              variant={activeCategory === "retrieval" ? "default" : "outline"}
              size="sm"
              className="h-8 text-xs gap-1.5 rounded-full px-3.5"
              onClick={() => setActiveCategory("retrieval")}
            >
              <span className="material-symbols-outlined text-[16px]">sort</span>
              Tìm kiếm ngữ nghĩa (Vector &amp; Rerank)
            </Button>
          </div>

          {/* Section 1: Core AI Inference Models */}
          {(activeCategory === "all" || activeCategory === "models") && (
            <div className="flex flex-col gap-5">
              <div className="flex items-center justify-between border-b border-border/50 pb-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <span className="material-symbols-outlined text-[18px]">smart_toy</span>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold tracking-tight text-foreground">
                      1. Cụm mô hình suy luận cốt lõi (Foundation AI Models)
                    </h3>
                    <p className="text-[11px] text-muted-foreground">
                      Mô hình ngôn ngữ lớn (LLM) và mô hình thị giác (Vision) phục vụ tổng hợp kho tri thức nghiệp vụ.
                    </p>
                  </div>
                </div>
                <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-mono text-muted-foreground">
                  2 mô hình
                </span>
              </div>

              <div className="flex flex-col gap-6">
                <ModelCatalogCard
                  id="llm-model-card"
                  title="Mô hình ngôn ngữ lớn (LLM Model)"
                  description="Mô hình chính phục vụ trích xuất thực thể, suy luận lập kế hoạch và tổng hợp trang tri thức nghiệp vụ."
                  icon="psychology"
                  catalogUrl="/api/settings/llm/catalog"
                  switchUrl="/api/settings/llm/switch"
                  kind="llm"
                  renderMeta={llmMeta}
                />
                <ModelCatalogCard
                  id="vision-model-card"
                  title="Mô hình thị giác (Vision LLM)"
                  description="Phân tích trang tài liệu hình ảnh, đọc cấu trúc bảng biểu, sơ đồ, con dấu và phối hợp hiệu đính OCR."
                  icon="visibility"
                  catalogUrl="/api/settings/vision/catalog"
                  switchUrl="/api/settings/vision/switch"
                  kind="vision"
                  renderMeta={visionMeta}
                />
              </div>
            </div>
          )}

          {/* Section 2: OCR & Document Ingestion */}
          {(activeCategory === "all" || activeCategory === "documents") && (
            <div className="flex flex-col gap-5">
              <div className="flex items-center justify-between border-b border-border/50 pb-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <span className="material-symbols-outlined text-[18px]">document_scanner</span>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold tracking-tight text-foreground">
                      2. Nhận dạng ký tự &amp; Tiếp nhận tài liệu (Ingestion &amp; OCR)
                    </h3>
                    <p className="text-[11px] text-muted-foreground">
                      Cấu hình bộ máy OCR chuyên dụng cho trang scan và engine bóc tách file PDF, bảng tính sang định dạng Markdown chuẩn.
                    </p>
                  </div>
                </div>
                <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-mono text-muted-foreground">
                  2 phân hệ
                </span>
              </div>

              <div className="flex flex-col gap-6">
                <OcrSettingsCard id="ocr-settings-card" />
                <DocumentProcessingSettingsCard id="doc-processing-settings-card" />
              </div>
            </div>
          )}

          {/* Section 3: Vector Search & Retrieval */}
          {(activeCategory === "all" || activeCategory === "retrieval") && (
            <div className="flex flex-col gap-5">
              <div className="flex items-center justify-between border-b border-border/50 pb-2">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:text-violet-400">
                    <span className="material-symbols-outlined text-[18px]">travel_explore</span>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold tracking-tight text-foreground">
                      3. Tìm kiếm ngữ nghĩa &amp; Xếp hạng (Vector Search &amp; Rerank)
                    </h3>
                    <p className="text-[11px] text-muted-foreground">
                      Mô hình vector hóa toàn bộ dữ liệu tri thức và cơ chế chấm điểm lại (Reranking) tăng cường độ chính xác tìm kiếm.
                    </p>
                  </div>
                </div>
                <span className="rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-mono text-muted-foreground">
                  2 phân hệ
                </span>
              </div>

              <div className="flex flex-col gap-6">
                <EmbeddingSettingsCard id="embedding-settings-card" />
                <RerankSettingsCard id="rerank-settings-card" />
              </div>
            </div>
          )}
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
