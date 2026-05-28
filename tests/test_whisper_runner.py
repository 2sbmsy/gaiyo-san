import os
import sys
from pathlib import Path

from poddesc import whisper_runner


def test_resolve_whisper_command_uses_current_python_venv(monkeypatch, tmp_path: Path) -> None:
    bin_dir = tmp_path / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    whisper = bin_dir / "whisper"
    python.write_text("", encoding="utf-8")
    whisper.write_text("", encoding="utf-8")
    os.chmod(whisper, 0o755)
    monkeypatch.setattr(sys, "executable", str(python))

    assert whisper_runner.resolve_whisper_command("whisper") == str(whisper)


def test_resolve_whisper_command_expands_path_command(tmp_path: Path) -> None:
    command = tmp_path / "bin" / "whisper"

    assert whisper_runner.resolve_whisper_command(str(command)) == str(command)
