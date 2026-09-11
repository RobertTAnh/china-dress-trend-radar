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
    if (badge) badge.textContent = data.status || "idle";
    if (status) status.textContent = data.status || "idle";
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
        text.innerHTML = `Đang chạy: <strong></strong> · ${data.request_count} request · ${data.result_count} video tìm thấy · ${data.new_video_count} mới${phaseNote}`;
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
