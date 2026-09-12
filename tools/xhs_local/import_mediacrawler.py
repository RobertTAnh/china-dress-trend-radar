from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.xhs_relevance import xhs_relevance  # noqa: E402
from app.xhs.normalizer import normalize_xhs_item  # noqa: E402
from tools.xhs_local.local_log import get_logger  # noqa: E402

logger = get_logger()
OUTBOX = PROJECT_ROOT / "data" / "xhs_outbox"


def _load_json_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                items.append(obj)
        return items
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("items", "data", "notes", "contents"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
        return [data]
    return []


def collect_source_files(source_dir: Path) -> list[Path]:
    files: list[Path] = []
    if source_dir.is_file():
        return [source_dir]
    if not source_dir.exists():
        return []
    for pattern in ("*.json", "*.jsonl"):
        files.extend(source_dir.rglob(pattern))
    return sorted(files)


def import_sources(
    source_dir: Path,
    keyword: str,
    max_results: int = 30,
    client_run_id: str | None = None,
    international: bool = True,
    media_type: str | None = None,
    max_age_days: int | None = None,
) -> Path:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    files = collect_source_files(source_dir)
    raw_items: list[dict] = []
    for path in files:
        raw_items.extend(_load_json_file(path))

    accepted_items: list[dict] = []
    rejected = 0
    seen: set[str] = set()
    keyword_items = [
        item
        for item in raw_items
        if not item.get("source_keyword") or item.get("source_keyword") == keyword
    ]
    for index, source_raw in enumerate(keyword_items, start=1):
        raw = dict(source_raw)
        if international:
            note_url = str(raw.get("note_url") or "")
            raw["note_url"] = note_url.replace(
                "https://www.xiaohongshu.com/", "https://www.rednote.com/", 1
            )
        normalized, error = normalize_xhs_item(raw, keyword=keyword, search_position=index)
        if normalized is None or error:
            rejected += 1
            logger.info("Import reject position=%s reason=%s", index, error)
            continue
        if media_type and normalized.media_type != media_type:
            rejected += 1
            logger.info(
                "Import reject position=%s reason=Loại bài %s, yêu cầu %s",
                index,
                normalized.media_type,
                media_type,
            )
            continue
        if max_age_days is not None:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max_age_days)
            if normalized.published_at is None or normalized.published_at < cutoff:
                rejected += 1
                logger.info(
                    "Import reject position=%s reason=Bài cũ hơn %s ngày hoặc thiếu ngày đăng",
                    index,
                    max_age_days,
                )
                continue
        if normalized.external_post_id in seen:
            continue
        seen.add(normalized.external_post_id)
        relevance = xhs_relevance(
            normalized.title,
            normalized.description,
            normalized.author_name,
        )
        logger.info(
            "Import item id=%s title=%s likes=%s collects=%s comments=%s url=%s accepted=%s reasons=%s",
            normalized.external_post_id,
            (normalized.title or "")[:80],
            normalized.like_count,
            normalized.collect_count,
            normalized.comment_count,
            normalized.source_url,
            relevance.accepted,
            "; ".join(relevance.reasons),
        )
        if not relevance.accepted:
            rejected += 1
            continue
        accepted_items.append(raw)
        if len(accepted_items) >= max_results:
            break

    run_id = client_run_id or datetime.now(timezone.utc).strftime("xhs-%Y-%m-%d-%H%M%S")
    out_path = OUTBOX / f"{run_id}.json"
    payload = {
        "client_run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": str(source_dir),
        "keywords": [{"keyword": keyword, "items": accepted_items[:max_results]}],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Imported keyword=%s files=%s received=%s accepted=%s rejected=%s out=%s",
        keyword,
        len(files),
        len(keyword_items),
        len(accepted_items),
        rejected,
        out_path,
    )
    return out_path


def merge_keyword_payloads(paths: list[Path], client_run_id: str) -> Path:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    batches = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        batches.extend(data.get("keywords") or [])
    payload = {
        "client_run_id": client_run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": ", ".join(p.name for p in paths),
        "keywords": batches,
    }
    out_path = OUTBOX / f"{client_run_id}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Chuẩn hóa output MediaCrawler thành JSON ingest")
    parser.add_argument("--source", required=True, help="File hoặc thư mục JSON/JSONL MediaCrawler")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--client-run-id", default="")
    args = parser.parse_args()
    path = import_sources(
        Path(args.source),
        args.keyword,
        max_results=min(max(args.max_results, 1), 30),
        client_run_id=args.client_run_id or None,
        international=True,
    )
    print(path)


if __name__ == "__main__":
    main()
