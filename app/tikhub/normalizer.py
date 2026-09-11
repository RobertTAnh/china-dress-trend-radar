from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


HASHTAG_RE = re.compile(r"#([^\s#]+)")


@dataclass
class NormalizedMetrics:
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    collect_count: int | None = None


@dataclass
class NormalizedVideo:
    external_video_id: str
    source_url: str = ""
    caption: str = ""
    author_id: str = ""
    author_name: str = ""
    published_at: datetime | None = None
    cover_url: str = ""
    duration: int | None = None
    hashtags: list[str] = field(default_factory=list)
    metrics: NormalizedMetrics = field(default_factory=NormalizedMetrics)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchPage:
    videos: list[NormalizedVideo]
    cursor: int = 0
    search_id: str = ""
    backtrace: str = ""
    has_more: bool = False
    raw_response: dict[str, Any] = field(default_factory=dict)


def nested_get(obj: Any, *paths: str, default: Any = None) -> Any:
    for path in paths:
        current = obj
        found = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return default


def first_url(value: Any) -> str:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        urls = value.get("url_list") or value.get("urlList") or []
        if isinstance(urls, list) and urls:
            return str(urls[0])
        for key in ("url", "uri", "cover"):
            if isinstance(value.get(key), str) and value[key].startswith(("http://", "https://")):
                return value[key]
    if isinstance(value, list) and value:
        return first_url(value[0])
    return ""


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, str) and value.isdigit():
        return parse_datetime(int(value))
    return None


def parse_duration_seconds(value: Any) -> int | None:
    ms_or_s = parse_int(value)
    if ms_or_s is None:
        return None
    if ms_or_s >= 1000:
        return int(ms_or_s / 1000)
    return ms_or_s


def extract_hashtags(aweme: dict[str, Any], caption: str) -> list[str]:
    tags: list[str] = []
    cha_list = nested_get(aweme, "cha_list", "text_extra") or []
    if isinstance(cha_list, list):
        for item in cha_list:
            if not isinstance(item, dict):
                continue
            name = item.get("cha_name") or item.get("hashtag_name") or item.get("name")
            if name:
                tags.append(str(name).lstrip("#"))
            if item.get("hashtag_name"):
                tags.append(str(item["hashtag_name"]).lstrip("#"))
    tags.extend(HASHTAG_RE.findall(caption or ""))
    seen: set[str] = set()
    unique: list[str] = []
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            unique.append(tag)
    return unique


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def extract_aweme_candidates(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    root = payload
    if isinstance(payload, dict) and "data" in payload:
        root = payload["data"]

    buckets: list[Any] = []
    if isinstance(root, list):
        buckets.append(root)
    elif isinstance(root, dict):
        for key in (
            "business_data",
            "data",
            "aweme_list",
            "search_item_list",
            "item_list",
            "items",
        ):
            if key in root and isinstance(root[key], list):
                buckets.append(root[key])
        inner = root.get("data")
        if isinstance(inner, dict):
            for key in ("business_data", "aweme_list", "data"):
                if isinstance(inner.get(key), list):
                    buckets.append(inner[key])

    for bucket in buckets:
        for entry in bucket:
            aweme = _pick_aweme(entry)
            if aweme:
                items.append(aweme)
    return items


def _pick_aweme(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    if entry.get("aweme_id") or entry.get("awemeId"):
        return entry
    for key in ("aweme_info", "aweme", "aweme_info.aweme", "data"):
        node: Any = entry
        found = True
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                found = False
                break
        if found and isinstance(node, dict):
            nested = _pick_aweme(node)
            if nested:
                return nested
    data = entry.get("data")
    if isinstance(data, dict):
        return _pick_aweme(data)
    return None


def normalize_metrics(aweme: dict[str, Any]) -> NormalizedMetrics:
    stats = _as_dict(aweme.get("statistics") or aweme.get("stats") or aweme.get("statistic"))
    source = {**stats, **aweme}
    view = None
    for key in ("play_count", "playCount", "view_count", "viewCount", "watch_count"):
        if key in source and source[key] is not None and source[key] != "":
            view = parse_int(source[key])
            break
    return NormalizedMetrics(
        view_count=view,
        like_count=parse_int(
            nested_get(source, "digg_count", "like_count", "diggCount", "likeCount")
        ),
        comment_count=parse_int(
            nested_get(source, "comment_count", "commentCount")
        ),
        share_count=parse_int(nested_get(source, "share_count", "shareCount")),
        collect_count=parse_int(
            nested_get(source, "collect_count", "collectCount", "favorite_count")
        ),
    )


def normalize_video(aweme: dict[str, Any]) -> NormalizedVideo | None:
    video_id = nested_get(aweme, "aweme_id", "awemeId", "group_id", "id_str", "id")
    if video_id is None:
        return None
    video_id = str(video_id)
    author = _as_dict(aweme.get("author") or aweme.get("author_info"))
    video = _as_dict(aweme.get("video") or aweme.get("video_info"))
    caption = str(nested_get(aweme, "desc", "description", "caption", "title") or "")
    source_url = str(
        nested_get(aweme, "share_url", "share_info.share_url", "shareUrl")
        or f"https://www.douyin.com/video/{video_id}"
    )
    cover = (
        first_url(nested_get(video, "cover", "origin_cover", "dynamic_cover", "ai_dynamic_cover"))
        or first_url(nested_get(aweme, "cover", "video.cover"))
    )
    return NormalizedVideo(
        external_video_id=video_id,
        source_url=source_url,
        caption=caption,
        author_id=str(nested_get(author, "uid", "id", "sec_uid", "unique_id") or ""),
        author_name=str(nested_get(author, "nickname", "nick_name", "name") or ""),
        published_at=parse_datetime(
            nested_get(aweme, "create_time", "createTime", "create_time_ms", "published_at")
        ),
        cover_url=cover,
        duration=parse_duration_seconds(nested_get(video, "duration") or nested_get(aweme, "duration")),
        hashtags=extract_hashtags(aweme, caption),
        metrics=normalize_metrics(aweme),
        raw_data=aweme,
    )


def extract_pagination(payload: Any) -> tuple[int, str, str, bool]:
    root = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(root, dict):
        root = payload if isinstance(payload, dict) else {}
    extra = root.get("extra") if isinstance(root.get("extra"), dict) else {}
    cursor = parse_int(
        nested_get(root, "cursor", "offset")
        or nested_get(extra, "cursor")
        or nested_get(payload if isinstance(payload, dict) else {}, "cursor")
    ) or 0
    search_id = str(
        nested_get(root, "search_id", "log_pb.impr_id", "impr_id")
        or nested_get(extra, "search_id")
        or ""
    )
    backtrace = str(nested_get(root, "backtrace", "extra.backtrace") or "")
    has_more_raw = nested_get(root, "has_more", "hasMore")
    if has_more_raw in (None, ""):
        has_more_raw = nested_get(extra, "has_more")
    has_more = bool(has_more_raw) and has_more_raw not in (0, "0", False, "false")
    return cursor, search_id, backtrace, has_more


def normalize_search_response(payload: Any) -> SearchPage:
    raw = payload if isinstance(payload, dict) else {"data": payload}
    videos: list[NormalizedVideo] = []
    seen: set[str] = set()
    for aweme in extract_aweme_candidates(raw):
        video = normalize_video(aweme)
        if video and video.external_video_id not in seen:
            seen.add(video.external_video_id)
            videos.append(video)
    cursor, search_id, backtrace, has_more = extract_pagination(raw)
    return SearchPage(
        videos=videos,
        cursor=cursor,
        search_id=search_id,
        backtrace=backtrace,
        has_more=has_more,
        raw_response=raw,
    )


def merge_statistics(video: NormalizedVideo, stats_payload: Any) -> NormalizedVideo:
    data = stats_payload.get("data") if isinstance(stats_payload, dict) else stats_payload
    candidates: list[dict[str, Any]] = []
    if isinstance(data, list):
        candidates.extend(item for item in data if isinstance(item, dict))
    elif isinstance(data, dict):
        if "statistics_list" in data and isinstance(data["statistics_list"], list):
            candidates.extend(item for item in data["statistics_list"] if isinstance(item, dict))
        else:
            candidates.append(data)
            for value in data.values():
                if isinstance(value, dict):
                    candidates.append(value)
                if isinstance(value, list):
                    candidates.extend(item for item in value if isinstance(item, dict))
    for item in candidates:
        item_id = str(nested_get(item, "aweme_id", "awemeId", "id") or "")
        if item_id and item_id != video.external_video_id:
            continue
        metrics = normalize_metrics(item)
        if metrics.view_count is not None:
            video.metrics.view_count = metrics.view_count
        if metrics.like_count is not None:
            video.metrics.like_count = metrics.like_count
        if metrics.comment_count is not None:
            video.metrics.comment_count = metrics.comment_count
        if metrics.share_count is not None:
            video.metrics.share_count = metrics.share_count
        if metrics.collect_count is not None:
            video.metrics.collect_count = metrics.collect_count
        if item_id == video.external_video_id:
            break
    return video
