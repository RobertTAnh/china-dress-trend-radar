# Xiaohongshu local (MediaCrawler)

MediaCrawler **chỉ chạy trên máy Windows** của bạn. Railway chỉ nhận metadata qua API. Không tải ảnh/video, không lấy bình luận, không vượt captcha.

## 1. Clone MediaCrawler (ngoài project này)

```powershell
mkdir C:\tools -ErrorAction SilentlyContinue
cd C:\tools
git clone https://github.com/NanmiCoder/MediaCrawler.git
cd MediaCrawler
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Đăng nhập lần đầu: chạy MediaCrawler theo README của họ, **quét QR** Xiaohongshu. Giữ trạng thái trình duyệt đã lưu (`SAVE_LOGIN_STATE`).

## 2. Cấu hình project radar

Trong thư mục China Dress Trend Radar, sao chép `.env.example` thành `.env` (nếu chưa có) và thêm:

```text
MEDIACRAWLER_PATH=C:\tools\MediaCrawler
XHS_RAILWAY_URL=https://web-production-f29ae8.up.railway.app
XHS_INGEST_TOKEN=dat_token_giong_tren_Railway
```

Sao chép `config.example.json` thành `config.json` nếu muốn fallback keyword khi Railway offline. **Không commit** `config.json` nếu có token.

Trên Railway (khi bạn xác nhận deploy):

```text
XHS_INGEST_TOKEN=cung_mot_token
```

## 3. Bật từ khóa trên web

Mở `/xhs/keywords`, bật từ khóa, giới hạn 20 hoặc 30 bài. Máy local lấy danh sách qua `GET /api/xhs/keywords`.

## 4. Chạy thử một từ khóa

```powershell
cd "c:\1 code app\tool check video hot douyin"
.\.venv\Scripts\Activate.ps1
$env:MEDIACRAWLER_PATH="C:\tools\MediaCrawler"
$env:XHS_RAILWAY_URL="https://web-production-f29ae8.up.railway.app"
$env:XHS_INGEST_TOKEN="token_cua_ban"
.\tools\xhs_local\run_xhs.ps1
```

Hoặc tách bước:

```powershell
python tools\xhs_local\run_mediacrawler.py "C:\tools\MediaCrawler" "生日小礼服穿搭" 30
python tools\xhs_local\import_mediacrawler.py --source "C:\tools\MediaCrawler\data" --keyword "生日小礼服穿搭" --max-results 30
python tools\xhs_local\upload_results.py --file data\xhs_outbox\ten-file.json
```

Kiểm tra JSON trong `data/xhs_outbox/` trước khi upload. Upload thành công thì file chuyển sang `data/xhs_processed/`. Nếu upload lỗi, file nguồn **không bị xóa**.

Xem kết quả trên web: `/xhs`, `/xhs/runs`.

## 5. Log

`logs/xhs_local_crawl.log` (xoay vòng, tối đa ~5 MB × 5 file). Ghi thời gian, từ khóa, số bài, ID/tiêu đề/chỉ số/URL, lý do loại, kết quả upload. Không ghi cookie, token hay header Authorization.

## 6. Lịch hàng tuần (Chủ nhật 09:00)

Chạy PowerShell **Run as administrator** nếu Task Scheduler yêu cầu:

```powershell
.\tools\xhs_local\register_weekly_task.ps1
```

Lịch: Chủ nhật 09:00, chạy bù khi máy vừa bật, không chạy hai tiến trình, timeout 2 giờ. Nếu session hết hạn, script dừng và ghi hướng dẫn quét QR lại.

## 7. Khi cookie / QR hết hạn

1. Mở thư mục MediaCrawler.
2. Chạy lại theo README của họ và **quét QR**.
3. Không nhờ script vượt captcha.
4. Chạy lại `run_xhs.ps1`.

## Giới hạn

- Tối đa 30 bài / từ khóa
- Không lấy comment
- Không tải media
- Không chạy Playwright trên Railway
