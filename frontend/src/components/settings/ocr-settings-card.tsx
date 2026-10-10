"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { ActivateBar, canActivate } from "./model-catalog-card";
import { ActiveModelChip, ProviderModelPicker } from "./provider-model-picker";
import { PreviewStudio, Stat, TestFileDropzone } from "./test-lab";

type OCRResponse = {
  success: boolean;
  text: string;
  model: string;
  latency_ms: number;
  chars_count: number;
  words_count: number;
  page_number?: number;
  total_pages?: number;
  error?: string | null;
  raw_text?: string | null;
  ocr_latency_ms?: number;
  refine_model?: string | null;
  refine_latency_ms?: number;
  refine_error?: string | null;
};

type OcrModel = {
  id: string;
  provider: string;
  group: string;
  label: string;
  base_url: string;
  model_id: string;
  custom: boolean;
  api_key_configured: boolean;
};

type OcrCatalog = { active_spec_id: string | null; specs: OcrModel[] };

type ConnResult = { success: boolean; message: string; latency_ms: number };

const OCR_MODES = [
  {
    refine: false,
    icon: "bolt",
    title: "Chỉ OCR",
    desc: "Nhanh, chi phí thấp. Phù hợp bản scan rõ nét.",
  },
  {
    refine: true,
    icon: "auto_fix_high",
    title: "OCR + LLM hiệu đính",
    desc: "Model Vision đối chiếu ảnh và sửa bản OCR — chính xác nhất, thời gian xử lý ~2×.",
  },
];

export function OcrSettingsCard() {
  const [catalog, setCatalog] = useState<OcrCatalog | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  const [switching, setSwitching] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [testingConn, setTestingConn] = useState(false);
  const [connResult, setConnResult] = useState<(ConnResult & { id: string }) | null>(null);

  // Test lab
  const [testFile, setTestFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [targetPage, setTargetPage] = useState(1);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<OCRResponse | null>(null);
  // null = follow the saved processing mode.
  const [labRefine, setLabRefine] = useState<boolean | null>(null);
  const [resultTab, setResultTab] = useState<"refined" | "raw">("refined");
  const [modeSaving, setModeSaving] = useState(false);
  const [modeError, setModeError] = useState("");

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    try {
      const [s, cat] = await Promise.all([
        api<Record<string, unknown>>("/api/settings"),
        api<OcrCatalog>("/api/settings/ocr/catalog"),
      ]);
      setCatalog(cat);
      setSettings(s);
      setSelectedId((prev) =>
        prev && cat.specs.some((x) => x.id === prev) ? prev : cat.active_spec_id ?? cat.specs[0]?.id ?? null,
      );
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Không thể tải cấu hình OCR");
    }
  }

  // Free the object URL of the previous image thumbnail.
  useEffect(() => {
    return () => {
      if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
    };
  }, [imagePreviewUrl]);

  const selectedModel = catalog?.specs.find((x) => x.id === selectedId) ?? null;
  const activeModel = catalog?.specs.find((x) => x.id === catalog.active_spec_id) ?? null;
  const willSwitch = !!selectedModel && selectedModel.id !== catalog?.active_spec_id;
  const conn = connResult && connResult.id === selectedId ? connResult : null;
  const refineMode = settings.ocr_llm_refine === "true" || settings.ocr_llm_refine === true;
  const runRefine = labRefine ?? refineMode;

  async function saveMode(refine: boolean) {
    if (refine === refineMode) return;
    setModeSaving(true);
    setModeError("");
    try {
      await api("/api/settings", {
        method: "PUT",
        body: { settings: { ocr_llm_refine: refine ? "true" : "false" } },
      });
      setSettings((s) => ({ ...s, ocr_llm_refine: refine ? "true" : "false" }));
    } catch (err) {
      setModeError(err instanceof Error ? err.message : "Không lưu được chế độ OCR");
    } finally {
      setModeSaving(false);
    }
  }

  async function handleActivate() {
    if (!selectedModel) return;
    setSwitching(true);
    setSaved(false);
    setSaveError("");
    try {
      await api("/api/settings/ocr/select", {
        method: "POST",
        body: { model_spec_id: selectedModel.id },
      });
      await refresh();
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Lỗi khi lưu cấu hình OCR");
    } finally {
      setSwitching(false);
    }
  }

  // The OCR service reads the flat ocr_api_key: re-apply the active model so a
  // new key of its provider takes effect.
  async function handleProviderKeySaved(group: string) {
    if (activeModel && !activeModel.custom && activeModel.group === group) {
      await api("/api/settings/ocr/select", {
        method: "POST",
        body: { model_spec_id: activeModel.id },
      });
    }
  }

  async function handleTestConnection() {
    if (!selectedModel) return;
    const id = selectedModel.id;
    setTestingConn(true);
    setConnResult(null);
    try {
      const res = await api<ConnResult>("/api/settings/test-ocr-connection", {
        method: "POST",
        body: { model_spec_id: id },
      });
      setConnResult({ ...res, id });
    } catch (err) {
      setConnResult({
        id,
        success: false,
        message: err instanceof Error ? err.message : "Không thể kết nối endpoint OCR",
        latency_ms: 0,
      });
    } finally {
      setTestingConn(false);
    }
  }

  function handleFile(file: File) {
    setTestFile(file);
    setTestResult(null);
    setTargetPage(1);
    setImagePreviewUrl(file.type.startsWith("image/") ? URL.createObjectURL(file) : null);
  }

  async function handleRunOcr() {
    if (!testFile || !selectedModel) return;
    setTestLoading(true);
    setTestResult(null);

    const formData = new FormData();
    formData.append("file", testFile);
    formData.append("target_page", String(targetPage));
    formData.append("model_spec_id", selectedModel.id);
    formData.append("llm_refine", String(runRefine));
    setResultTab("refined");

    try {
      const res = await api<OCRResponse>("/api/settings/test-ocr", {
        method: "POST",
        body: formData,
        timeoutMs: runRefine ? 360_000 : 180_000,
      });
      setTestResult(res);
      if (res.page_number) setTargetPage(res.page_number);
    } catch (err) {
      setTestResult({
        success: false,
        text: "",
        model: selectedModel.model_id,
        latency_ms: 0,
        chars_count: 0,
        words_count: 0,
        error: err instanceof Error ? err.message : "Thực hiện OCR thất bại",
      });
    } finally {
      setTestLoading(false);
    }
  }

  const isPdf = !!testFile?.name.toLowerCase().endsWith(".pdf");
  const totalPages = testResult?.total_pages ?? null;

  return (
    <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-sahara flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <span className="material-symbols-outlined text-[22px]">photo_camera</span>
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-semibold tracking-tight text-foreground">Dịch vụ OCR</h2>
          <p className="text-xs text-muted-foreground">
            Model đọc trang scan / ảnh chụp văn bản khi bóc tách tài liệu.
          </p>
        </div>
        <ActiveModelChip spec={activeModel} />
      </div>

      {!catalog ? (
        <div className="flex items-center justify-center gap-2.5 py-10 text-muted-foreground">
          {loadError ? (
            <span className="text-xs text-destructive">{loadError}</span>
          ) : (
            <>
              <span className="material-symbols-outlined animate-spin text-xl text-primary">progress_activity</span>
              <span className="text-xs font-medium">Đang tải cấu hình OCR...</span>
            </>
          )}
        </div>
      ) : (
        <>
          <ProviderModelPicker
            kind="ocr"
            specs={catalog.specs}
            activeId={catalog.active_spec_id}
            selectedId={selectedId}
            onSelect={setSelectedId}
            settings={settings}
            onChanged={refresh}
            onProviderKeySaved={handleProviderKeySaved}
            keyFallbackHint="Dùng key Vision cùng nhà cung cấp"
          />

          <ActivateBar
            willSwitch={willSwitch}
            ready={canActivate(selectedModel)}
            busy={switching}
            saved={saved}
            error={saveError}
            label={selectedModel?.label}
            onActivate={handleActivate}
          >
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestConnection}
              disabled={testingConn || !selectedModel}
              className="h-9 gap-1 text-xs"
              title="Gửi 1 request nhỏ tới model đang chọn"
            >
              <span className={`material-symbols-outlined text-sm ${testingConn ? "animate-spin" : ""}`}>
                {testingConn ? "progress_activity" : "network_ping"}
              </span>
              Ping
            </Button>
            {conn && (
              <span
                className={`flex items-center gap-1 text-xs ${
                  conn.success ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                }`}
              >
                <span className="material-symbols-outlined text-sm">{conn.success ? "check_circle" : "error"}</span>
                <span className="max-w-[320px] truncate" title={conn.message}>
                  {conn.message}
                </span>
                {conn.latency_ms > 0 && <span className="font-mono">· {conn.latency_ms} ms</span>}
              </span>
            )}
          </ActivateBar>

          {/* Processing mode */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-foreground">Chế độ xử lý trang scan</span>
            <div role="radiogroup" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {OCR_MODES.map((m) => {
                const on = refineMode === m.refine;
                return (
                  <button
                    key={m.title}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    disabled={modeSaving}
                    onClick={() => void saveMode(m.refine)}
                    className={`flex items-start gap-2.5 rounded-lg border p-3 text-left transition-colors disabled:opacity-60 ${
                      on ? "border-primary bg-primary/5" : "border-border hover:bg-accent/30"
                    }`}
                  >
                    <span className={`material-symbols-outlined text-lg ${on ? "text-primary" : "text-muted-foreground"}`}>
                      {m.icon}
                    </span>
                    <span className="flex flex-col gap-0.5">
                      <span className="text-sm font-medium text-foreground">{m.title}</span>
                      <span className="text-[11px] leading-snug text-muted-foreground">{m.desc}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {refineMode
                ? "Bước hiệu đính dùng model đang chọn ở mục Vision Model."
                : "Áp dụng cho các tài liệu tải lên sau khi lưu."}
              {modeSaving && " Đang lưu…"}
            </p>
            {modeError && <p className="text-xs text-destructive">{modeError}</p>}
          </div>

          {/* Test lab */}
          <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                <span className="material-symbols-outlined text-sm text-primary">science</span>
                Thử OCR
              </span>
              {selectedModel && (
                <span className="truncate text-[11px] text-muted-foreground">
                  Model thử: <span className="font-medium text-foreground">{selectedModel.label}</span>
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="flex flex-col gap-3 lg:col-span-4">
                <TestFileDropzone
                  file={testFile}
                  onFile={handleFile}
                  onClear={() => {
                    setTestFile(null);
                    setImagePreviewUrl(null);
                    setTestResult(null);
                  }}
                  accept="image/png,image/jpeg,image/webp,.pdf"
                  hint="PNG, JPG, WEBP hoặc PDF scan (quét 1 trang)"
                  thumbnailUrl={imagePreviewUrl}
                />

                {isPdf && (
                  <div className="flex items-center justify-between rounded-lg border border-border bg-background p-2 text-xs">
                    <span className="font-medium text-muted-foreground">
                      Trang{totalPages ? ` (/${totalPages})` : ""}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setTargetPage((p) => Math.max(1, p - 1))}
                        className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                        title="Trang trước"
                      >
                        <span className="material-symbols-outlined text-sm">chevron_left</span>
                      </button>
                      <input
                        type="number"
                        min={1}
                        max={totalPages ?? undefined}
                        value={targetPage}
                        onChange={(e) => setTargetPage(Math.max(1, parseInt(e.target.value) || 1))}
                        className="h-7 w-12 rounded border border-border bg-background text-center font-mono text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                      <button
                        type="button"
                        onClick={() => setTargetPage((p) => (totalPages ? Math.min(totalPages, p + 1) : p + 1))}
                        className="flex h-7 w-7 items-center justify-center rounded border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                        title="Trang tiếp"
                      >
                        <span className="material-symbols-outlined text-sm">chevron_right</span>
                      </button>
                    </div>
                  </div>
                )}

                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-background p-2 text-xs">
                  <input type="checkbox" checked={runRefine} onChange={(e) => setLabRefine(e.target.checked)} />
                  <span className="flex-1">Hiệu đính bằng LLM</span>
                  <span className="material-symbols-outlined text-sm text-muted-foreground">auto_fix_high</span>
                </label>

                <Button
                  size="sm"
                  onClick={handleRunOcr}
                  disabled={!testFile || !selectedModel || testLoading}
                  className="h-9 w-full gap-2 text-xs font-medium"
                >
                  <span className={`material-symbols-outlined text-sm ${testLoading ? "animate-spin" : ""}`}>
                    {testLoading ? "progress_activity" : "document_scanner"}
                  </span>
                  {testLoading
                    ? runRefine
                      ? "Đang OCR + hiệu đính..."
                      : "Đang quét OCR..."
                    : runRefine
                      ? "Chạy OCR + LLM"
                      : "Chạy OCR"}
                </Button>
                <p className="text-[11px] text-muted-foreground">
                  Chạy bằng model đang chọn ở trên (không cần bấm &quot;Dùng model này&quot;), với API key đã lưu.
                </p>
              </div>

              <div className="lg:col-span-8">
                <PreviewStudio
                  title="Kết quả OCR"
                  icon="text_fields"
                  loading={testLoading}
                  loadingTitle={runRefine ? "Đang nhận diện và hiệu đính văn bản..." : "Đang nhận diện văn bản..."}
                  content={
                    testResult?.success
                      ? resultTab === "raw" && testResult.raw_text
                        ? testResult.raw_text
                        : testResult.text
                      : null
                  }
                  tabs={
                    testResult?.success && testResult.raw_text
                      ? [
                          { key: "refined", label: "Sau LLM" },
                          { key: "raw", label: "OCR thô" },
                        ]
                      : undefined
                  }
                  activeTab={resultTab}
                  onTab={(k) => setResultTab(k === "raw" ? "raw" : "refined")}
                  error={testResult && !testResult.success ? testResult.error || "OCR thất bại" : null}
                  successLabel={testResult?.success ? "Thành công" : null}
                  telemetry={
                    testResult?.success ? (
                      <>
                        <Stat icon="timer">
                          {(testResult.latency_ms / 1000).toFixed(2)}s
                          {!!testResult.refine_latency_ms &&
                            ` (OCR ${((testResult.ocr_latency_ms ?? 0) / 1000).toFixed(1)}s + LLM ${(
                              testResult.refine_latency_ms / 1000
                            ).toFixed(1)}s)`}
                        </Stat>
                        {testResult.refine_error && (
                          <span className="text-amber-600 dark:text-amber-400">{testResult.refine_error}</span>
                        )}
                        <Stat icon="format_quote">
                          {testResult.words_count.toLocaleString()} từ · {testResult.chars_count.toLocaleString()} ký tự
                        </Stat>
                        {testResult.total_pages && testResult.total_pages > 1 && (
                          <Stat icon="layers">
                            Trang {testResult.page_number}/{testResult.total_pages}
                          </Stat>
                        )}
                        <span className="ml-auto rounded border border-border/60 bg-background px-2 text-[10px] font-semibold text-foreground">
                          {testResult.model}
                          {testResult.raw_text && testResult.refine_model && ` + ${testResult.refine_model}`}
                        </span>
                      </>
                    ) : null
                  }
                  downloadName={`ocr_${testFile?.name || "result"}.md`}
                  emptyTitle="Chưa có kết quả OCR"
                  emptyHint="Chọn ảnh hoặc PDF bên trái rồi bấm “Chạy OCR”."
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
