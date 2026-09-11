from __future__ import annotations

import logging
from datetime import datetime
from threading import Lock

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import CrawlRun, Keyword, Snapshot, Video, VideoKeyword
from app.services.budget import BudgetGuard
from app.services.progress import progress_store
from app.services.relevance import is_relevant_video, relevance_score
from app.services.seed_defaults import get_setting, get_setting_bool, get_setting_int
from app.tikhub.adapter import TikHubAdapter, TikHubAuthError, TikHubClientError
from app.tikhub.normalizer import NormalizedVideo, merge_statistics, needs_view_enrichment

logger = logging.getLogger(__name__)

_run_lock = Lock()


class CrawlInProgress(Exception):
    pass


def _apply_runtime_settings(db: Session, settings: Settings) -> Settings:
    settings.tikhub_use_fallback_search = get_setting_bool(
        db, "tikhub_use_fallback_search", settings.tikhub_use_fallback_search
    )
    endpoint = get_setting(db, "tikhub_search_endpoint", settings.tikhub_search_endpoint)
    if endpoint:
        settings.tikhub_search_endpoint = endpoint
    settings.search_sort_type = get_setting(db, "search_sort_type", settings.search_sort_type)
    settings.search_publish_time = get_setting(db, "search_publish_time", settings.search_publish_time)
    settings.search_content_type = get_setting(db, "search_content_type", settings.search_content_type)
    try:
        settings.internal_rate_limit_rps = float(
            get_setting(db, "internal_rate_limit_rps", str(settings.internal_rate_limit_rps))
        )
    except ValueError:
        pass
    return settings


def upsert_video(
    db: Session,
    item: NormalizedVideo,
    keyword: Keyword | None,
    captured_at: datetime,
) -> tuple[Video, bool]:
    existing = (
        db.query(Video)
        .filter(Video.external_video_id == item.external_video_id)
        .one_or_none()
    )
    created = False
    if existing is None:
        existing = Video(
            platform="douyin",
            external_video_id=item.external_video_id,
            source_url=item.source_url,
            caption=item.caption,
            author_id=item.author_id,
            author_name=item.author_name,
            published_at=item.published_at,
            cover_url=item.cover_url,
            duration=item.duration,
            hashtags_json=item.hashtags,
            first_seen_at=captured_at,
            last_seen_at=captured_at,
            raw_data_json=item.raw_data,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        if item.source_url and item.source_url != existing.source_url:
            existing.source_url = item.source_url
        existing.caption = item.caption or existing.caption
        existing.author_id = item.author_id or existing.author_id
        existing.author_name = item.author_name or existing.author_name
        existing.cover_url = item.cover_url or existing.cover_url
        existing.duration = item.duration if item.duration is not None else existing.duration
        existing.hashtags_json = item.hashtags or existing.hashtags_json
        existing.published_at = item.published_at or existing.published_at
        existing.last_seen_at = captured_at
        existing.raw_data_json = item.raw_data or existing.raw_data_json

    if keyword is not None:
        link = (
            db.query(VideoKeyword)
            .filter(
                VideoKeyword.video_id == existing.id,
                VideoKeyword.keyword_id == keyword.id,
            )
            .one_or_none()
        )
        if link is None:
            db.add(
                VideoKeyword(
                    video_id=existing.id,
                    keyword_id=keyword.id,
                    first_seen_at=captured_at,
                )
            )

    snapshot = (
        db.query(Snapshot)
        .filter(Snapshot.video_id == existing.id, Snapshot.captured_at == captured_at)
        .one_or_none()
    )
    if snapshot is None:
        db.add(
            Snapshot(
                video_id=existing.id,
                captured_at=captured_at,
                view_count=item.metrics.view_count,
                like_count=item.metrics.like_count,
                comment_count=item.metrics.comment_count,
                share_count=item.metrics.share_count,
                collect_count=item.metrics.collect_count,
            )
        )
    else:
        if item.metrics.view_count is not None:
            snapshot.view_count = item.metrics.view_count
        if item.metrics.like_count is not None:
            snapshot.like_count = item.metrics.like_count
        if item.metrics.comment_count is not None:
            snapshot.comment_count = item.metrics.comment_count
        if item.metrics.share_count is not None:
            snapshot.share_count = item.metrics.share_count
        if item.metrics.collect_count is not None:
            snapshot.collect_count = item.metrics.collect_count
    return existing, created


async def run_crawl(
    db: Session,
    adapter: TikHubAdapter | None = None,
    settings: Settings | None = None,
) -> CrawlRun:
    if not _run_lock.acquire(blocking=False):
        raise CrawlInProgress("Đang có một lần thu thập chạy. Không thể chạy song song.")
    running = db.query(CrawlRun).filter(CrawlRun.status == "running").first()
    if running:
        _run_lock.release()
        raise CrawlInProgress("Đang có một lần thu thập chạy. Không thể chạy song song.")

    settings = _apply_runtime_settings(db, (settings or get_settings()).model_copy())
    owns_adapter = adapter is None
    adapter = adapter or TikHubAdapter(settings=settings, mock_mode=settings.mock_mode)
    run = CrawlRun(started_at=datetime.utcnow(), status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    progress_store.reset_for_run(run.id, settings.mock_mode)
    budget = BudgetGuard(db, run)
    captured_at = run.started_at
    pages = get_setting_int(db, "pages_per_keyword", settings.pages_per_keyword)
    max_detail = get_setting_int(db, "max_detail_videos_per_run", settings.max_detail_videos_per_run)
    # Keep budget for play_count enrichment (2 aweme_ids per stats request).
    stats_reserve = min(max((max_detail + 1) // 2, 1), max(budget.remaining() // 3, 1))
    logger.info(
        "Crawl started run_id=%s mock=%s pages_per_keyword=%s max_requests=%s "
        "publish_time=%s sort_type=%s content_type=%s",
        run.id,
        settings.mock_mode,
        pages,
        budget.max_run,
        settings.search_publish_time,
        settings.search_sort_type,
        settings.search_content_type,
    )

    try:
        keywords = db.query(Keyword).filter(Keyword.active.is_(True)).order_by(Keyword.id).all()
        missing_views: list[NormalizedVideo] = []
        seen_ids: set[str] = set()
        raw_result_count = 0
        filtered_result_count = 0

        for keyword in keywords:
            progress_store.update(current_keyword=keyword.keyword)
            cursor, search_id, backtrace = 0, "", ""
            keyword_raw = 0
            keyword_filtered = 0
            keyword_accepted = 0
            logger.info(
                "Keyword started run_id=%s keyword_id=%s keyword=%s",
                run.id,
                keyword.id,
                keyword.keyword,
            )
            try:
                for page_number in range(1, pages + 1):
                    # Leave room for play_count stats after at least one search request.
                    if budget.remaining() <= stats_reserve and budget.run_requests > 0:
                        break
                    if not budget.can_request():
                        run.status = "budget_stopped"
                        break
                    page = await adapter.search_videos(
                        keyword.keyword,
                        cursor=cursor,
                        search_id=search_id,
                        backtrace=backtrace,
                    )
                    budget.record_search()
                    progress_store.update(request_count=budget.run_requests)
                    logger.info(
                        "Search page run_id=%s keyword=%s page=%s cursor=%s "
                        "raw=%s has_more=%s next_cursor=%s",
                        run.id,
                        keyword.keyword,
                        page_number,
                        cursor,
                        len(page.videos),
                        page.has_more,
                        page.cursor,
                    )
                    for item in page.videos:
                        raw_result_count += 1
                        keyword_raw += 1
                        score = relevance_score(
                            item.caption,
                            item.hashtags,
                            search_keyword=keyword.keyword,
                        )
                        if not is_relevant_video(
                            item.caption,
                            item.hashtags,
                            search_keyword=keyword.keyword,
                        ):
                            filtered_result_count += 1
                            keyword_filtered += 1
                            logger.info(
                                "Video filtered run_id=%s keyword=%s video_id=%s "
                                "relevance=%s caption=%r",
                                run.id,
                                keyword.keyword,
                                item.external_video_id,
                                score,
                                (item.caption or "")[:240],
                            )
                            continue
                        run.result_count += 1
                        keyword_accepted += 1
                        video, created = upsert_video(db, item, keyword, captured_at)
                        logger.info(
                            "Video accepted run_id=%s keyword=%s video_id=%s new=%s "
                            "relevance=%s views=%s likes=%s comments=%s shares=%s "
                            "collects=%s caption=%r url=%s",
                            run.id,
                            keyword.keyword,
                            item.external_video_id,
                            created,
                            score,
                            item.metrics.view_count,
                            item.metrics.like_count,
                            item.metrics.comment_count,
                            item.metrics.share_count,
                            item.metrics.collect_count,
                            (item.caption or "")[:240],
                            item.source_url,
                        )
                        if created:
                            run.new_video_count += 1
                        if (
                            needs_view_enrichment(item.metrics)
                            and item.external_video_id not in seen_ids
                        ):
                            missing_views.append(item)
                        seen_ids.add(item.external_video_id)
                        del video
                    progress_store.update(
                        result_count=run.result_count,
                        raw_result_count=raw_result_count,
                        filtered_result_count=filtered_result_count,
                        new_video_count=run.new_video_count,
                        request_count=budget.run_requests,
                    )
                    db.commit()
                    if not page.has_more:
                        break
                    cursor, search_id, backtrace = page.cursor, page.search_id, page.backtrace
                if run.status == "budget_stopped":
                    break
            except TikHubAuthError as exc:
                logger.error("Auth error while searching keyword id=%s", keyword.id)
                run.status = "error"
                run.error_message = str(exc)
                progress_store.update(last_error=str(exc), status="error")
                break
            except Exception as exc:
                logger.exception("Keyword failed: id=%s", keyword.id)
                progress_store.update(last_error=str(exc))
                run.error_message = str(exc)
            finally:
                logger.info(
                    "Keyword finished run_id=%s keyword=%s raw=%s filtered=%s accepted=%s",
                    run.id,
                    keyword.keyword,
                    keyword_raw,
                    keyword_filtered,
                    keyword_accepted,
                )

        if run.status == "running":
            progress_store.update(current_keyword="(đang cập nhật lượt xem)")
            missing_views.sort(
                key=lambda item: item.metrics.like_count or 0,
                reverse=True,
            )
            detail_candidates = missing_views[:max_detail]
            for index in range(0, len(detail_candidates), 2):
                if not budget.can_request():
                    run.status = "budget_stopped"
                    break
                batch = detail_candidates[index : index + 2]
                progress_store.update(
                    current_keyword=f"(lượt xem {index + 1}-{min(index + 2, len(detail_candidates))}/{len(detail_candidates)})"
                )
                try:
                    payload = await adapter.fetch_statistics(
                        [item.external_video_id for item in batch]
                    )
                except TikHubClientError as exc:
                    logger.warning(
                        "Statistics enrichment skipped for batch size=%s status=%s",
                        len(batch),
                        exc.status_code,
                    )
                    progress_store.update(
                        last_error=f"Bỏ qua lấy view (HTTP {exc.status_code}). Tiếp tục các video khác."
                    )
                    continue
                except Exception as exc:
                    logger.exception("Statistics enrichment failed")
                    progress_store.update(last_error=str(exc))
                    continue
                # Count actual TikHub stats calls: batch attempt + optional single retries.
                budget.record_stats()
                progress_store.update(request_count=budget.run_requests)
                for item in batch:
                    merge_statistics(item, payload)
                    upsert_video(db, item, None, captured_at)
                db.commit()
            if detail_candidates and budget.stopped:
                logger.warning(
                    "Stopped before enriching all views; filled=%s pending=%s",
                    min(len(detail_candidates), budget.run_requests),
                    max(len(missing_views) - len(detail_candidates), 0),
                )

        if run.status == "running":
            run.status = "success"
        run.finished_at = datetime.utcnow()
        run.estimated_cost_usd = budget.estimated_cost_usd
        if budget.warning and run.status == "budget_stopped":
            run.error_message = budget.warning
        db.commit()
        logger.info(
            "Crawl result summary raw=%s filtered=%s accepted=%s new=%s",
            raw_result_count,
            filtered_result_count,
            run.result_count,
            run.new_video_count,
        )
        progress_store.update(
            running=False,
            status=run.status,
            request_count=run.request_count,
            result_count=run.result_count,
            raw_result_count=raw_result_count,
            filtered_result_count=filtered_result_count,
            new_video_count=run.new_video_count,
            warning=budget.warning,
            last_error=run.error_message,
            finished_at=run.finished_at.isoformat(timespec="seconds"),
            current_keyword=None,
        )
        return run
    except Exception as exc:
        logger.exception("Crawl run failed")
        run.status = "error"
        run.error_message = str(exc)
        run.finished_at = datetime.utcnow()
        db.commit()
        progress_store.update(
            running=False,
            status="error",
            last_error=str(exc),
            finished_at=run.finished_at.isoformat(timespec="seconds"),
        )
        raise
    finally:
        if _run_lock.locked():
            _run_lock.release()
        if owns_adapter:
            await adapter.aclose()
