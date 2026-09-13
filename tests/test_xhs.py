from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_utils import RedactFilter, redact_secrets
from app.models import XhsKeyword, XhsPost
from app.services.xhs_ingest import ingest_xhs_payload
from app.services.xhs_ranking import rank_xhs_post
from app.services.xhs_relevance import xhs_relevance
from app.web import xhs_routes
from app.xhs.normalizer import normalize_xhs_item
from app.xhs.schemas import XhsIngestPayload
from tests.conftest import make_session


def _note(
    note_id: str,
    title: str,
    **extra,
) -> dict:
    payload = {
        "note_id": note_id,
        "title": title,
        "desc": extra.pop("desc", "法式收腰连衣裙生日穿搭推荐"),
        "liked_count": extra.pop("liked_count", 120),
        "collected_count": extra.pop("collected_count", 80),
        "comments_count": extra.pop("comments_count", 5),
        "note_url": extra.pop("note_url", f"https://www.xiaohongshu.com/explore/{note_id}"),
        "nickname": extra.pop("nickname", "穿搭博主"),
        "time": extra.pop("time", 1710000000),
        "cover": extra.pop("cover", "https://example.com/cover.jpg"),
    }
    payload.update(extra)
    return payload


def test_normalize_multiple_aliases():
    a, err_a = normalize_xhs_item(
        {
            "note_id": "n1",
            "note_title": "一字肩连衣裙穿搭",
            "content": "宴会小礼服",
            "likes": "1.2万+",
            "favorites": "已收藏5000+",
            "comments_count": "12",
            "share_url": "https://www.xiaohongshu.com/explore/n1",
            "user": {"user_id": "u1", "nickname": "A"},
            "image_list": [{"url": "https://example.com/a.jpg"}],
            "create_time": "2026-09-01T10:00:00Z",
        }
    )
    assert err_a is None
    assert a is not None
    assert a.external_post_id == "n1"
    assert a.title == "一字肩连衣裙穿搭"
    assert a.like_count == 12000
    assert a.collect_count == 5000
    assert a.author_name == "A"
    assert a.cover_url.startswith("https://")

    b, err_b = normalize_xhs_item(
        {
            "id": 9876543210123456789,
            "display_title": "法式收腰",
            "description": "小礼服",
            "interact_info": {"liked_count": 9, "collected_count": 3, "comment_count": 1},
            "note_card": {"user": {"nickname": "B"}},
        }
    )
    assert err_b is None
    assert b is not None
    assert b.external_post_id == "9876543210123456789"
    assert b.source_url.endswith("9876543210123456789")

    missing, err = normalize_xhs_item({"title": "no id"})
    assert missing is None
    assert "external_post_id" in (err or "")


def test_relevance_filters_and_keeps_bridesmaid():
    ok = xhs_relevance("伴娘裙宴会小礼服显瘦收腰", "生日穿搭推荐")
    assert ok.accepted
    assert ok.score >= 50

    kids = xhs_relevance("女童公主裙儿童童装宝宝周岁")
    assert not kids.accepted
    assert any("童" in term or "宝" in term for term in kids.matched_negative_terms)

    wedding = xhs_relevance("新娘主纱婚纱敬酒")
    assert not wedding.accepted

    celeb = xhs_relevance("明星活动红毯颁奖高定秀场")
    assert not celeb.accepted

    weak = xhs_relevance("今天天气真好", "出去玩")
    assert not weak.accepted


def test_ranking_collect_outranks_like():
    high_collect = rank_xhs_post(
        relevance_score=80,
        like_count=200,
        collect_count=8000,
        comment_count=10,
        published_at=datetime.utcnow() - timedelta(days=2),
    )
    high_like = rank_xhs_post(
        relevance_score=80,
        like_count=8000,
        collect_count=200,
        comment_count=10,
        published_at=datetime.utcnow() - timedelta(days=2),
    )
    assert high_collect.score > high_like.score
    assert high_collect.label == "phù hợp"


def test_ingest_dedupe_limit_and_idempotent():
    db = make_session()
    items = [
        _note("keep-1", "法式收腰连衣裙生日穿搭"),
        _note("keep-1", "法式收腰连衣裙生日穿搭"),
        _note("kids-1", "儿童童装公主连衣裙", desc="女童宝宝"),
        _note("keep-2", "一字肩小礼服宴会穿搭"),
    ]
    extras = [_note(f"extra-{i}", "法式收腰连衣裙生日穿搭") for i in range(28)]
    payload = XhsIngestPayload.model_validate(
        {
            "client_run_id": "xhs-test-001",
            "keywords": [{"keyword": "生日小礼服穿搭", "items": items + extras}],
        }
    )
    first = ingest_xhs_payload(db, payload)
    assert first.ok
    assert first.received_count == 30
    assert first.accepted_count >= 1
    assert first.rejected_count == 0
    assert db.query(XhsPost).filter(XhsPost.external_post_id == "keep-1").count() == 1
    kids_post = db.query(XhsPost).filter(XhsPost.external_post_id == "kids-1").one()
    assert kids_post.snapshots[-1].trend_label == "không phù hợp"

    second = ingest_xhs_payload(db, payload)
    assert second.ok
    assert second.idempotent
    assert second.accepted_count == first.accepted_count
    assert db.query(XhsPost).count() == first.new_post_count


def _test_app(db, monkeypatch, token: str = "secret-ingest-token"):
    settings = Settings(xhs_ingest_token=token, xhs_ingest_max_body_mb=1)
    monkeypatch.setattr("app.web.xhs_routes.get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(xhs_routes.router)

    def override_db():
        yield db

    app.dependency_overrides[xhs_routes.get_db] = override_db
    return TestClient(app)


def test_ingest_rejects_bad_token(monkeypatch):
    db = make_session()
    client = _test_app(db, monkeypatch)
    response = client.post(
        "/api/xhs/ingest",
        json={"client_run_id": "x", "keywords": []},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    missing = client.post("/api/xhs/ingest", json={"client_run_id": "x", "keywords": []})
    assert missing.status_code == 401


def test_remote_crawl_request_claim_and_progress(monkeypatch):
    db = make_session()
    client = _test_app(db, monkeypatch)

    requested = client.post("/xhs/crawl/request", follow_redirects=False)
    assert requested.status_code == 303
    queued = client.get("/api/xhs/crawl/status").json()
    assert queued["status"] == "queued"

    unauthorized = client.post("/api/xhs/crawl/claim")
    assert unauthorized.status_code == 401
    claimed = client.post(
        "/api/xhs/crawl/claim",
        headers={"Authorization": "Bearer secret-ingest-token"},
    ).json()["job"]
    assert claimed["status"] == "running"

    updated = client.post(
        "/api/xhs/crawl/progress",
        headers={"Authorization": "Bearer secret-ingest-token"},
        json={
            "job_id": claimed["job_id"],
            "status": "waiting",
            "keyword": "宴会连衣裙",
            "keyword_index": 1,
            "keyword_total": 8,
            "accepted_count": 6,
        },
    )
    assert updated.status_code == 200
    status = client.get("/api/xhs/crawl/status").json()
    assert status["keyword"] == "宴会连衣裙"
    assert status["accepted_count"] == 6


def test_remote_login_request_is_claimed_as_login_action(monkeypatch):
    db = make_session()
    client = _test_app(db, monkeypatch)
    requested = client.post("/xhs/login/request", follow_redirects=False)
    assert requested.status_code == 303
    queued = client.get("/api/xhs/crawl/status").json()
    assert queued["action"] == "login"
    claimed = client.post(
        "/api/xhs/crawl/claim",
        headers={"Authorization": "Bearer secret-ingest-token"},
    ).json()["job"]
    assert claimed["action"] == "login"


def test_ingest_token_not_logged(caplog, monkeypatch):
    from app.services.xhs_ingest import XhsIngestResult

    db = make_session()
    monkeypatch.setattr(
        "app.web.xhs_routes.ingest_xhs_payload",
        lambda _db, payload: XhsIngestResult(
            ok=True,
            idempotent=False,
            run_id=1,
            client_run_id=payload.client_run_id,
        ),
    )
    client = _test_app(db, monkeypatch)
    logger = logging.getLogger("app.web.xhs_routes")
    logger.addFilter(RedactFilter())
    with caplog.at_level(logging.INFO):
        logger.info("Authorization Bearer secret-ingest-token XHS_INGEST_TOKEN=secret-ingest-token")
        response = client.post(
            "/api/xhs/ingest",
            json={"client_run_id": "xhs-log-1", "keywords": []},
            headers={"Authorization": "Bearer secret-ingest-token"},
        )
    assert response.status_code == 200
    text = " ".join(record.getMessage() for record in caplog.records)
    assert "secret-ingest-token" not in text
    assert "secret-ingest-token" not in redact_secrets(
        "Authorization: Bearer secret-ingest-token XHS_INGEST_TOKEN=secret-ingest-token"
    )


def test_api_keywords_enabled_only():
    db = make_session()
    row = db.query(XhsKeyword).first()
    assert row is not None
    row.enabled = False
    db.commit()
    enabled = [item.keyword for item in db.query(XhsKeyword).filter(XhsKeyword.enabled.is_(True)).all()]
    assert row.keyword not in enabled


def test_seed_creates_xhs_keywords():
    db = make_session()
    words = {row.keyword for row in db.query(XhsKeyword).all()}
    assert "生日小礼服穿搭" in words
    assert "宴会小礼服穿搭" in words
    assert len(words) == 8
    assert {row.max_results for row in db.query(XhsKeyword).all()} == {20}


def test_resolve_mediacrawler_python_prefers_its_own_venv(tmp_path):
    from tools.xhs_local.run_week import resolve_mediacrawler_python

    expected = tmp_path / ".venv" / "Scripts" / "python.exe"
    expected.parent.mkdir(parents=True)
    expected.write_text("", encoding="utf-8")

    assert resolve_mediacrawler_python(tmp_path) == expected


def test_resolve_mediacrawler_python_honors_configured_path(tmp_path):
    from tools.xhs_local.run_week import resolve_mediacrawler_python

    configured = tmp_path / "custom" / "python.exe"
    configured.parent.mkdir(parents=True)
    configured.write_text("", encoding="utf-8")

    assert resolve_mediacrawler_python(tmp_path, str(configured)) == configured
