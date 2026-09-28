"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

const DEFAULT_OCR_PROMPT =
  "Trích xuất TOÀN BỘ văn bản từ hình ảnh trang tài liệu này một cách chính xác tuyệt đối.\n" +
  "Yêu cầu nghiêm ngặt:\n" +
  "1. Giữ nguyên số hiệu văn bản, tiêu đề, dấu câu, ngày tháng, các cụm từ viết tắt ngành (CAND, CSGT, PCCC, ANTT, QĐ, NĐ, TT...).\n" +
  "2. Tái tạo chính xác cấu trúc bảng biểu dạng Markdown Table (| Cột 1 | Cột 2 |).\n" +
  "3. Tái tạo cấu trúc thứ bậc đề mục: Phần, Chương, Mục, Điều, Khoản, Điểm.\n" +
  "4. Tuyệt đối không thêm lời bình, không tóm tắt hay tự ý suy diễn từ ngữ.";

type SettingsMap = Record<string, string | null | undefined>;

export function DocumentProcessingSettingsCard() {
  const [ocrBaseUrl, setOcrBaseUrl] = useState("");
  const [ocrApiKey, setOcrApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [ocrModel, setOcrModel] = useState("ggml-org/GLM-OCR-GGUF:f16");
  const [ocrPrompt, setOcrPrompt] = useState(DEFAULT_OCR_PROMPT);
  const [ocrMode, setOcrMode] = useState("auto");
  const [ocrFallbackVision, setOcrFallbackVision] = useState(true);

  const [pdfEngine, setPdfEngine] = useState("pymupdf4llm");
  const [stripHeaders, setStripHeaders] = useState(true);
  const [enhanceHeadings, setEnhanceHeadings] = useState(true);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState("");

  const [testingConn, setTestingConn] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    latency_ms: number;
  } | null>(null);

  useEffect(() => {
    void loadSettings();
  }, []);

  async function loadSettings() {
    setLoading(true);
    setSaveError("");
    try {
      const data = await api<SettingsMap>("/api/settings");
      if (data) {
        if (data.ocr_base_url) setOcrBaseUrl(String(data.ocr_base_url));
        if (data.ocr_api_key) setOcrApiKey(String(data.ocr_api_key));
        if (data.ocr_model) setOcrModel(String(data.ocr_model));
        if (data.ocr_prompt) setOcrPrompt(String(data.ocr_prompt));
        if (data.ocr_mode) setOcrMode(String(data.ocr_mode));
        if (data.ocr_fallback_vision !== undefined) {
          setOcrFallbackVision(data.ocr_fallback_vision !== "false");
        }
        if (data.pdf_parser_engine) setPdfEngine(String(data.pdf_parser_engine));
        if (data.pdf_strip_headers_footers !== undefined) {
          setStripHeaders(data.pdf_strip_headers_footers !== "false");
        }
        if (data.pdf_enhance_headings !== undefined) {
          setEnhanceHeadings(data.pdf_enhance_headings !== "false");
        }
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Không thể tải cấu hình");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError("");

    const payload: Record<string, string> = {
      ocr_base_url: ocrBaseUrl.trim(),
      ocr_api_key: ocrApiKey.trim(),
      ocr_model: ocrModel.trim(),
      ocr_prompt: ocrPrompt.trim(),
      ocr_mode: ocrMode,
      ocr_fallback_vision: ocrFallbackVision ? "true" : "false",
      pdf_parser_engine: pdfEngine,
      pdf_strip_headers_footers: stripHeaders ? "true" : "false",
      pdf_enhance_headings: enhanceHeadings ? "true" : "false",
    };

    try {
      await api("/api/settings", {
        method: "PUT",
        body: { settings: payload },
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Lỗi khi lưu cấu hình");
    } finally {
      setSaving(false);
    }
  }

  async function handleTestConnection() {
    setTestingConn(true);
    setTestResult(null);
    try {
      const res = await api<{ success: boolean; message: string; latency_ms: number }>(
        "/api/settings/test-ocr-connection",
        {
          method: "POST",
          body: {
            base_url: ocrBaseUrl.trim() || undefined,
            api_key: ocrApiKey.trim() || undefined,
            model: ocrModel.trim() || undefined,
          },
        }
      );
      setTestResult(res);
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : "Kết nối thất bại",
        latency_ms: 0,
      });
    } finally {
      setTestingConn(false);
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between mb-6 pb-4 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <span className="material-symbols-outlined text-2xl">document_scanner</span>
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              Cấu hình Bóc tách Tài liệu & OCR
            </h2>
            <p className="text-sm text-muted-foreground">
              Tùy chỉnh mô hình OCR chuyên dụng, engine trích xuất PDF và các bước tiền xử lý đề mục.
            </p>
          </div>
        </div>

        {saveSuccess && (
          <Badge variant="outline" className="text-emerald-600 border-emerald-500/30 bg-emerald-500/10 gap-1.5 self-start sm:self-auto">
            <span className="material-symbols-outlined text-sm">check_circle</span>
            Đã lưu thành công
          </Badge>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10 text-muted-foreground gap-2">
          <span className="material-symbols-outlined animate-spin text-xl">progress_activity</span>
          <span>Đang tải thông số cấu hình...</span>
        </div>
      ) : (
        <div className="space-y-8">
          {/* PHẦN 1: OCR SERVICE */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  1. Dịch vụ OCR Chuyên dụng (OpenAI-Compatible)
                </h3>
                <p className="text-xs text-muted-foreground">
                  Sử dụng GLM-OCR hoặc mô hình Vision tương thích OpenAI để quét chữ từ ảnh tài liệu scan.
                </p>
              </div>

              <Button
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testingConn}
                className="gap-1.5 h-8 text-xs font-medium"
              >
                {testingConn ? (
                  <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                ) : (
                  <span className="material-symbols-outlined text-sm">network_ping</span>
                )}
                Kiểm tra kết nối
              </Button>
            </div>

            {testResult && (
              <div
                className={`p-3 rounded-lg text-xs flex items-center justify-between border ${
                  testResult.success
                    ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-400"
                    : "bg-destructive/10 border-destructive/20 text-destructive"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-base">
                    {testResult.success ? "check_circle" : "error"}
                  </span>
                  <span>{testResult.message}</span>
                </div>
                {testResult.latency_ms > 0 && (
                  <span className="font-mono font-medium">
                    {testResult.latency_ms} ms
                  </span>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="ocr-base-url" className="text-xs font-medium">
                  OCR Base URL
                </Label>
                <Input
                  id="ocr-base-url"
                  placeholder="https://unsloth.anm05.com/v1"
                  value={ocrBaseUrl}
                  onChange={(e) => setOcrBaseUrl(e.target.value)}
                  className="font-mono text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="ocr-api-key" className="text-xs font-medium">
                  OCR API Key
                </Label>
                <div className="relative">
                  <Input
                    id="ocr-api-key"
                    type={showApiKey ? "text" : "password"}
                    placeholder="sk-..."
                    value={ocrApiKey}
                    onChange={(e) => setOcrApiKey(e.target.value)}
                    className="font-mono text-xs pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    title={showApiKey ? "Ẩn" : "Hiện"}
                  >
                    <span className="material-symbols-outlined text-base">
                      {showApiKey ? "visibility_off" : "visibility"}
                    </span>
                  </button>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="ocr-model" className="text-xs font-medium">
                  Mô hình OCR (Model Name)
                </Label>
                <Input
                  id="ocr-model"
                  placeholder="ggml-org/GLM-OCR-GGUF:f16"
                  value={ocrModel}
                  onChange={(e) => setOcrModel(e.target.value)}
                  className="font-mono text-xs"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="ocr-mode" className="text-xs font-medium">
                  Chế độ OCR (Quét chữ)
                </Label>
                <Select value={ocrMode} onValueChange={setOcrMode}>
                  <SelectTrigger id="ocr-mode" className="text-xs">
                    <SelectValue placeholder="Chọn chế độ" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">
                      Tự động (Chỉ chạy OCR với trang scan / ảnh) - Khuyến nghị
                    </SelectItem>
                    <SelectItem value="force_ocr">
                      Ép OCR toàn bộ (Chạy OCR với tất cả các trang)
                    </SelectItem>
                    <SelectItem value="disabled">
                      Tắt OCR (Chỉ lấy văn bản số hóa gốc trong PDF)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="ocr-prompt" className="text-xs font-medium">
                  Chỉ thị OCR Prompt
                </Label>
                <button
                  type="button"
                  onClick={() => setOcrPrompt(DEFAULT_OCR_PROMPT)}
                  className="text-xs text-primary hover:underline"
                >
                  Khôi phục mặc định
                </button>
              </div>
              <Textarea
                id="ocr-prompt"
                rows={3}
                value={ocrPrompt}
                onChange={(e) => setOcrPrompt(e.target.value)}
                className="text-xs font-sans resize-y"
              />
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/30">
              <div className="space-y-0.5">
                <Label htmlFor="ocr-fallback-vision" className="text-xs font-medium">
                  Fallback sang Vision Model khi OCR lỗi
                </Label>
                <p className="text-[11px] text-muted-foreground">
                  Nếu endpoint OCR chuyên dụng gặp sự cố hoặc timeout, hệ thống sẽ tự động dùng mô hình Vision đã cấu hình để cứu cánh.
                </p>
              </div>
              <Switch
                id="ocr-fallback-vision"
                checked={ocrFallbackVision}
                onCheckedChange={setOcrFallbackVision}
              />
            </div>
          </div>

          {/* PHẦN 2: PDF PARSER & HEURISTICS */}
          <div className="space-y-4 pt-4 border-t border-border">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                2. Bộ máy Trích xuất PDF & Tiền xử lý Văn bản
              </h3>
              <p className="text-xs text-muted-foreground">
                Định dạng cấu trúc bảng biểu Markdown và chuẩn hóa tiêu đề pháp lý Việt Nam.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="pdf-engine" className="text-xs font-medium">
                  Công cụ phân tích PDF (PDF Parser Engine)
                </Label>
                <Select value={pdfEngine} onValueChange={setPdfEngine}>
                  <SelectTrigger id="pdf-engine" className="text-xs">
                    <SelectValue placeholder="Chọn engine" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="pymupdf4llm">
                      PyMuPDF4LLM (Khuyên dùng: giữ nguyên cấu trúc bảng biểu, heading Markdown)
                    </SelectItem>
                    <SelectItem value="pymupdf_plain">
                      PyMuPDF Plain Text (Trích xuất văn bản thuần fitz get_text, tốc độ nhanh)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/30">
                <div className="space-y-0.5">
                  <Label htmlFor="strip-headers" className="text-xs font-medium">
                    Tự động lọc tiêu ngữ, đầu trang & chân trang lặp lại
                  </Label>
                  <p className="text-[11px] text-muted-foreground">
                    Loại bỏ &quot;CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM&quot;, số trang (trang 1/10) lặp lại trên &gt; 50% số trang để tránh nhiễu nội dung.
                  </p>
                </div>
                <Switch
                  id="strip-headers"
                  checked={stripHeaders}
                  onCheckedChange={setStripHeaders}
                />
              </div>

              <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/30">
                <div className="space-y-0.5">
                  <Label htmlFor="enhance-headings" className="text-xs font-medium">
                    Chuẩn hóa cấu trúc đề mục pháp lý tiếng Việt
                  </Label>
                  <p className="text-[11px] text-muted-foreground">
                    Tự động nhận diện và gán thứ bậc Markdown (#, ##, ###) cho Phần, Chương, Mục, Điều, Khoản.
                  </p>
                </div>
                <Switch
                  id="enhance-headings"
                  checked={enhanceHeadings}
                  onCheckedChange={setEnhanceHeadings}
                />
              </div>
            </div>
          </div>

          {saveError && (
            <p className="text-xs text-destructive font-medium">{saveError}</p>
          )}

          <div className="flex justify-end pt-2">
            <Button
              onClick={handleSave}
              disabled={saving}
              className="gap-2 px-5 font-medium"
            >
              {saving ? (
                <span className="material-symbols-outlined animate-spin text-base">progress_activity</span>
              ) : (
                <span className="material-symbols-outlined text-base">save</span>
              )}
              Lưu cấu hình bóc tách & OCR
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
