# China Dress Trend Radar

Ứng dụng MVP giúp người bán thời trang tại Việt Nam theo dõi video đầm dự tiệc đang tăng tương tác trên Douyin. Hệ thống tìm video theo từ khóa tiếng Trung qua TikHub, lưu metadata công khai theo từng lần thu thập, rồi xếp hạng xu hướng 7 ngày / 30 ngày.

Bộ từ khóa mặc định được tối ưu cho phong cách Tisora (đầm tiệc nhẹ, đầm sinh nhật, corset/cúp ngực, lệch vai, hoa/nơ và voan). Kết quả thảm đỏ, haute couture, váy cưới, Hán phục, sườn xám, thời trang trình diễn và cho thuê lễ phục được loại trước khi lưu; dữ liệu cũ không liên quan cũng không xuất hiện trong danh sách và bảng xu hướng.

Ứng dụng **không tải file video**. Chỉ lưu URL nguồn, thumbnail và metadata công khai.

Mặc định phát triển bằng **MOCK_MODE**. Không gọi TikHub thật trừ khi bạn chủ động xác nhận.

## 1. Yêu cầu hệ thống

- Windows 10/11
- Python 3.11 trở lên (trên máy này dùng `py -3.11` nếu lệnh `python` không có trong PATH)
- Node.js 18+ nếu chạy bản desktop Electron
- Kết nối internet chỉ cần khi gọi API TikHub thật (mock mode thì không cần)
- Khoảng 200 MB trống cho virtual environment và SQLite

## 2. Cài đặt trên Windows

Mở PowerShell tại thư mục dự án:

```powershell
cd "c:\1 code app\tool check video hot douyin"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
```

Nếu PowerShell chặn script, chạy:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. Tạo virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Thoát môi trường ảo: `deactivate`.

## 4. Cấu hình API key

1. Sao chép `.env.example` thành `.env`.
2. Giữ `MOCK_MODE=true` khi phát triển.
3. Khi đã sẵn sàng gọi API thật, đặt:

```text
MOCK_MODE=false
TIKHUB_API_KEY=điền_key_của_bạn
```

Key chỉ được đọc từ biến môi trường / file `.env`. Không ghi key vào mã nguồn, log hoặc git.

Lấy key tại [user.tikhub.io](https://user.tikhub.io). Tài liệu: [Douyin API](https://tikhub.io/douyin-api), [Video Search V2](https://docs.tikhub.io/370212780e0).

**Chưa gọi API thật khi chưa được chủ dự án xác nhận.** Mỗi request search TikHub khoảng 0,01 USD.

## 5. Chạy mock mode

`.env.example` đã bật `MOCK_MODE=true`. Không cần API key.

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Mở http://127.0.0.1:8000

Trên dashboard bấm **Seed dữ liệu mẫu** để có từ 20 video, nhiều snapshot, video thiếu lượt xem và video trùng từ khóa. Sau đó xem Top Trending 7/30 ngày.

Hoặc:

```powershell
python -m app.cli seed
```

## 6. Chạy crawler thủ công

Trên dashboard bấm **Thu thập ngay**.

Hoặc CLI:

```powershell
python -m app.cli crawl
```

Ở mock mode, crawler dùng dữ liệu giả, không tốn tiền TikHub.

Không cho phép hai lần chạy song song.

## 7. Bật lịch tự động

Lịch mặc định: thứ Hai, thứ Tư, thứ Sáu, múi giờ `Asia/Bangkok`.

1. Vào **Cài đặt**.
2. Chọn **Bật lịch T2/T4/T6**.
3. Đặt giờ/phút (mặc định 09:00).
4. Lưu. Ứng dụng phải đang chạy thì lịch mới kích hoạt.

Biến `.env`:

```text
SCHEDULER_ENABLED=true
SCHEDULER_TIMEZONE=Asia/Bangkok
SCHEDULER_HOUR=9
SCHEDULER_MINUTE=0
```

## 8. Sao lưu SQLite

File mặc định: `data/radar.db`.

```powershell
copy data\radar.db data\radar-backup-YYYYMMDD.db
```

Có thể copy cả thư mục `data\`. Đóng app hoặc dừng crawler trước khi sao lưu để tránh file đang ghi.

## 9. Cách xem chi phí

Trang **Tổng quan** và **Cài đặt** hiển thị:

- số request lần chạy
- số request trong tháng
- chi phí ước tính USD và VND
- tỷ giá USD/VND (mặc định 26.000, sửa thủ công)
- trạng thái còn trong ngân sách hay đã dừng

Giới hạn mặc định: 35 request/lần, 400 request/tháng. Search tính 0,01 USD/request; thống kê chi tiết tính 0,001 USD/request. Khi sắp vượt hạn mức, crawler dừng và ghi cảnh báo.

## 10. Khi TikHub đổi cấu trúc API

Adapter không giả định một shape JSON duy nhất. Nó lần lượt tìm video trong `business_data`, `aweme_info`, `aweme_list`, `data[]`, v.v. Bản gốc luôn lưu ở `raw_data_json`.

Nếu TikHub đổi endpoint:

1. Vào **Cài đặt** → Endpoint tìm kiếm.
2. Mặc định: `/api/v1/douyin/search/fetch_video_search_v2`
3. Có thể bật general search V2: `/api/v1/douyin/search/fetch_general_search_v2`

Nếu đổi tên field, bổ sung mapping trong `app/tikhub/normalizer.py` rồi thêm test trong `tests/test_normalizer.py`. Không cần xóa dữ liệu cũ vì raw JSON vẫn còn.

TikHub không có lọc “30 ngày” (chỉ 0 / 1 / 7 / 180). Báo cáo 30 ngày lọc theo ngày đăng đã lưu trong database.

## 13. Sản phẩm Douyin Shop (Apify)

Tính năng **song song** với crawl video TikHub: tìm sản phẩm Douyin Shop qua Actor `zen-studio/douyin-product-search-scraper`, lưu snapshot lượng bán, lọc phong cách Tisora và xếp hạng.

### Biến môi trường

Sao chép từ `.env.example`:

```text
APIFY_TOKEN=
APIFY_ACTOR_ID=zen-studio/douyin-product-search-scraper
APIFY_MONTHLY_BUDGET_USD=4.50
APIFY_ESTIMATED_PRICE_PER_1000_PRODUCTS=7.99
PRODUCT_RESULTS_PER_KEYWORD=20
PRODUCT_MAX_KEYWORDS_PER_RUN=1
PRODUCT_CRAWL_ENABLED=false
PRODUCT_FREE_PREVIEW_MODE=true
PRODUCT_FREE_PREVIEW_RUN_LIMIT=10
PRODUCT_AUTO_SCHEDULE_ENABLED=false
PRODUCT_MOCK_MODE=true
```

- Token tạo tại [console.apify.com](https://console.apify.com/) → Settings → Integrations → API tokens.
- **Không** commit token. Log sẽ redact `APIFY_TOKEN` / `Authorization: Bearer`.
- Trên Railway: `railway variable set` từng biến trên (chỉ khi bạn xác nhận deploy).

### Mock mode (mặc định)

```text
PRODUCT_MOCK_MODE=true
PRODUCT_CRAWL_ENABLED=true
```

```powershell
python -m app.cli product-seed
python -m app.cli product-crawl --keyword-id 1
```

Hoặc UI: **Từ khóa SP** → **Crawl thử**. Xem kết quả tại **Sản phẩm Douyin** / **Lần chạy SP**.

Chi phí ước tính mỗi lần (20 sản phẩm): `20/1000 × 7.99 ≈ 0,16 USD`. Với ngân sách hữu dụng ~4,00 USD (4,50 trừ buffer 0,50) ≈ **~25 lần/tháng**. Free Preview **10 lần** là giới hạn cứng trước. Credit Apify **không cộng dồn** sang tháng sau.

Hộp ngân sách trên UI ghi rõ đây là **ước tính nội bộ**, chưa phải hóa đơn Apify.

### Free Preview và Starter

- Free Preview: 1 từ khóa/lần, max 20 kết quả, `includeDetails=false`, tối đa 10 run.
- Không tự động nâng gói. Khi đủ nhu cầu, bạn tự chuyển Starter trên Apify rồi cập nhật `PRODUCT_FREE_PREVIEW_MODE=false` và ngân sách — app không tự upgrade.

### API nội bộ

- `POST /api/products/crawl` body `{"keyword_id": 1}`
- `GET /api/products`, `/api/products/{id}`, `/api/products/runs`, `/api/products/budget`

Client **không** được truyền Actor ID / `includeDetails` / limit tùy ý.

## 14. Xiaohongshu (MediaCrawler trên máy Windows)

Lane **song song** với Douyin video/product. Playwright **không** chạy trên Railway.

1. Clone MediaCrawler ra ngoài repo (ví dụ `C:\tools\MediaCrawler`), quét QR lần đầu.
2. Đặt biến trên máy local:

```text
MEDIACRAWLER_PATH=C:\tools\MediaCrawler
XHS_RAILWAY_URL=https://web-production-f29ae8.up.railway.app
XHS_INGEST_TOKEN=
```

3. Trên Railway chỉ cần `XHS_INGEST_TOKEN` (cùng giá trị). Không commit token.
4. Quản lý từ khóa: `/xhs/keywords`. Máy local gọi `GET /api/xhs/keywords`.
5. Mỗi tuần (hoặc thử tay): `.\tools\xhs_local\run_xhs.ps1`
6. Kết quả: `/xhs`, `/xhs/runs`. Ảnh chỉ hiện URL công khai; server không tải media.

Chi tiết từng bước, Task Scheduler Chủ nhật 09:00, và cách đăng nhập lại: [tools/xhs_local/README.md](tools/xhs_local/README.md).

`POST /api/xhs/ingest` yêu cầu `Authorization: Bearer <XHS_INGEST_TOKEN>`. Upload lại cùng `client_run_id` không tạo dữ liệu trùng. Tối đa 30 bài/từ khóa.

## Chạy test

```powershell
pytest
```

Toàn bộ HTTP được mock. Test không gọi TikHub, Apify hoặc Xiaohongshu thật.

## Docker

```powershell
docker compose up --build
```

Vẫn ưu tiên chạy trực tiếp trên Windows bằng virtual environment.

## Bảo mật và giới hạn

- Không lưu cookie Douyin, không dùng tài khoản Douyin, không vượt CAPTCHA.
- Không tải hàng loạt video, không phát lại video trên dashboard.
- Rate limiter nội bộ mặc định khoảng 2 request/giây.
- Giao diện escape HTML (Jinja2) để giảm XSS từ caption/API.

## Điểm chưa kiểm chứng với API thật

Phát triển hoàn toàn bằng mock. Khi có API key thật (sau khi bạn xác nhận), cần kiểm tra:

- Shape thực tế của `data` / `business_data` từ Video Search V2
- `play_count` có xuất hiện trong search hay phải gọi `fetch_multi_video_statistics`
- Phân trang `cursor` / `search_id` / `backtrace` đúng như tài liệu hay không
- Giá request thống kê chi tiết (tài liệu search là 0,01 USD; App V3 thường rẻ hơn)

## 11. Chạy ứng dụng desktop (Electron)

Mặc định desktop **mở thẳng bản Railway** (cùng SQLite + lịch crawler trên cloud). Không cần chạy Python local để xem dữ liệu đã thu thập trên server.

Cấu hình: [desktop/config.json](desktop/config.json)

```json
{
  "mode": "railway",
  "railwayUrl": "https://web-production-f29ae8.up.railway.app",
  "localFallback": true
}
```

- `mode: "railway"` → xem DB cloud (khuyến nghị khi Railway đang chạy lịch).
- `mode: "local"` → chạy FastAPI + SQLite trên máy bạn.
- Menu **Nguồn dữ liệu** cho phép chuyển Railway / Local lúc đang mở app.
- Nếu Railway lỗi và `localFallback: true`, app tự chuyển sang Local.

```powershell
cd "c:\1 code app\tool check video hot douyin"
npm install
npm start
```

Hoặc double-click `start-desktop.bat`.

**Lưu ý:** Railway và Local là **hai database khác nhau**. Muốn xem kết quả crawler theo lịch cloud → dùng chế độ Railway. Local chỉ có dữ liệu khi bạn crawl trên máy này.

Đóng gói installer Windows (tùy chọn, vẫn cần `.venv` Python trên máy chạy):

```powershell
npm install --save-dev electron-builder
npm run dist
```

File cài nằm trong thư mục `release\`. Cách này chưa đóng gói Python; máy đích vẫn cần virtual environment.

## 12. Deploy Railway (chạy tự động)

Railway host bản **web FastAPI**, không phải Electron. Lịch crawler T2/T4/T6 09:00 `Asia/Bangkok` chạy trong process web nên service phải **không ngủ**.

### Chuẩn bị

1. Tài khoản [railway.com](https://railway.com)
2. Cài CLI: `npm install -g @railway/cli`
3. Đăng nhập: `railway login`

### Deploy từ máy này

```powershell
cd "c:\1 code app\tool check video hot douyin"
railway init
railway up
railway variable set MOCK_MODE=true
railway variable set SCHEDULER_ENABLED=true
railway variable set SCHEDULER_TIMEZONE=Asia/Bangkok
railway variable set SCHEDULER_HOUR=9
railway variable set SCHEDULER_MINUTE=0
railway variable set DATABASE_URL=sqlite:///./data/radar.db
```

Gắn **Volume** mount path `/app/data` để SQLite không mất khi redeploy.

```powershell
railway volume add --mount /app/data
```

Mở domain:

```powershell
railway domain
railway open
```

### API TikHub thật

Mặc định `MOCK_MODE=true` — lịch vẫn chạy nhưng **không tốn tiền TikHub**.

Khi bạn xác nhận gọi API thật:

```powershell
railway variable set MOCK_MODE=false
railway variable set TIKHUB_API_KEY=key_cua_ban
```

Mỗi lần crawl khoảng 10–35 request × 0,01 USD.

## Lệnh hữu ích

```powershell
uvicorn app.main:app --reload --port 8000
python -m app.cli seed
python -m app.cli crawl
python -m app.cli product-seed
python -m app.cli product-crawl --keyword-id 1
.\tools\xhs_local\run_xhs.ps1
pytest
npm start
railway up
```
