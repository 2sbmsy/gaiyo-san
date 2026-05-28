from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from poddesc.errors import StepError


REQUIRED_USER_PROMPT_PLACEHOLDERS = ("{program_name}", "{transcript}")


def load_prompt_text(path: Path) -> str:
    if not path.exists():
        raise StepError("prompts", f"prompt file not found: {path}")
    if not path.is_file():
        raise StepError("prompts", f"prompt path is not a file: {path}")
    return path.read_text(encoding="utf-8")


def validate_user_prompt_template(user_prompt: str) -> None:
    missing = [placeholder for placeholder in REQUIRED_USER_PROMPT_PLACEHOLDERS if placeholder not in user_prompt]
    if missing:
        raise StepError("prompts", f"user prompt is missing required placeholder(s): {', '.join(missing)}")
    try:
        user_prompt.format(program_name="program", transcript="transcript")
    except (IndexError, KeyError, ValueError) as exc:
        raise StepError("prompts", f"user prompt format is invalid: {exc}") from exc


def validate_template_values(links: list[dict[str, str]], user_prompt: str) -> None:
    if not links:
        raise StepError("config", "links must not be empty")
    for index, link in enumerate(links, start=1):
        if not link.get("label", "").strip():
            raise StepError("config", f"links[{index}].label must not be empty")
        if not link.get("url", "").strip():
            raise StepError("config", f"links[{index}].url must not be empty")
    validate_user_prompt_template(user_prompt)


def _read_config_data(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise StepError("config", f"config file not found: {config_path}")
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise StepError("config", f"failed to parse YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StepError("config", "config root must be a mapping")
    return data


def save_config_values(config_path: Path, program_name: str, links: list[dict[str, str]]) -> None:
    data = _read_config_data(config_path)

    data["program_name"] = program_name.strip()
    data["links"] = [
        {"label": link["label"].strip(), "url": link["url"].strip()}
        for link in links
        if link.get("label", "").strip() or link.get("url", "").strip()
    ]

    try:
        config_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise StepError("config", f"failed to save config file: {exc}") from exc


def save_prompt_text(path: Path, content: str) -> None:
    if not path.exists():
        raise StepError("prompts", f"prompt file not found: {path}")
    if not path.is_file():
        raise StepError("prompts", f"prompt path is not a file: {path}")
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise StepError("prompts", f"failed to save prompt file: {exc}") from exc
