from pathlib import Path

from tools.xhs_local.run_mediacrawler import (
    detect_permission_issue,
    detect_session_issue,
    patch_mediacrawler_config,
)


def test_permission_error_is_detected_separately_from_successful_login() -> None:
    output = "Login successful\n您当前登录的账号没有权限访问"
    assert detect_permission_issue(output) is True
    assert detect_session_issue(output) is False


def test_patch_uses_general_xhs_sort(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "base_config.py").write_text(
        "ENABLE_GET_COMMENTS = True\nCRAWLER_MAX_NOTES_COUNT = 10\nXHS_INTERNATIONAL = False\n",
        encoding="utf-8",
    )
    xhs_config = config_dir / "xhs_config.py"
    xhs_config.write_text('SORT_TYPE = "popularity_descending"\n', encoding="utf-8")

    patch_mediacrawler_config(tmp_path, 25)

    assert 'SORT_TYPE = "popularity_descending"' in xhs_config.read_text(encoding="utf-8")
    base_config = (config_dir / "base_config.py").read_text(encoding="utf-8")
    assert "ENABLE_GET_COMMENTS = False" in base_config
    assert "CRAWLER_MAX_NOTES_COUNT = 25" in base_config
    assert "XHS_INTERNATIONAL = True" in base_config


def test_patch_adds_server_side_all_content_filter(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "base_config.py").write_text("XHS_INTERNATIONAL = False\n", encoding="utf-8")
    xhs_dir = tmp_path / "media_platform" / "xhs"
    xhs_dir.mkdir(parents=True)
    core = xhs_dir / "core.py"
    core.write_text(
        'from .field import SearchSortType\n'
        '                        sort=(SearchSortType(config.SORT_TYPE) if config.SORT_TYPE != "" else SearchSortType.GENERAL),\n',
        encoding="utf-8",
    )

    patch_mediacrawler_config(tmp_path, 20)
    patched = core.read_text(encoding="utf-8")

    assert "SearchSortType, SearchNoteType" in patched
    assert "note_type=SearchNoteType.ALL" in patched
