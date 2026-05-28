from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from poddesc.config import WhisperConfig
from poddesc.debug_log import append_debug_log
from poddesc.errors import StepError


def _is_path_command(command: str) -> bool:
    return os.sep in command or (os.altsep is not None and os.altsep in command)


def resolve_whisper_command(command: str) -> str:
    if _is_path_command(command):
        return str(Path(command).expanduser())

    candidates = [
        Path(sys.executable).resolve().parent / command,
        Path(__file__).resolve().parents[2] / ".venv" / "bin" / command,
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return shutil.which(command) or command


def run_whisper(audio_file: Path, output_dir: Path, config: WhisperConfig, debug_log_path: Path | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        resolve_whisper_command(config.command),
        str(audio_file),
        "--language",
        config.language,
        "--model",
        config.model,
        "--output_dir",
        str(output_dir),
        "--output_format",
        config.output_format,
        *config.extra_args,
    ]
    append_debug_log(debug_log_path, f"whisper.command={' '.join(command)}")

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        append_debug_log(debug_log_path, f"whisper.error=command not found: {config.command}")
        raise StepError("whisper", f"command not found: {config.command}") from exc

    output_tail: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", file=sys.stderr)
        append_debug_log(debug_log_path, f"whisper.output={line.rstrip()}")
        output_tail.append(line.rstrip())
        output_tail = output_tail[-20:]

    return_code = process.wait()
    append_debug_log(debug_log_path, f"whisper.exit_code={return_code}")
    if return_code != 0:
        detail = "\n".join(output_tail).strip()
        message = f"Whisper command failed with exit code {return_code}"
        if detail:
            message = f"{message}:\n{detail}"
        raise StepError("whisper", message)

    transcript_path = output_dir / f"{audio_file.stem}.{config.output_format}"
    if not transcript_path.exists():
        fallback = output_dir / f"{audio_file.stem}.txt"
        if fallback.exists():
            append_debug_log(debug_log_path, f"whisper.transcript_path={fallback}")
            return fallback
        raise StepError("whisper", f"transcript output not found: {transcript_path}")

    append_debug_log(debug_log_path, f"whisper.transcript_path={transcript_path}")
    return transcript_path
