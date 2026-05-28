from __future__ import annotations

import os
import re
import shlex
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILES = (
    PROJECT_ROOT / ".env.local",
    PROJECT_ROOT / ".env",
)

_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    if stripped.startswith("export "):
        stripped = stripped[7:].lstrip()

    if "=" not in stripped:
        return None

    key, raw_value = stripped.split("=", 1)
    key = key.strip()
    if not _ENV_KEY_PATTERN.match(key):
        return None

    value = raw_value.strip()
    if value.startswith(("'", '"')):
        try:
            parts = shlex.split(value, posix=True)
        except ValueError:
            parts = []
        value = parts[0] if parts else value.strip("'\"")
    else:
        value = value.split(" #", 1)[0].rstrip()

    return key, value


def load_local_env(env_files: tuple[Path, ...] | list[Path] = DEFAULT_ENV_FILES, *, override: bool = False) -> set[str]:
    loaded: set[str] = set()
    for env_file in env_files:
        if not env_file.is_file():
            continue

        for line in env_file.read_text(encoding="utf-8").splitlines():
            parsed = _parse_env_line(line)
            if parsed is None:
                continue

            key, value = parsed
            if override or key not in os.environ:
                os.environ[key] = value
                loaded.add(key)

    return loaded


def ensure_openai_api_key() -> bool:
    load_local_env()
    return bool(os.environ.get("OPENAI_API_KEY"))
