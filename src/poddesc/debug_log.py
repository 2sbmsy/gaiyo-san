from __future__ import annotations

from datetime import datetime
from pathlib import Path


def append_debug_log(path: Path | None, message: str) -> None:
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    path.write_text(
        path.read_text(encoding="utf-8") + f"{timestamp} {message}\n" if path.exists() else f"{timestamp} {message}\n",
        encoding="utf-8",
    )
