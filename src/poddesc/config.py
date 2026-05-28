from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from poddesc.errors import StepError


@dataclass(frozen=True)
class WhisperConfig:
    command: str = "whisper"
    language: str = "Japanese"
    model: str = "medium"
    output_format: str = "txt"
    extra_args: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OpenAIConfig:
    model: str = "gpt-4.1-mini"
    temperature: float = 0.4


@dataclass(frozen=True)
class PromptConfig:
    system: Path = Path("prompts/description_system.md")
    user: Path = Path("prompts/description_user.md")


@dataclass(frozen=True)
class LinkConfig:
    label: str
    url: str


@dataclass(frozen=True)
class DescriptionConfig:
    platform: str = "Spotify"
    intro_heading: str = "▼番組紹介"
    links_heading: str = "▼リンク"
    topics_heading: str = "▼今回のトピック"
    intro_text: str = (
        "友人同士で日常の出来事、気になった作品、最近考えたことを話すPodcastです。\n"
        "会話の温度感を残しつつ、初めて聴く人にも伝わる概要欄を作成します。"
    )
    topic_separator: str = " / "
    topic_min: int = 5
    topic_max: int = 15
    topic_warn_length: int = 45
    topic_error_length: int = 70
    topic_line_warning_length: int = 220
    exclude_topic_markers: tuple[str, ...] = (
        "お便りテーマ",
        "おたよりテーマ",
        "メールテーマ",
        "募集テーマ",
    )


@dataclass(frozen=True)
class AppConfig:
    program_name: str = "Sample Podcast"
    output_dir: Path = Path("outputs")
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    prompts: PromptConfig = field(default_factory=PromptConfig)
    description: DescriptionConfig = field(default_factory=DescriptionConfig)
    links: tuple[LinkConfig, ...] = (
        LinkConfig(label="Message Form", url="https://example.com/message"),
        LinkConfig(label="Official Links", url="https://example.com/links"),
    )
    base_dir: Path = Path(".")


def _as_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise StepError("config", f"{field_name} must be a mapping")
    return value


def _resolve_path(base_dir: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path


def _as_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return getattr(DescriptionConfig(), field_name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise StepError("config", f"description.{field_name} must be a list of strings")
    return tuple(value)


def _load_links(raw_links: Any) -> tuple[LinkConfig, ...]:
    if raw_links is None:
        return AppConfig.links

    if isinstance(raw_links, list):
        links: list[LinkConfig] = []
        for index, item in enumerate(raw_links, start=1):
            if not isinstance(item, dict):
                raise StepError("config", f"links[{index}] must be a mapping")
            label = str(item.get("label", "")).strip()
            url = str(item.get("url", "")).strip()
            if not label or not url:
                raise StepError("config", f"links[{index}] requires label and url")
            links.append(LinkConfig(label=label, url=url))
        return tuple(links)

    if isinstance(raw_links, dict):
        if "letter_form" in raw_links or "link_list" in raw_links:
            legacy_links = []
            if raw_links.get("letter_form"):
                legacy_links.append(LinkConfig(label="Message Form", url=str(raw_links["letter_form"]).strip()))
            if raw_links.get("link_list"):
                legacy_links.append(LinkConfig(label="Official Links", url=str(raw_links["link_list"]).strip()))
            return tuple(legacy_links) if legacy_links else AppConfig.links
        if "label" in raw_links or "url" in raw_links:
            label = str(raw_links.get("label", "")).strip()
            url = str(raw_links.get("url", "")).strip()
            if not label or not url:
                raise StepError("config", "links requires label and url")
            return (LinkConfig(label=label, url=url),)

    raise StepError("config", "links must be a list of label/url mappings")


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise StepError("config", f"config file not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise StepError("config", f"failed to parse YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise StepError("config", "config root must be a mapping")

    base_dir = path.resolve().parent
    whisper_data = _as_dict(data.get("whisper"), "whisper")
    openai_data = _as_dict(data.get("openai"), "openai")
    prompts_data = _as_dict(data.get("prompts"), "prompts")
    description_data = _as_dict(data.get("description"), "description")

    extra_args = whisper_data.get("extra_args", [])
    if extra_args is None:
        extra_args = []
    if not isinstance(extra_args, list) or not all(isinstance(item, str) for item in extra_args):
        raise StepError("config", "whisper.extra_args must be a list of strings")

    return AppConfig(
        program_name=str(data.get("program_name", AppConfig.program_name)),
        output_dir=_resolve_path(base_dir, data.get("output_dir", AppConfig.output_dir)),
        whisper=WhisperConfig(
            command=str(whisper_data.get("command", WhisperConfig.command)),
            language=str(whisper_data.get("language", WhisperConfig.language)),
            model=str(whisper_data.get("model", WhisperConfig.model)),
            output_format=str(whisper_data.get("output_format", WhisperConfig.output_format)),
            extra_args=extra_args,
        ),
        openai=OpenAIConfig(
            model=str(openai_data.get("model", OpenAIConfig.model)),
            temperature=float(openai_data.get("temperature", OpenAIConfig.temperature)),
        ),
        prompts=PromptConfig(
            system=_resolve_path(base_dir, prompts_data.get("system", PromptConfig.system)),
            user=_resolve_path(base_dir, prompts_data.get("user", PromptConfig.user)),
        ),
        description=DescriptionConfig(
            platform=str(description_data.get("platform", DescriptionConfig.platform)),
            intro_heading=str(description_data.get("intro_heading", DescriptionConfig.intro_heading)),
            links_heading=str(description_data.get("links_heading", DescriptionConfig.links_heading)),
            topics_heading=str(description_data.get("topics_heading", DescriptionConfig.topics_heading)),
            intro_text=str(description_data.get("intro_text", DescriptionConfig.intro_text)),
            topic_separator=str(description_data.get("topic_separator", DescriptionConfig.topic_separator)),
            topic_min=int(description_data.get("topic_min", DescriptionConfig.topic_min)),
            topic_max=int(description_data.get("topic_max", DescriptionConfig.topic_max)),
            topic_warn_length=int(description_data.get("topic_warn_length", DescriptionConfig.topic_warn_length)),
            topic_error_length=int(description_data.get("topic_error_length", DescriptionConfig.topic_error_length)),
            topic_line_warning_length=int(
                description_data.get("topic_line_warning_length", DescriptionConfig.topic_line_warning_length)
            ),
            exclude_topic_markers=_as_string_tuple(
                description_data.get("exclude_topic_markers"), "exclude_topic_markers"
            ),
        ),
        links=_load_links(data.get("links")),
        base_dir=base_dir,
    )
