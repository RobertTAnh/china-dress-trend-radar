async function pollProgress() {
  try {
    const response = await fetch("/api/crawl/status");
    if (!response.ok) return;
    const data = await response.json();
    const badge = document.getElementById("crawler-badge");
    const status = document.getElementById("crawler-status");
    const detail = document.getElementById("crawler-detail");
    const text = document.getElementById("progress-text");
    const errorBox = document.getElementById("progress-error");
    const statusLabels = {
      idle: "Sẵn sàng",
      running: "Đang chạy",
      success: "Hoàn tất",
      completed: "Hoàn tất",
      failed: "Có lỗi",
      error: "Có lỗi",
    };
    const statusLabel = statusLabels[data.status] || data.status || "Sẵn sàng";
    if (badge) {
      badge.textContent = statusLabel;
      badge.classList.toggle("is-running", Boolean(data.running));
    }
    if (status) status.textContent = data.running ? "Đang thu thập dữ liệu" : "Hệ thống sẵn sàng";
    if (detail) {
      detail.textContent = data.running
        ? `Từ khóa: ${data.current_keyword || "..."}`
        : "Crawler đang chờ";
    }
    if (text) {
      if (data.running) {
        const phaseNote =
          data.current_keyword && String(data.current_keyword).startsWith("(")
            ? '<div class="tiny mt-1">Giai đoạn cập nhật lượt xem — số video tìm thấy không tăng thêm.</div>'
            : "";
        text.innerHTML = `Đang chạy: <strong></strong> · ${data.request_count} request · ${data.raw_result_count || 0} video thô · ${data.filtered_result_count || 0} bị loại · ${data.result_count} được giữ · ${data.new_video_count} mới${phaseNote}`;
        const strong = text.querySelector("strong");
        if (strong) strong.textContent = data.current_keyword || "...";
      }
    }
    if (errorBox) {
      if (data.last_error) {
        errorBox.classList.remove("d-none");
        errorBox.textContent = `Lỗi gần nhất: ${data.last_error}`;
      }
    }
  } catch (err) {
    // ignore polling errors
  }
}

setInterval(pollProgress, 2000);
