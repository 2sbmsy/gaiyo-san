from pathlib import Path

from poddesc.debug_log import append_debug_log


def test_append_debug_log_creates_and_appends(tmp_path: Path) -> None:
    log_path = tmp_path / "debug.log"

    append_debug_log(log_path, "first")
    append_debug_log(log_path, "second")

    content = log_path.read_text(encoding="utf-8")
    assert "first" in content
    assert "second" in content
    assert len(content.splitlines()) == 2
