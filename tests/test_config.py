from pathlib import Path

from poddesc.config import load_config


def test_load_config_reads_yaml_and_resolves_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
program_name: "Sample Podcast"
output_dir: "custom_outputs"
whisper:
  command: "whisperx"
  language: "ja"
  model: "small"
  output_format: "txt"
  extra_args:
    - "--verbose"
openai:
  model: "gpt-test"
  temperature: 0.2
prompts:
  system: "prompts/system.md"
  user: "prompts/user.md"
links:
  - label: "Message Form"
    url: "https://example.com/form"
  - label: "Official Links"
    url: "https://example.com/links"
description:
  topics_heading: "▼Topics"
  topic_min: 2
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.output_dir == tmp_path / "custom_outputs"
    assert config.whisper.command == "whisperx"
    assert config.whisper.language == "ja"
    assert config.whisper.model == "small"
    assert config.whisper.extra_args == ["--verbose"]
    assert config.openai.model == "gpt-test"
    assert config.openai.temperature == 0.2
    assert config.prompts.system == tmp_path / "prompts/system.md"
    assert config.prompts.user == tmp_path / "prompts/user.md"
    assert config.program_name == "Sample Podcast"
    assert config.links[0].label == "Message Form"
    assert config.links[0].url == "https://example.com/form"
    assert config.links[1].label == "Official Links"
    assert config.links[1].url == "https://example.com/links"
    assert config.description.topics_heading == "▼Topics"
    assert config.description.topic_min == 2


def test_load_config_reads_legacy_link_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
links:
  letter_form: "https://example.com/form"
  link_list: "https://example.com/links"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert [link.label for link in config.links] == ["Message Form", "Official Links"]
    assert [link.url for link in config.links] == ["https://example.com/form", "https://example.com/links"]


def test_config_example_loads() -> None:
    config = load_config(Path("config.example.yaml"))

    assert config.program_name == "Sample Podcast"
    assert config.links[0].url == "https://example.com/message"
    assert config.description.topics_heading == "▼今回のトピック"
