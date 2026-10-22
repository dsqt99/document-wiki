import type { ProcessingQuality, QualityStatus, Source } from "../types";

export type QualityStage = {
  key: string;
  label: string;
  status: QualityStatus;
  metrics: { label: string; value: string }[];
};

export const QUALITY_LABELS: Record<QualityStatus, string> = {
  unknown: "Chưa xác định",
  pending: "Chờ xử lý",
  processing: "Đang xử lý",
  ready: "Hoàn tất",
  complete: "Hoàn tất",
  partial: "Một phần",
  error: "Lỗi",
  blocked: "Bị chặn",
};

function measured(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function count(value: number | null | undefined): string {
  return measured(value) ? value.toLocaleString("vi-VN") : "Chưa rõ";
}

function coverageStatus(status: QualityStatus | undefined, expected: number | null | undefined, actual: number | null | undefined, failed = 0): QualityStatus {
  if (!status || !Object.hasOwn(QUALITY_LABELS, status)) return "unknown";
  if (status !== "ready" && status !== "complete") return status;
  if (failed > 0 || (measured(expected) && measured(actual) && actual < expected)) return "partial";
  if (!measured(expected) || !measured(actual)) return "unknown";
  return status;
}

/** Use only measured observations; legacy aggregate readiness does not prove coverage. */
export function qualityStages(quality?: ProcessingQuality | null): QualityStage[] {
  const extraction = quality?.extraction;
  const index = quality?.source_index;
  const wiki = quality?.wiki;
  return [
    {
      key: "extraction",
      label: "Trích xuất nội dung",
      status: coverageStatus(extraction?.status, extraction?.total_pages, extraction?.text_pages, extraction?.empty_pages ?? 0),
      metrics: [
        { label: "Trang có văn bản / tổng", value: `${count(extraction?.text_pages)} / ${count(extraction?.total_pages)}` },
        { label: "Trang trống / bỏ qua", value: count(extraction?.empty_pages) },
        { label: "Trang OCR", value: count(extraction?.ocr_pages) },
      ],
    },
    {
      key: "source_index",
      label: "Chỉ mục nguồn gốc",
      status: coverageStatus(index?.status, index?.expected, index?.indexed),
      metrics: [{ label: "Đoạn đã lập chỉ mục / dự kiến", value: `${count(index?.indexed)} / ${count(index?.expected)}` }],
    },
    {
      key: "wiki",
      label: "Biên soạn Wiki",
      status: coverageStatus(wiki?.status, wiki?.expected, wiki?.published, wiki?.failed ?? 0),
      metrics: [
        { label: "Trang đã xuất bản / dự kiến", value: `${count(wiki?.published)} / ${count(wiki?.expected)}` },
        { label: "Trang thất bại", value: count(wiki?.failed) },
      ],
    },
  ];
}

export function qualitySummary(source: Pick<Source, "status" | "processing_quality">): string | null {
  if (source.status !== "ready") return null;
  const statuses = qualityStages(source.processing_quality).map((stage) => stage.status);
  if (statuses.some((status) => status === "error" || status === "blocked")) return "Có bước lỗi hoặc bị chặn";
  if (statuses.includes("partial")) return "Độ bao phủ chưa đầy đủ";
  if (statuses.includes("processing") || statuses.includes("pending")) return "Một số bước chưa hoàn tất";
  if (statuses.includes("unknown")) return "Chưa đo độ bao phủ";
  return null;
}

export function qualityWarningText(warning: ProcessingQuality["warnings"][number], quality?: ProcessingQuality | null): string {
  switch (warning.code) {
    case "empty_pages":
      return `${count(quality?.extraction?.empty_pages)} trang không có văn bản. Đối chiếu tệp gốc và chạy lại trích xuất nếu cần.`;
    case "unprocessed_pages":
      return "Một số trang chưa được trích xuất. Đối chiếu số trang tệp gốc và chạy lại phần trích xuất.";
    case "review_expired":
      return "Đã hết thời hạn duyệt. Tệp gốc vẫn được giữ; hãy duyệt thông tin hoặc chạy lại xử lý.";
    case "ocr_incomplete":
      return "Một số trang cần OCR chưa được nhận dạng đầy đủ. Nội dung văn bản sẵn có vẫn được giữ; hãy đối chiếu tệp gốc và chạy lại trích xuất.";
    case "embedding_unavailable":
      return "Chưa cấu hình mô hình tìm kiếm ngữ nghĩa; hiện chỉ tìm được bằng từ khóa. Kiểm tra cấu hình mô hình rồi chạy lại chỉ mục nguồn.";
    case "no_source_chunks":
      return "Nội dung trích xuất chưa tạo được đoạn để lập chỉ mục. Kiểm tra nội dung tệp gốc và chạy lại trích xuất.";
    case "source_index_incomplete":
      return `Đã lập chỉ mục ${count(quality?.source_index?.indexed)} / ${count(quality?.source_index?.expected)} đoạn nguồn. Chạy lại chỉ mục nguồn để xử lý phần còn thiếu.`;
    case "wiki_pages_skipped":
      return `${count(quality?.wiki?.failed)} / ${count(quality?.wiki?.expected)} trang Wiki dự kiến chưa được xuất bản. Kiểm tra nội dung và chạy lại phần Wiki.`;
    case "wiki_index_failed":
      return "Một số trang Wiki chưa được lập chỉ mục ngữ nghĩa; tìm kiếm từ khóa vẫn hoạt động. Kiểm tra cấu hình mô hình và chạy lại phần Wiki.";
    default:
      return warning.message;
  }
}
