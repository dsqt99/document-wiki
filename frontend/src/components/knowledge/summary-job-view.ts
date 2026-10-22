type JobView = {
  status: string; total: number; processed: number; updated: number;
  failed: number; index_failed: number; unchanged?: number; skipped?: number;
};

export function summaryJobPresentation(job: JobView) {
  const running = job.status === "queued" || job.status === "running";
  const warning = job.status === "failed" || job.failed > 0 || job.index_failed > 0;
  const metrics = [{ label: "Đã xử lý", value: job.total ? `${job.processed}/${job.total}` : "0 trang" }];
  for (const [label, value] of [
    ["Cập nhật", job.updated], ["Đã khớp", job.unchanged], ["Bỏ qua", job.skipped],
    ["Lỗi", job.failed], ["Lỗi chỉ mục", job.index_failed],
  ] as const) {
    if (value) metrics.push({ label, value: String(value) });
  }
  return {
    running, warning, metrics,
    title: running ? "Tiến trình cập nhật tóm tắt" : "Kết quả cập nhật tóm tắt",
    label: job.status === "queued" ? "Đang chờ" : running ? "Đang xử lý" : warning ? "Cần kiểm tra" : "Hoàn tất",
    description: running
      ? "Theo dõi từng trang Wiki và văn bản nguồn. Đóng cửa sổ này không dừng tác vụ."
      : warning ? "Kiểm tra các trang chưa hoàn tất và lý do xử lý bên dưới."
        : "Tác vụ đã hoàn tất. Xem các trang đã cập nhật và văn bản nguồn bên dưới.",
  };
}

export function summaryJobEmptyMessage({ filtered = false, running = false, warning = false }: {
  filtered?: boolean; running?: boolean; warning?: boolean;
}) {
  return filtered ? "Không có trang khớp bộ lọc." : running ? "Các trang đang được chuẩn bị. Kết quả sẽ tự cập nhật."
    : warning ? "Tác vụ chưa hoàn tất. Kiểm tra lý do ở trên; bạn có thể đóng cửa sổ và chạy lại thao tác cập nhật tóm tắt."
      : "Không có trang cần cập nhật trong lần chạy này.";
}

export function summaryDetailControls({ total = 0, fullTotal = total, offset = 0, query = "", status = "", running = false, error = false }: {
  total?: number; fullTotal?: number; offset?: number; query?: string; status?: string; running?: boolean; error?: boolean;
}) {
  return {
    filters: fullTotal > 5 || !!query || !!status || offset > 0,
    pagination: total > 50 || offset > 0,
    refresh: running || error,
    compact: fullTotal <= 5 && !query && !status && offset === 0,
  };
}
