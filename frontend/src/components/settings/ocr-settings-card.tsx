"use client";

import { useEffect, useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { WikiContent } from "@/components/wiki/wiki-content";

type SettingsMap = Record<string, string | null | undefined>;

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
};

export function OcrSettingsCard() {
  // Config state
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("ggml-org/GLM-OCR-GGUF:f16");
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [testingConn, setTestingConn] = useState(false);
  const [connResult, setConnResult] = useState<{
    success: boolean;
    message: string;
    latency_ms: number;
  } | null>(null);

  // Test / Preview state
  const [testFile, setTestFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [targetPage, setTargetPage] = useState<number>(1);
  const [isDragging, setIsDragging] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState<OCRResponse | null>(null);
  const [viewMode, setViewMode] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    async function loadSettings() {
      setLoading(true);
      setSaveError("");
      try {
        const data = await api<SettingsMap>("/api/settings");
        if (data) {
          if (data.ocr_base_url) setBaseUrl(String(data.ocr_base_url));
          if (data.ocr_model) setModel(String(data.ocr_model));
          if (data.ocr_api_key) setApiKey(String(data.ocr_api_key));
        }
      } catch (err) {
        setSaveError(err instanceof Error ? err.message : "Không thể tải cấu hình OCR");
      } finally {
        setLoading(false);
      }
    }
    void loadSettings();
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError("");

    try {
      await api("/api/settings", {
        method: "PUT",
        body: {
          settings: {
            ocr_base_url: baseUrl.trim(),
            ocr_model: model.trim(),
            ocr_api_key: apiKey.trim(),
          },
        },
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Lỗi khi lưu cấu hình OCR");
    } finally {
      setSaving(false);
    }
  }

  async function handleTestConnection() {
    setTestingConn(true);
    setConnResult(null);
    try {
      const res = await api<{ success: boolean; message: string; latency_ms: number }>(
        "/api/settings/test-ocr-connection",
        {
          method: "POST",
          body: {
            base_url: baseUrl.trim() || undefined,
            model: model.trim() || undefined,
            api_key: apiKey.trim() || undefined,
          },
        }
      );
      setConnResult(res);
    } catch (err) {
      setConnResult({
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

    if (file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setImagePreviewUrl(url);
    } else {
      setImagePreviewUrl(null);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  async function handleRunOcr() {
    if (!testFile) return;
    setTestLoading(true);
    setTestResult(null);

    const formData = new FormData();
    formData.append("file", testFile);
    formData.append("target_page", String(targetPage));
    if (baseUrl.trim()) formData.append("override_base_url", baseUrl.trim());
    if (model.trim()) formData.append("override_model", model.trim());
    if (apiKey.trim()) formData.append("override_api_key", apiKey.trim());

    try {
      const res = await api<OCRResponse>("/api/settings/test-ocr", {
        method: "POST",
        body: formData,
        timeoutMs: 180_000,
      });
      setTestResult(res);
    } catch (err) {
      setTestResult({
        success: false,
        text: "",
        model: model,
        latency_ms: 0,
        chars_count: 0,
        words_count: 0,
        error: err instanceof Error ? err.message : "Thực hiện OCR thất bại",
      });
    } finally {
      setTestLoading(false);
    }
  }

  function handleCopy(text: string) {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDownloadMarkdown() {
    if (!testResult?.text) return;
    const blob = new Blob([testResult.text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ocr_${testFile?.name || "result"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const isPdf = testFile?.name.toLowerCase().endsWith(".pdf");

  return (
    <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.04)] dark:shadow-[0_4px_24px_-4px_rgba(0,0,0,0.25)] transition-all">
      {/* Header Bar */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-6 pb-4 border-b border-border/60">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 shadow-xs">
            <span className="material-symbols-outlined text-[26px]">photo_camera</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold tracking-tight text-foreground">
                Cấu hình Dịch vụ OCR
              </h2>
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-muted-foreground border border-border">
                Vision Engine
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Dịch vụ OCR OpenAI-compatible cho tài liệu scan, bản vẽ và ảnh chụp trang văn bản.
            </p>
          </div>
        </div>

        {saveSuccess && (
          <Badge
            variant="outline"
            className="text-emerald-600 border-emerald-500/30 bg-emerald-500/10 gap-1.5 self-start sm:self-auto py-1 px-3"
          >
            <span className="material-symbols-outlined text-sm">check_circle</span>
            Đã lưu cấu hình OCR
          </Badge>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground gap-2.5">
          <span className="material-symbols-outlined animate-spin text-xl text-primary">progress_activity</span>
          <span className="text-xs font-medium">Đang tải cấu hình OCR...</span>
        </div>
      ) : (
        /* Layout ngang 1 | 1 Cân đối */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* CỘT TRÁI (1): CẤU HÌNH & BÀN ĐIỀU KHIỂN (Col span 5/12) */}
          <div className="lg:col-span-5 space-y-5">
            {/* Box 1: Cấu hình Endpoint & Model */}
            <div className="rounded-xl border border-border/70 bg-muted/20 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-primary">dns</span>
                  Endpoint &amp; Model Credentials
                </span>

                <div className="flex items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleTestConnection}
                    disabled={testingConn}
                    className="gap-1 text-xs font-medium h-7 px-2.5 bg-background shadow-xs active:scale-[0.98]"
                    title="Kiểm tra độ trễ mạng tới OCR service"
                  >
                    {testingConn ? (
                      <span className="material-symbols-outlined animate-spin text-xs">progress_activity</span>
                    ) : (
                      <span className="material-symbols-outlined text-xs">network_ping</span>
                    )}
                    Ping test
                  </Button>

                  <Button
                    size="sm"
                    onClick={handleSave}
                    disabled={saving}
                    className="gap-1.5 text-xs font-medium h-7 px-3 shadow-xs active:scale-[0.98]"
                  >
                    {saving ? (
                      <span className="material-symbols-outlined animate-spin text-xs">progress_activity</span>
                    ) : (
                      <span className="material-symbols-outlined text-xs">save</span>
                    )}
                    Lưu
                  </Button>
                </div>
              </div>

              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="ocr-base-url" className="text-xs font-medium text-foreground">
                    OCR Base URL
                  </Label>
                  <Input
                    id="ocr-base-url"
                    placeholder="https://unsloth.anm05.com/v1"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    className="font-mono text-xs h-9 bg-background"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="ocr-model" className="text-xs font-medium text-foreground">
                      Mô hình (Model)
                    </Label>
                    <Input
                      id="ocr-model"
                      placeholder="ggml-org/GLM-OCR-GGUF:f16"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      className="font-mono text-xs h-9 bg-background"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="ocr-api-key" className="text-xs font-medium text-foreground">
                      API Key
                    </Label>
                    <div className="relative">
                      <Input
                        id="ocr-api-key"
                        type={showApiKey ? "text" : "password"}
                        placeholder="sk-..."
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        className="font-mono text-xs h-9 bg-background pr-8"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        title={showApiKey ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                      >
                        <span className="material-symbols-outlined text-sm">
                          {showApiKey ? "visibility_off" : "visibility"}
                        </span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Connection Ping Feedback Banner */}
                {connResult && (
                  <div
                    className={`p-2.5 rounded-lg text-xs flex items-center justify-between border transition-all ${
                      connResult.success
                        ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-700 dark:text-emerald-400 font-medium"
                        : "bg-destructive/10 border-destructive/25 text-destructive font-medium"
                    }`}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="material-symbols-outlined text-sm shrink-0">
                        {connResult.success ? "check_circle" : "error"}
                      </span>
                      <span className="truncate">{connResult.message}</span>
                    </div>
                    {connResult.latency_ms > 0 && (
                      <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-background/80 border border-emerald-500/20 shrink-0 ml-2">
                        {connResult.latency_ms} ms
                      </span>
                    )}
                  </div>
                )}
              </div>

              {saveError && (
                <div className="p-2 rounded-lg bg-destructive/10 text-destructive text-[11px] font-medium border border-destructive/20">
                  {saveError}
                </div>
              )}
            </div>

            {/* Box 2: Test Studio Dropzone */}
            <div className="rounded-xl border border-border/70 bg-card p-4 space-y-3.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-sm text-primary">photo_filter</span>
                  Phòng thử nghiệm OCR
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">Quét 1 trang</span>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,.pdf"
                className="hidden"
                onChange={handleFileSelect}
              />

              {/* Drag & Drop interactive zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`relative group cursor-pointer rounded-xl border-2 border-dashed p-4 transition-all duration-200 text-center flex flex-col items-center justify-center ${
                  isDragging
                    ? "border-emerald-500 bg-emerald-500/10 scale-[1.01]"
                    : testFile
                    ? "border-emerald-500/40 bg-emerald-500/5 hover:border-emerald-500/60"
                    : "border-border/80 hover:border-emerald-500/50 hover:bg-muted/30 bg-muted/15"
                }`}
              >
                {testFile ? (
                  <div className="w-full flex items-center justify-between gap-3 text-left">
                    <div className="flex items-center gap-3 overflow-hidden">
                      {imagePreviewUrl ? (
                        <div className="h-11 w-11 shrink-0 rounded-lg overflow-hidden border border-border/80 bg-background shadow-xs">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={imagePreviewUrl}
                            alt="Preview thumbnail"
                            className="h-full w-full object-cover"
                          />
                        </div>
                      ) : (
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-rose-500/10 text-rose-500 border border-rose-500/20 shadow-xs">
                          <span className="material-symbols-outlined text-xl">picture_as_pdf</span>
                        </div>
                      )}

                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <Badge
                            variant="outline"
                            className={`text-[9px] uppercase px-1.5 py-0 font-mono ${
                              isPdf
                                ? "bg-rose-500/10 text-rose-600 border-rose-500/20"
                                : "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
                            }`}
                          >
                            {isPdf ? "PDF" : testFile.name.split(".").pop()}
                          </Badge>
                          <p className="text-xs font-medium text-foreground truncate max-w-[170px]">
                            {testFile.name}
                          </p>
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          {(testFile.size / 1024).toFixed(1)} KB • Nhấn để đổi file
                        </p>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setTestFile(null);
                        setImagePreviewUrl(null);
                        setTestResult(null);
                      }}
                      className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors"
                      title="Gỡ file"
                    >
                      <span className="material-symbols-outlined text-base">close</span>
                    </button>
                  </div>
                ) : (
                  <div className="py-2 flex flex-col items-center">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 mb-2 group-hover:scale-110 transition-transform">
                      <span className="material-symbols-outlined text-xl">add_photo_alternate</span>
                    </div>
                    <p className="text-xs font-semibold text-foreground">
                      Kéo thả ảnh hoặc file PDF vào đây
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Hỗ trợ: PNG, JPG, JPEG, WEBP hoặc file tài liệu PDF scan
                    </p>
                  </div>
                )}
              </div>

              {/* PDF Target Page Stepper */}
              {isPdf && (
                <div className="flex items-center justify-between p-2 rounded-lg bg-muted/30 border border-border text-xs">
                  <span className="text-muted-foreground flex items-center gap-1 font-medium">
                    <span className="material-symbols-outlined text-sm text-rose-500">menu_book</span>
                    Chọn trang PDF để quét OCR:
                  </span>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setTargetPage((p) => Math.max(1, p - 1))}
                      className="h-7 w-7 rounded bg-background border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted active:scale-95 transition-all"
                      title="Trang trước"
                    >
                      <span className="material-symbols-outlined text-sm">chevron_left</span>
                    </button>
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={targetPage}
                      onChange={(e) => setTargetPage(Math.max(1, parseInt(e.target.value) || 1))}
                      className="w-12 h-7 text-xs text-center font-mono rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary font-semibold"
                    />
                    <button
                      type="button"
                      onClick={() => setTargetPage((p) => p + 1)}
                      className="h-7 w-7 rounded bg-background border border-border flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted active:scale-95 transition-all"
                      title="Trang tiếp"
                    >
                      <span className="material-symbols-outlined text-sm">chevron_right</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Action Button */}
              <Button
                size="sm"
                onClick={handleRunOcr}
                disabled={!testFile || testLoading}
                className="w-full gap-2 text-xs font-medium h-9 shadow-xs active:scale-[0.98] transition-all bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                {testLoading ? (
                  <>
                    <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                    Đang quét nhận diện OCR...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-sm">document_scanner</span>
                    Quét OCR &amp; Xem trước ngay
                  </>
                )}
              </Button>

              {testResult?.error && (
                <div className="p-3 rounded-lg border border-destructive/20 bg-destructive/10 text-destructive text-xs flex items-start gap-2">
                  <span className="material-symbols-outlined text-base shrink-0 mt-0.5">error</span>
                  <div className="space-y-1">
                    <p className="font-semibold">Quét OCR thất bại</p>
                    <p className="font-mono text-[11px] opacity-90 break-all">{testResult.error}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* CỘT PHẢI (2): STUDIO XEM TRƯỚC OCR (Col span 7/12) */}
          <div className="lg:col-span-7 flex flex-col h-full space-y-3">
            {/* Workbench Frame */}
            <div
              className={`rounded-xl border border-border/80 bg-card overflow-hidden shadow-xs flex flex-col transition-all duration-200 ${
                isExpanded ? "fixed inset-4 z-50 shadow-2xl bg-background" : "min-h-[460px]"
              }`}
            >
              {/* Studio Header Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 bg-muted/40 border-b border-border/70 text-xs select-none">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-base text-emerald-600 dark:text-emerald-400">
                      text_fields
                    </span>
                    Studio Nhận diện OCR
                  </span>

                  {testResult?.success && (
                    <Badge
                      variant="outline"
                      className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 gap-1 text-[10px] h-5 font-medium"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      OCR thành công
                    </Badge>
                  )}
                </div>

                {/* Right controls */}
                <div className="flex items-center gap-1.5">
                  {/* Mode switcher */}
                  <div className="flex rounded-md border border-border/80 p-0.5 bg-background shadow-2xs">
                    <button
                      onClick={() => setViewMode("rendered")}
                      className={`px-2.5 py-0.5 rounded text-[11px] font-medium transition-all ${
                        viewMode === "rendered"
                          ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                      title="Chế độ trực quan"
                    >
                      Rendered
                    </button>
                    <button
                      onClick={() => setViewMode("raw")}
                      className={`px-2.5 py-0.5 rounded text-[11px] font-medium transition-all ${
                        viewMode === "raw"
                          ? "bg-primary text-primary-foreground shadow-xs font-semibold"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                      title="Chế độ mã nguồn văn bản"
                    >
                      Raw
                    </button>
                  </div>

                  {testResult?.text && (
                    <>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopy(testResult.text)}
                        className="h-7 text-xs px-2 gap-1 text-muted-foreground hover:text-foreground"
                        title="Sao chép văn bản OCR"
                      >
                        <span className="material-symbols-outlined text-sm">
                          {copied ? "check" : "content_copy"}
                        </span>
                        {copied ? "Đã chép" : "Copy"}
                      </Button>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleDownloadMarkdown}
                        className="h-7 text-xs px-2 gap-1 text-muted-foreground hover:text-foreground"
                        title="Tải về file Markdown (.md)"
                      >
                        <span className="material-symbols-outlined text-sm">download</span>
                        Tải .md
                      </Button>
                    </>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsExpanded(!isExpanded)}
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                    title={isExpanded ? "Thu nhỏ" : "Toàn màn hình"}
                  >
                    <span className="material-symbols-outlined text-sm">
                      {isExpanded ? "close_fullscreen" : "open_in_full"}
                    </span>
                  </Button>
                </div>
              </div>

              {/* Telemetry bar (Stats pills) */}
              {testResult?.success && (
                <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-1.5 bg-muted/20 border-b border-border/50 text-[11px] font-mono text-muted-foreground">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px] text-muted-foreground">timer</span>
                      {testResult.latency_ms} ms
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <span className="material-symbols-outlined text-[13px] text-muted-foreground">format_quote</span>
                      {testResult.words_count.toLocaleString()} từ ({testResult.chars_count.toLocaleString()} ký tự)
                    </span>
                    {testResult.total_pages && testResult.total_pages > 1 && (
                      <>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <span className="material-symbols-outlined text-[13px] text-muted-foreground">layers</span>
                          Trang {testResult.page_number}/{testResult.total_pages}
                        </span>
                      </>
                    )}
                  </div>

                  <span className="px-2 py-0.2 rounded bg-background border border-border/60 text-[10px] text-foreground font-semibold">
                    {testResult.model || model}
                  </span>
                </div>
              )}

              {/* Studio Canvas / Viewport */}
              <div
                className={`relative flex-1 p-4 overflow-y-auto transition-all ${
                  isExpanded ? "max-h-[calc(100vh-140px)]" : "max-h-[380px]"
                }`}
              >
                {testLoading ? (
                  /* Animated High-tech Scanning State */
                  <div className="h-full min-h-[300px] flex flex-col items-center justify-center p-6 text-center space-y-4">
                    <div className="relative w-20 h-20 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center overflow-hidden shadow-inner">
                      <span className="material-symbols-outlined text-4xl text-emerald-600 dark:text-emerald-400 animate-pulse">
                        document_scanner
                      </span>
                      {/* Scanning laser beam */}
                      <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-emerald-400 to-transparent shadow-[0_0_12px_rgba(16,185,129,0.8)] animate-[scan_2s_ease-in-out_infinite]" />
                    </div>
                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-foreground">
                        Đang quét và nhận diện văn bản OCR...
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        Sử dụng mô hình Vision AI để số hóa ảnh trang tài liệu
                      </p>
                    </div>
                  </div>
                ) : testResult?.success && testResult.text ? (
                  viewMode === "rendered" ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none text-xs leading-relaxed">
                      <WikiContent markdown={testResult.text} />
                    </div>
                  ) : (
                    <div className="rounded-lg bg-slate-950 p-4 font-mono text-[11px] leading-relaxed text-slate-200 overflow-x-auto border border-slate-800 shadow-inner">
                      <pre className="whitespace-pre-wrap break-words">{testResult.text}</pre>
                    </div>
                  )
                ) : (
                  /* Empty State Workbench Canvas */
                  <div className="h-full min-h-[320px] flex flex-col items-center justify-center text-center p-6 text-muted-foreground">
                    <div className="w-14 h-14 rounded-2xl bg-muted/40 border border-border flex items-center justify-center mb-3 text-muted-foreground/60 shadow-xs">
                      <span className="material-symbols-outlined text-3xl">photo_camera</span>
                    </div>
                    <p className="text-xs font-semibold text-foreground">Chưa có kết quả OCR</p>
                    <p className="text-[11px] text-muted-foreground mt-1 max-w-[280px]">
                      Kéo thả ảnh hoặc file PDF ở cột bên trái và bấm &quot;Quét OCR &amp; Xem trước ngay&quot; để hiển thị kết quả tại đây.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
