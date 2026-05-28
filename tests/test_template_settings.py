from pathlib import Path

import pytest
import yaml

from poddesc.errors import StepError
from poddesc.template_settings import (
    load_prompt_text,
    save_config_values,
    save_prompt_text,
    validate_template_values,
    validate_user_prompt_template,
)


def test_save_config_values_updates_program_name_and_links_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
program_name: "Before"
output_dir: "outputs"
prompts:
  system: "prompts/system.md"
  user: "prompts/user.md"
links:
  - label: "Old Form"
    url: "https://example.com/old-form"
  - label: "Old Links"
    url: "https://example.com/old-links"
openai:
  model: "gpt-test"
""",
        encoding="utf-8",
    )

    save_config_values(
        config_path,
        "After",
        [
            {"label": "Message Form", "url": "https://example.com/new-form"},
            {"label": "Official Links", "url": "https://example.com/new-links"},
        ],
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["program_name"] == "After"
    assert saved["links"][0] == {"label": "Message Form", "url": "https://example.com/new-form"}
    assert saved["links"][1] == {"label": "Official Links", "url": "https://example.com/new-links"}
    assert saved["prompts"] == {"system": "prompts/system.md", "user": "prompts/user.md"}
    assert saved["openai"]["model"] == "gpt-test"


def test_validate_user_prompt_template_accepts_required_placeholders() -> None:
    validate_user_prompt_template("番組: {program_name}\n本文: {transcript}")


def test_validate_user_prompt_template_rejects_missing_required_placeholders() -> None:
    with pytest.raises(StepError, match=r"\{program_name\}"):
        validate_user_prompt_template("本文: {transcript}")


def test_validate_user_prompt_template_rejects_invalid_format() -> None:
    with pytest.raises(StepError, match="user prompt format is invalid"):
        validate_user_prompt_template("番組: {program_name}\nJSON: {\n本文: {transcript}")


def test_validate_template_values_rejects_empty_urls() -> None:
    with pytest.raises(StepError, match=r"links\[1\].url"):
        validate_template_values(
            [{"label": "Message Form", "url": ""}],
            "番組: {program_name}\n本文: {transcript}",
        )

    with pytest.raises(StepError, match=r"links\[1\].label"):
        validate_template_values(
            [{"label": " ", "url": "https://example.com/form"}],
            "番組: {program_name}\n本文: {transcript}",
        )


def test_prompt_text_helpers_require_existing_files(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("before", encoding="utf-8")

    assert load_prompt_text(prompt_path) == "before"

    save_prompt_text(prompt_path, "after")

    assert prompt_path.read_text(encoding="utf-8") == "after"

    with pytest.raises(StepError, match="prompt file not found"):
        load_prompt_text(tmp_path / "missing.md")

    with pytest.raises(StepError, match="prompt file not found"):
        save_prompt_text(tmp_path / "missing.md", "content")
