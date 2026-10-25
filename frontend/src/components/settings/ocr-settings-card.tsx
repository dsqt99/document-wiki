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
    desc: "Nhanh, chi phí thấp, giữ nguyên văn bản gốc. Tối ưu cho SenOCR-Vi.",
    badge: "Khuyên dùng cho SenOCR-Vi",
  },
  {
    refine: true,
    icon: "auto_fix_high",
    title: "OCR + LLM hiệu đính",
    desc: "Model Vision đối chiếu ảnh và sửa lỗi ký tự — tốn thêm thời gian xử lý ~2×.",
    badge: "Dành cho ảnh scan mờ",
  },
];

const PROMPT_PLAIN = "OCR:";
const PROMPT_MARKDOWN =
  "Convert the document in this image into Markdown format, preserving layout, tables, and formulas.";
const PROMPT_VISION_DEFAULT =
  "Hãy trích xuất toàn bộ chữ trong ảnh trang tài liệu này, đúng nguyên văn từng chữ. Giữ nguyên số hiệu văn bản, ngày tháng, con số và chữ viết tắt. Nếu có bảng, dựng lại thành bảng Markdown. Dựng lại cấu trúc Phần, Chương, Điều, Khoản nếu có. Chỉ trả về nội dung đã trích xuất, không thêm lời chào, giải thích hay nhận xét.";

type PromptMode = "plain" | "markdown" | "custom";

export function OcrSettingsCard({ id = "ocr-settings-card" }: { id?: string } = {}) {
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
  const [resultTab, setResultTab] = useState<"refined" | "raw">("refined");
  const [modeSaving, setModeSaving] = useState(false);
  const [modeError, setModeError] = useState("");
  const [visionCatalog, setVisionCatalog] = useState<{ active_spec_id: string | null; specs: Array<{ id: string; label: string }> } | null>(null);

  // Prompt configuration
  const [promptMode, setPromptMode] = useState<PromptMode>("plain");
  const [customPrompt, setCustomPrompt] = useState<string>("");
  const [promptSaving, setPromptSaving] = useState(false);
  const [promptSaved, setPromptSaved] = useState(false);
  const [promptError, setPromptError] = useState("");
  const [showPromptDetails, setShowPromptDetails] = useState(false);

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    try {
      const [s, cat, vCat] = await Promise.all([
        api<Record<string, unknown>>("/api/settings"),
        api<OcrCatalog>("/api/settings/ocr/catalog"),
        api<{ active_spec_id: string | null; specs: Array<{ id: string; label: string }> }>("/api/settings/vision/catalog").catch(() => null),
      ]);
      setCatalog(cat);
      setSettings(s);
      setVisionCatalog(vCat);

      const rawMode = (s.ocr_prompt_mode as string) || "plain";
      const validMode: PromptMode =
        rawMode === "plain" || rawMode === "markdown" || rawMode === "custom" ? rawMode : "plain";
      setPromptMode(validMode);

      if (typeof s.ocr_prompt === "string" && s.ocr_prompt.trim()) {
        setCustomPrompt(s.ocr_prompt);
      } else {
        setCustomPrompt(PROMPT_VISION_DEFAULT);
      }

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
  const activeVisionModel = visionCatalog?.specs.find((x) => x.id === visionCatalog.active_spec_id) ?? null;
  const willSwitch = !!selectedModel && selectedModel.id !== catalog?.active_spec_id;
  const conn = connResult && connResult.id === selectedId ? connResult : null;
  const refineMode = settings.ocr_llm_refine === "true" || settings.ocr_llm_refine === true;

  const isDedicatedOcr = (model: OcrModel | null) => {
    if (!model) return false;
    if (model.custom) return true;
    const lower = (model.model_id + " " + model.label).toLowerCase();
    return (
      lower.includes("senocr") ||
      lower.includes("paddle") ||
      lower.includes("hunyuan") ||
      lower.includes("glm-ocr") ||
      lower.includes("ocr")
    );
  };

  const selectedIsDedicated = isDedicatedOcr(selectedModel);

  // Compute what prompt string will be sent
  const effectivePrompt =
    promptMode === "plain"
      ? PROMPT_PLAIN
      : promptMode === "markdown"
        ? PROMPT_MARKDOWN
        : customPrompt.trim() || PROMPT_PLAIN;

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

  async function handleSavePromptConfig(targetMode: PromptMode, promptText?: string) {
    setPromptSaving(true);
    setPromptSaved(false);
    setPromptError("");
    const textToSave = promptText !== undefined ? promptText : customPrompt;
    try {
      await api("/api/settings", {
        method: "PUT",
        body: {
          settings: {
            ocr_prompt_mode: targetMode,
            ocr_prompt: textToSave.trim(),
          },
        },
      });
      setPromptMode(targetMode);
      if (promptText !== undefined) setCustomPrompt(promptText);
      setSettings((s) => ({
        ...s,
        ocr_prompt_mode: targetMode,
        ocr_prompt: textToSave.trim(),
      }));
      setPromptSaved(true);
      setTimeout(() => setPromptSaved(false), 2500);
    } catch (err) {
      setPromptError(err instanceof Error ? err.message : "Không lưu được cấu hình prompt");
    } finally {
      setPromptSaving(false);
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
    formData.append("llm_refine", String(refineMode));
    formData.append("override_prompt", effectivePrompt);
    setResultTab("refined");

    try {
      const res = await api<OCRResponse>("/api/settings/test-ocr", {
        method: "POST",
        body: formData,
        timeoutMs: refineMode ? 360_000 : 180_000,
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
  const hasGarbageTokens = !!(
    testResult?.text &&
    (testResult.text.includes("LOC_") || testResult.text.includes("boldsymbol"))
  );

  return (
    <div id={id} className="rounded-2xl border border-border/80 bg-card p-6 shadow-sahara flex flex-col gap-6 scroll-mt-6">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <span className="material-symbols-outlined text-[22px]">photo_camera</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-foreground">Dịch vụ OCR</h2>
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
              vLLM / Vision Engine
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Model trích xuất văn bản từ trang scan hoặc ảnh chụp tài liệu phục vụ lập chỉ mục RAG &amp; Wiki.
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
          {/* Model picker & activation */}
          <div className="flex flex-col gap-3">
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
                className="h-9 gap-1.5 text-xs font-medium"
                title="Gửi request kiểm tra tới endpoint OCR đang chọn"
              >
                <span className={`material-symbols-outlined text-sm ${testingConn ? "animate-spin" : ""}`}>
                  {testingConn ? "progress_activity" : "network_ping"}
                </span>
                Kiểm tra kết nối
              </Button>
              {conn && (
                <span
                  className={`flex items-center gap-1.5 text-xs ${
                    conn.success ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                  }`}
                >
                  <span className="material-symbols-outlined text-sm">{conn.success ? "check_circle" : "error"}</span>
                  <span className="max-w-[320px] truncate" title={conn.message}>
                    {conn.message}
                  </span>
                  {conn.latency_ms > 0 && <span className="font-mono text-[11px]">({conn.latency_ms} ms)</span>}
                </span>
              )}
            </ActivateBar>
          </div>

          {/* Model guidance banner when selecting SenOCR-Vi */}
          {selectedIsDedicated && (
            <div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 p-3 text-xs">
              <span className="material-symbols-outlined text-primary text-lg mt-0.5">verified</span>
              <div className="flex-1 space-y-1">
                <p className="font-semibold text-foreground">
                  Đang chọn Model OCR chuyên dụng ({selectedModel?.label})
                </p>
                <p className="text-[11px] leading-relaxed text-muted-foreground">
                  Model lightweight (0.95B) được tinh chỉnh chuyên sâu cho tiếng Việt. Cần sử dụng prompt chuẩn tác vụ{" "}
                  <code className="rounded bg-primary/10 px-1 py-0.5 font-mono font-semibold text-primary">OCR:</code>{" "}
                  để giữ nguyên văn bản, bảng biểu và tránh sinh toạ độ rác <code>&lt;LOC_...&gt;</code>.
                </p>
              </div>
            </div>
          )}

          {/* Prompt configuration */}
          <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-muted/15 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-base text-primary">chat</span>
                <div>
                  <span className="text-xs font-semibold text-foreground">Prompt OCR tiêu chuẩn</span>
                  <p className="text-[11px] text-muted-foreground">
                    Câu lệnh chỉ dẫn tác vụ gửi kèm ảnh văn bản tới model OCR.
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {promptSaved && (
                  <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <span className="material-symbols-outlined text-sm">check</span>
                    Đã lưu cấu hình prompt!
                  </span>
                )}
                {promptError && <span className="text-[11px] text-destructive">{promptError}</span>}
              </div>
            </div>

            {/* Prompt Mode Radio Cards */}
            <div role="radiogroup" aria-label="Chế độ Prompt OCR" className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
              {/* Option 1: OCR: (Plain) */}
              <button
                type="button"
                role="radio"
                aria-checked={promptMode === "plain"}
                onClick={() => void handleSavePromptConfig("plain")}
                disabled={promptSaving}
                className={`relative flex flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition-all ${
                  promptMode === "plain"
                    ? "border-primary bg-primary/10 shadow-sm"
                    : "border-border/80 bg-card hover:border-primary/40 hover:bg-accent/30"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="font-mono text-xs font-bold text-foreground">OCR:</span>
                  <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-600 dark:text-emerald-400">
                    Khuyên dùng
                  </span>
                </div>
                <span className="text-xs font-medium text-foreground">Tối giản chuẩn (Plain)</span>
                <span className="text-[11px] leading-snug text-muted-foreground">
                  Gửi lệnh chuẩn <code className="font-mono font-semibold">OCR:</code>. Chống sinh toạ độ <code>LOC_</code>, LaTeX, tiếng Trung cho SenOCR-Vi.
                </span>
                {promptMode === "plain" && (
                  <span className="material-symbols-outlined absolute top-2 right-2 text-sm text-primary">
                    check_circle
                  </span>
                )}
              </button>

              {/* Option 2: Markdown */}
              <button
                type="button"
                role="radio"
                aria-checked={promptMode === "markdown"}
                onClick={() => void handleSavePromptConfig("markdown")}
                disabled={promptSaving}
                className={`relative flex flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition-all ${
                  promptMode === "markdown"
                    ? "border-primary bg-primary/10 shadow-sm"
                    : "border-border/80 bg-card hover:border-primary/40 hover:bg-accent/30"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="font-mono text-xs font-bold text-foreground">Markdown</span>
                  <span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[9px] font-medium text-blue-600 dark:text-blue-400">
                    Bảng biểu
                  </span>
                </div>
                <span className="text-xs font-medium text-foreground">Cấu trúc Markdown</span>
                <span className="text-[11px] leading-snug text-muted-foreground">
                  Yêu cầu trích xuất bảng và công thức sang Markdown. Phù hợp HunyuanOCR hoặc model đa năng.
                </span>
                {promptMode === "markdown" && (
                  <span className="material-symbols-outlined absolute top-2 right-2 text-sm text-primary">
                    check_circle
                  </span>
                )}
              </button>

              {/* Option 3: Custom */}
              <button
                type="button"
                role="radio"
                aria-checked={promptMode === "custom"}
                onClick={() => {
                  setPromptMode("custom");
                  setShowPromptDetails(true);
                }}
                disabled={promptSaving}
                className={`relative flex flex-col items-start gap-1.5 rounded-xl border p-3 text-left transition-all ${
                  promptMode === "custom"
                    ? "border-primary bg-primary/10 shadow-sm"
                    : "border-border/80 bg-card hover:border-primary/40 hover:bg-accent/30"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <span className="font-mono text-xs font-bold text-foreground">Custom</span>
                  <span className="rounded bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
                    Tùy biến
                  </span>
                </div>
                <span className="text-xs font-medium text-foreground">Prompt tự chọn</span>
                <span className="text-[11px] leading-snug text-muted-foreground">
                  Nhập câu lệnh riêng biệt hoặc dùng prompt bóc tách chi tiết cho các Vision LLM lớn.
                </span>
                {promptMode === "custom" && (
                  <span className="material-symbols-outlined absolute top-2 right-2 text-sm text-primary">
                    check_circle
                  </span>
                )}
              </button>
            </div>

            {/* Prompt preview / details */}
            <div className="rounded-lg border border-border/80 bg-background/80 p-3">
              <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1.5">
                <span className="flex items-center gap-1 font-medium text-foreground">
                  <span className="material-symbols-outlined text-sm text-primary">terminal</span>
                  Nội dung prompt thực tế sẽ gửi tới model:
                </span>
                <button
                  type="button"
                  onClick={() => setShowPromptDetails(!showPromptDetails)}
                  className="text-primary hover:underline flex items-center gap-0.5"
                >
                  <span className="material-symbols-outlined text-xs">
                    {showPromptDetails ? "expand_less" : "tune"}
                  </span>
                  {showPromptDetails ? "Thu gọn tùy chỉnh" : "Chỉnh sửa câu lệnh"}
                </button>
              </div>

              {showPromptDetails || promptMode === "custom" ? (
                <div className="flex flex-col gap-2 mt-2">
                  <textarea
                    value={promptMode === "custom" ? customPrompt : effectivePrompt}
                    onChange={(e) => {
                      setCustomPrompt(e.target.value);
                      if (promptMode !== "custom") setPromptMode("custom");
                    }}
                    rows={3}
                    placeholder="Nhập prompt gửi kèm ảnh..."
                    className="w-full rounded-md border border-input bg-muted/20 p-2 font-mono text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px]">
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setCustomPrompt(PROMPT_PLAIN);
                          void handleSavePromptConfig("plain", PROMPT_PLAIN);
                        }}
                        className="rounded border border-border bg-card px-2 py-0.5 text-foreground hover:bg-accent"
                      >
                        Đặt lại &quot;OCR:&quot;
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCustomPrompt(PROMPT_MARKDOWN);
                          void handleSavePromptConfig("markdown", PROMPT_MARKDOWN);
                        }}
                        className="rounded border border-border bg-card px-2 py-0.5 text-foreground hover:bg-accent"
                      >
                        Đặt lại &quot;Markdown&quot;
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCustomPrompt(PROMPT_VISION_DEFAULT);
                          setPromptMode("custom");
                        }}
                        className="rounded border border-border bg-card px-2 py-0.5 text-foreground hover:bg-accent"
                      >
                        Nạp mẫu Vision Tiếng Việt
                      </button>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => void handleSavePromptConfig(promptMode, customPrompt)}
                      disabled={promptSaving}
                      className="h-7 text-xs font-medium"
                    >
                      {promptSaving ? "Đang lưu..." : "Lưu prompt tùy chỉnh"}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="rounded border border-border/50 bg-muted/30 px-3 py-2 font-mono text-xs text-foreground select-all break-words">
                  {effectivePrompt}
                </div>
              )}
            </div>
          </div>

          {/* Processing mode (Chỉ OCR vs OCR + LLM hiệu đính) */}
          <div className="flex flex-col gap-2">
            <span className="text-xs font-semibold text-foreground">Chế độ xử lý trang scan</span>
            <div role="radiogroup" aria-label="Chế độ xử lý trang scan" className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
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
                    className={`flex items-start gap-2.5 rounded-xl border p-3 text-left transition-colors disabled:opacity-60 ${
                      on ? "border-primary bg-primary/5 shadow-sm" : "border-border hover:bg-accent/30"
                    }`}
                  >
                    <span className={`material-symbols-outlined text-lg ${on ? "text-primary" : "text-muted-foreground"}`}>
                      {m.icon}
                    </span>
                    <span className="flex flex-col gap-0.5 flex-1 min-w-0">
                      <span className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-foreground">{m.title}</span>
                        {m.badge && (
                          <span
                            className={`rounded px-1.5 py-0.2 text-[9px] font-medium ${
                              m.refine
                                ? "bg-muted text-muted-foreground"
                                : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-semibold"
                            }`}
                          >
                            {m.badge}
                          </span>
                        )}
                      </span>
                      <span className="text-[11px] leading-snug text-muted-foreground">{m.desc}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {refineMode && (
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/80 bg-muted/40 p-2.5 text-xs">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-base text-primary">visibility</span>
                  <span className="text-muted-foreground">Vision Model dùng để hiệu đính:</span>
                  {activeVisionModel ? (
                    <span className="inline-flex items-center gap-1.5 font-semibold text-foreground">
                      {activeVisionModel.label}
                      <span className="rounded bg-emerald-500/15 px-1.5 py-0.2 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                        Đang hoạt động
                      </span>
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 font-medium text-amber-600 dark:text-amber-400">
                      <span className="material-symbols-outlined text-sm">warning</span>
                      Chưa cấu hình Vision Model
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    document.getElementById("vision-model-card")?.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
                >
                  {activeVisionModel ? "Xem Vision Model" : "Cấu hình Vision Model ngay"}
                  <span className="material-symbols-outlined text-xs">arrow_downward</span>
                </button>
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">
              {refineMode
                ? "Bước hiệu đính sẽ dùng model đang chọn ở mục Vision Model để đối chiếu văn bản thô."
                : "Chế độ 'Chỉ OCR' bảo đảm giữ nguyên 100% số hiệu, ngày tháng và bảng biểu công văn theo kết quả quét."}
              {modeSaving && " Đang lưu…"}
            </p>
            {modeError && <p className="text-xs text-destructive">{modeError}</p>}
          </div>

          {/* Test lab */}
          <div className="rounded-xl border border-border/70 bg-muted/10 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                <span className="material-symbols-outlined text-sm text-primary">science</span>
                Thử nghiệm OCR trực tiếp
              </span>
              <div className="flex items-center gap-2 text-[11px]">
                {selectedModel && (
                  <span className="rounded bg-background px-2 py-0.5 border border-border/80 text-muted-foreground">
                    Model: <strong className="text-foreground">{selectedModel.label}</strong>
                  </span>
                )}
                <span className="rounded bg-background px-2 py-0.5 border border-border/80 text-muted-foreground">
                  Prompt: <strong className="font-mono text-foreground">{promptMode === "plain" ? "OCR:" : promptMode}</strong>
                </span>
              </div>
            </div>

            {hasGarbageTokens && (
              <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-700 dark:text-amber-300">
                <span className="material-symbols-outlined text-sm">warning</span>
                <span>
                  Phát hiện ký tự lạ hoặc mã toạ độ layout trong kết quả. Hãy chọn chế độ Prompt <strong>&quot;OCR:&quot;</strong> ở trên để loại bỏ hoàn toàn các ký tự này.
                </span>
              </div>
            )}

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

                <div className="flex items-center justify-between rounded-lg border border-border/80 bg-background px-3 py-2 text-xs">
                  <span className="text-muted-foreground">Chế độ đang dùng:</span>
                  <span className="inline-flex items-center gap-1 font-semibold text-foreground">
                    <span className="material-symbols-outlined text-sm text-primary">
                      {refineMode ? "auto_fix_high" : "bolt"}
                    </span>
                    {refineMode ? "OCR + LLM hiệu đính" : "Chỉ OCR"}
                  </span>
                </div>

                <Button
                  size="sm"
                  onClick={handleRunOcr}
                  disabled={!testFile || !selectedModel || testLoading}
                  className="h-9 w-full gap-2 text-xs font-medium"
                >
                  <span className={`material-symbols-outlined text-sm ${testLoading ? "animate-spin" : ""}`}>
                    {testLoading ? "progress_activity" : refineMode ? "auto_fix_high" : "document_scanner"}
                  </span>
                  {testLoading
                    ? refineMode
                      ? "Đang OCR + hiệu đính..."
                      : "Đang nhận diện OCR..."
                    : refineMode
                      ? "Chạy OCR + LLM hiệu đính"
                      : "Chạy OCR"}
                </Button>
                <p className="text-[11px] text-muted-foreground">
                  Gửi ảnh tới model đang chọn với prompt{" "}
                  <code className="font-mono font-semibold text-foreground">
                    {promptMode === "plain" ? "OCR:" : promptMode}
                  </code>
                  .
                </p>
              </div>

              <div className="lg:col-span-8">
                <PreviewStudio
                  title="Kết quả OCR"
                  icon="text_fields"
                  loading={testLoading}
                  loadingTitle={refineMode ? "Đang nhận diện và hiệu đính văn bản..." : "Đang trích xuất nội dung văn bản..."}
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
                          { key: "refined", label: "Sau hiệu đính" },
                          { key: "raw", label: "Bản thô OCR" },
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
