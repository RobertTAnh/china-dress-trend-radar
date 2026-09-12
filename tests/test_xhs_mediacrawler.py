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
        "ENABLE_GET_COMMENTS = True\nCRAWLER_MAX_NOTES_COUNT = 10\n",
        encoding="utf-8",
    )
    xhs_config = config_dir / "xhs_config.py"
    xhs_config.write_text('SORT_TYPE = "popularity_descending"\n', encoding="utf-8")

    patch_mediacrawler_config(tmp_path, 25)

    assert 'SORT_TYPE = "general"' in xhs_config.read_text(encoding="utf-8")
    base_config = (config_dir / "base_config.py").read_text(encoding="utf-8")
    assert "ENABLE_GET_COMMENTS = False" in base_config
    assert "CRAWLER_MAX_NOTES_COUNT = 25" in base_config
