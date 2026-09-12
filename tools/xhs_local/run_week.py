from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.xhs_local.import_mediacrawler import import_sources, merge_keyword_payloads  # noqa: E402
from tools.xhs_local.local_log import get_logger  # noqa: E402
from tools.xhs_local.run_mediacrawler import run_search  # noqa: E402
from tools.xhs_local.upload_results import upload_file  # noqa: E402

logger = get_logger()
LOCK_FILE = PROJECT_ROOT / "data" / "xhs_outbox" / ".xhs_local.lock"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config() -> dict:
    data = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data["mediacrawler_path"] = os.getenv("MEDIACRAWLER_PATH", data.get("mediacrawler_path", r"C:\tools\MediaCrawler"))
    data["mediacrawler_python"] = os.getenv(
        "MEDIACRAWLER_PYTHON", data.get("mediacrawler_python", "")
    )
    data["railway_url"] = os.getenv("XHS_RAILWAY_URL", data.get("railway_url", ""))
    data["ingest_token"] = os.getenv("XHS_INGEST_TOKEN", data.get("ingest_token", ""))
    international_raw = os.getenv(
        "XHS_INTERNATIONAL", str(data.get("xhs_international", True))
    )
    data["xhs_international"] = international_raw.strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    data["keyword_delay_min_seconds"] = int(
        os.getenv(
            "XHS_KEYWORD_DELAY_MIN_SECONDS",
            data.get("keyword_delay_min_seconds", 420),
        )
    )
    data["keyword_delay_max_seconds"] = int(
        os.getenv(
            "XHS_KEYWORD_DELAY_MAX_SECONDS",
            data.get("keyword_delay_max_seconds", 540),
        )
    )
    return data


def keyword_delay_seconds(config: dict) -> int:
    minimum = max(0, int(config.get("keyword_delay_min_seconds", 420)))
    maximum = max(minimum, int(config.get("keyword_delay_max_seconds", 540)))
    return random.randint(minimum, maximum)


def report_remote_progress(config: dict, **fields) -> None:
    job_id = (os.getenv("XHS_REMOTE_JOB_ID") or "").strip()
    if not job_id:
        return
    railway_url = (config.get("railway_url") or "").rstrip("/")
    token = (config.get("ingest_token") or "").strip()
    if not railway_url or not token:
        return
    payload = {"job_id": job_id, **fields}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                railway_url + "/api/xhs/crawl/progress",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Không gửi được tiến độ RedNote: %s", exc)


def resolve_mediacrawler_python(mc_root: Path, configured: str = "") -> Path:
    candidates = []
    if configured.strip():
        candidates.append(Path(configured.strip()))
    candidates.extend(
        [
            mc_root / ".venv" / "Scripts" / "python.exe",
            mc_root / "venv" / "Scripts" / "python.exe",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "Không thấy Python riêng của MediaCrawler. Hãy tạo bằng: "
        f'python -m venv "{mc_root / ".venv"}" rồi cài requirements.txt.'
    )


def acquire_lock() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        raise SystemExit("Đang có một tiến trình Xiaohongshu chạy. Không chạy song song.")
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")


def release_lock() -> None:
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def fetch_keywords(railway_url: str, fallback: list[dict]) -> list[dict]:
    if not railway_url:
        logger.warning("Không có XHS_RAILWAY_URL — dùng fallback_keywords.")
        return fallback
    url = railway_url.rstrip("/") + "/api/xhs/keywords"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
        response.raise_for_status()
        items = response.json().get("items") or []
        logger.info("Lấy %s từ khóa đang bật từ Railway", len(items))
        return items
    except Exception as exc:
        logger.warning("Không lấy được keyword từ Railway (%s). Dùng fallback.", exc)
        return fallback


def default_data_dir(root: Path) -> Path:
    for candidate in (root / "data" / "xhs", root / "data", root / "output"):
        if candidate.exists():
            return candidate
    return root / "data"


def main() -> None:
    started = datetime.now(timezone.utc)
    acquire_lock()
    try:
        config = load_config()
        mc_root = Path(config["mediacrawler_path"])
        railway_url = (config.get("railway_url") or "").strip()
        token = (config.get("ingest_token") or "").strip()
        mc_python = resolve_mediacrawler_python(
            mc_root, str(config.get("mediacrawler_python") or "")
        )
        logger.info("Bắt đầu crawl Xiaohongshu local started=%s", started.isoformat())
        if not mc_root.exists():
            raise SystemExit(f"Không thấy MediaCrawler tại {mc_root}. Clone repo ra ngoài project.")
        if not (mc_root / "main.py").exists():
            raise SystemExit(f"{mc_root} thiếu main.py — kiểm tra clone MediaCrawler.")
        logger.info("MediaCrawler Python: %s", mc_python)

        keywords = fetch_keywords(railway_url, config.get("fallback_keywords") or [])
        if not keywords:
            raise SystemExit("Không có từ khóa Xiaohongshu đang bật.")
        logger.info("Từ khóa: %s", ", ".join(item.get("keyword", "") for item in keywords))
        report_remote_progress(
            config,
            status="running",
            stage="starting",
            message=f"Đã nhận {len(keywords)} từ khóa, chuẩn bị tìm kiếm",
            keyword_total=len(keywords),
            accepted_count=0,
        )

        client_run_id = started.strftime("xhs-%Y-%m-%d-%H%M%S")
        parts: list[Path] = []
        total_accepted = 0
        for keyword_index, item in enumerate(keywords):
            keyword = item.get("keyword")
            if not keyword:
                continue
            max_results = min(int(item.get("max_results") or 30), 30)
            report_remote_progress(
                config,
                status="running",
                stage="searching",
                message=f"Đang tìm từ khóa {keyword_index + 1}/{len(keywords)}",
                keyword=keyword,
                keyword_index=keyword_index + 1,
                keyword_total=len(keywords),
                accepted_count=total_accepted,
                next_keyword_at=None,
            )
            try:
                run_search(
                    mc_root,
                    keyword,
                    max_results,
                    str(mc_python),
                    international=bool(config.get("xhs_international", True)),
                )
            except SystemExit:
                raise
            except Exception as exc:
                logger.error("MediaCrawler lỗi keyword=%s: %s", keyword, exc)
                raise
            source = default_data_dir(mc_root)
            part = import_sources(
                source,
                keyword,
                max_results=max_results,
                client_run_id=f"{client_run_id}-{keyword}",
                international=bool(config.get("xhs_international", True)),
                max_age_days=7,
            )
            parts.append(part)
            part_data = json.loads(part.read_text(encoding="utf-8"))
            part_count = sum(len(batch.get("items") or []) for batch in part_data.get("keywords") or [])
            total_accepted += part_count
            report_remote_progress(
                config,
                status="running",
                stage="keyword_done",
                message=f"Xong từ khóa {keyword_index + 1}/{len(keywords)} · giữ {part_count} bài",
                keyword=keyword,
                keyword_index=keyword_index + 1,
                keyword_total=len(keywords),
                accepted_count=total_accepted,
            )
            if keyword_index < len(keywords) - 1:
                delay = keyword_delay_seconds(config)
                logger.info(
                    "Nghỉ %s giây (%.1f phút) trước từ khóa tiếp theo để giảm tải RedNote.",
                    delay,
                    delay / 60,
                )
                next_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                report_remote_progress(
                    config,
                    status="waiting",
                    stage="waiting",
                    message=f"Đang nghỉ {delay / 60:.1f} phút trước từ khóa tiếp theo",
                    next_keyword_at=next_at.isoformat(),
                    accepted_count=total_accepted,
                )
                time.sleep(delay)

        payload_path = merge_keyword_payloads(parts, client_run_id)
        if not railway_url or not token:
            logger.error("Thiếu XHS_RAILWAY_URL hoặc XHS_INGEST_TOKEN — giữ file %s, không upload.", payload_path)
            raise SystemExit(3)
        upload_file(payload_path, railway_url, token)
        finished = datetime.now(timezone.utc)
        report_remote_progress(
            config,
            status="completed",
            stage="completed",
            message=f"Hoàn tất {len(keywords)} từ khóa · giữ {total_accepted} bài",
            keyword=None,
            keyword_index=len(keywords),
            keyword_total=len(keywords),
            accepted_count=total_accepted,
            next_keyword_at=None,
            finished_at=finished.isoformat(),
        )
        logger.info("Hoàn tất started=%s finished=%s", started.isoformat(), finished.isoformat())
    finally:
        release_lock()


if __name__ == "__main__":
    main()
