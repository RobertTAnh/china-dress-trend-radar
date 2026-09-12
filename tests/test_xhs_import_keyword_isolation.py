import json
from pathlib import Path

import tools.xhs_local.import_mediacrawler as importer


def test_import_only_reads_requested_keyword_and_rewrites_rednote_url(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "search.jsonl"
    rows = [
        {
            "note_id": "wanted",
            "title": "一字肩连衣裙 小礼服",
            "source_keyword": "一字肩连衣裙穿搭",
            "note_url": "https://www.xiaohongshu.com/explore/wanted",
        },
        {
            "note_id": "other",
            "title": "生日小礼服",
            "source_keyword": "生日小礼服穿搭",
            "note_url": "https://www.xiaohongshu.com/explore/other",
        },
    ]
    source.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    monkeypatch.setattr(importer, "OUTBOX", tmp_path / "outbox")
    monkeypatch.setattr(
        importer,
        "xhs_relevance",
        lambda *_args: type("R", (), {"accepted": True, "reasons": ["test"]})(),
    )

    output = importer.import_sources(
        source, "一字肩连衣裙穿搭", client_run_id="isolation-test"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    items = payload["keywords"][0]["items"]

    assert [item["note_id"] for item in items] == ["wanted"]
    assert items[0]["note_url"].startswith("https://www.rednote.com/")
