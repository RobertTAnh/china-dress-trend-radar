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
        text.innerHTML = `Đang chạy từ khóa <strong></strong> · ${data.request_count} request · ${data.result_count} video · ${data.new_video_count} mới`;
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
