from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


COUNT_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*([万wWkK]?)\s*\+?",
    re.IGNORECASE,
)


@dataclass
class NormalizedXhsPost:
    external_post_id: str
    title: str = ""
    description: str = ""
    author_id: str = ""
    author_name: str = ""
    source_url: str = ""
    cover_url: str = ""
    media_type: str = "note"
    published_at: datetime | None = None
    like_count: int | None = None
    collect_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    search_position: int | None = None
    keyword: str = ""
    raw_json: dict[str, Any] = field(default_factory=dict)


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


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = COUNT_RE.search(text)
    if match:
        number = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit in {"万", "w"}:
            number *= 10000
        elif unit == "k":
            number *= 1000
        return int(number)
    try:
        return int(float(text.rstrip("+")))
    except ValueError:
        return None


def first_url(value: Any) -> str:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        for key in ("url", "url_default", "src", "uri", "cover"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                return candidate
        urls = value.get("url_list") or value.get("urlList") or []
        if isinstance(urls, list) and urls:
            return first_url(urls[0])
    if isinstance(value, list) and value:
        return first_url(value[0])
    return ""


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if text.isdigit():
        return parse_datetime(int(text))
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text.replace("Z", ""), fmt.replace("%z", "").replace("Z", ""))
            return parsed
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def truncate_raw(raw: dict[str, Any], max_chars: int = 8000) -> dict[str, Any]:
    try:
        encoded = json.dumps(raw, ensure_ascii=False)
        if len(encoded) <= max_chars:
            return raw
        return {"_truncated": True, "preview": encoded[:max_chars]}
    except Exception:
        return {"_truncated": True}


def _build_note_url(note_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def normalize_xhs_item(
    item: dict[str, Any],
    *,
    keyword: str = "",
    search_position: int | None = None,
) -> tuple[NormalizedXhsPost | None, str | None]:
    if not isinstance(item, dict):
        return None, "Item không phải object JSON"
    note = item.get("note") if isinstance(item.get("note"), dict) else item
    note_card = note.get("note_card") if isinstance(note.get("note_card"), dict) else note

    post_id = nested_get(
        item,
        "note_id",
        "post_id",
        "id",
        "noteId",
        "aweme_id",
        "note.note_id",
        "note.id",
        "note_card.note_id",
        "note_card.noteId",
    )
    if post_id is None:
        post_id = nested_get(note_card, "note_id", "id", "noteId")
    external_id = str(post_id).strip() if post_id is not None else ""
    if not external_id or external_id.lower() in {"none", "null"}:
        return None, "Thiếu external_post_id (note_id/id/post_id)"

    title = str(
        nested_get(
            item,
            "title",
            "note_title",
            "display_title",
            "note.title",
            "note_card.title",
            "note_card.display_title",
        )
        or ""
    ).strip()
    description = str(
        nested_get(
            item,
            "desc",
            "description",
            "content",
            "note.desc",
            "note_card.desc",
            "note_card.description",
        )
        or ""
    ).strip()

    source_url = str(
        nested_get(
            item,
            "note_url",
            "share_url",
            "source_url",
            "url",
            "link",
            "note.note_url",
            "note.share_url",
        )
        or ""
    ).strip()
    if source_url and not source_url.startswith(("http://", "https://")):
        source_url = ""
    if not source_url:
        source_url = _build_note_url(external_id)
    if not source_url.startswith(("http://", "https://")):
        return None, "Thiếu URL hợp lệ"

    cover = first_url(
        nested_get(
            item,
            "cover_url",
            "cover",
            "image",
            "note.cover",
            "note_card.cover",
            "image_list",
            "images",
            "note_card.image_list",
        )
    )

    like_count = parse_int(
        nested_get(
            item,
            "liked_count",
            "like_count",
            "likes",
            "interact_info.liked_count",
            "note.liked_count",
            "note_card.interact_info.liked_count",
        )
    )
    collect_count = parse_int(
        nested_get(
            item,
            "collected_count",
            "collect_count",
            "favorites",
            "collectedCount",
            "interact_info.collected_count",
            "note.collected_count",
            "note_card.interact_info.collected_count",
        )
    )
    comment_count = parse_int(
        nested_get(
            item,
            "comments_count",
            "comment_count",
            "comments",
            "interact_info.comment_count",
            "note.comments_count",
            "note_card.interact_info.comment_count",
        )
    )
    share_count = parse_int(
        nested_get(
            item,
            "share_count",
            "shared_count",
            "interact_info.share_count",
            "note.share_count",
        )
    )

    published = parse_datetime(
        nested_get(
            item,
            "published_at",
            "publish_time",
            "time",
            "create_time",
            "timestamp",
            "note.time",
            "note.create_time",
            "note_card.time",
        )
    )

    author_id = str(
        nested_get(
            item,
            "author_id",
            "user_id",
            "user.user_id",
            "user.userid",
            "user.uid",
            "note.user.user_id",
            "note_card.user.user_id",
        )
        or ""
    ).strip()
    author_name = str(
        nested_get(
            item,
            "author_name",
            "nickname",
            "user.nickname",
            "user.nick_name",
            "note.user.nickname",
            "note_card.user.nickname",
        )
        or ""
    ).strip()

    media_type = str(
        nested_get(item, "media_type", "type", "note_type", "note.type") or "note"
    ).strip() or "note"
    if str(media_type) in {"1", "normal", "image"}:
        media_type = "note"
    elif str(media_type) in {"2", "video"}:
        media_type = "video"

    position = parse_int(nested_get(item, "search_position", "rank", "position"))
    if position is None:
        position = search_position
    kw = str(nested_get(item, "keyword", "search_keyword") or keyword or "").strip()

    return (
        NormalizedXhsPost(
            external_post_id=external_id,
            title=title,
            description=description,
            author_id=author_id,
            author_name=author_name,
            source_url=source_url,
            cover_url=cover,
            media_type=media_type,
            published_at=published,
            like_count=like_count,
            collect_count=collect_count,
            comment_count=comment_count,
            share_count=share_count,
            search_position=position,
            keyword=kw,
            raw_json=truncate_raw(item),
        ),
        None,
    )
