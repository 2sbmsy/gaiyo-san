from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from poddesc.config import AppConfig
from poddesc.env import ensure_openai_api_key
from poddesc.errors import StepError
from poddesc.renderer import DescriptionDraft, render_description, strip_trailing_extras, topics_line


@dataclass(frozen=True)
class PromptBundle:
    system: str
    user: str


@dataclass(frozen=True)
class GenerationResult:
    description: str
    metadata: dict[str, Any]
    topics_line: str

    @property
    def culture_line(self) -> str:
        return self.topics_line


def _read_prompt(path: Path, step: str) -> str:
    if not path.exists():
        raise StepError(step, f"prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def parse_draft(raw: str) -> DescriptionDraft:
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StepError("openai", f"failed to parse model JSON response: {exc}") from exc

    topics_raw = data.get("topics", [])
    if not isinstance(topics_raw, list):
        raise StepError("openai", "model response field 'topics' must be a list")

    return DescriptionDraft(
        episode_number=str(data.get("episode_number", "")).strip(),
        title=str(data.get("title", "")).strip(),
        topics=[str(topic).strip() for topic in topics_raw],
    )


def build_prompts(transcript: str, config: AppConfig) -> PromptBundle:
    system_prompt = _read_prompt(config.prompts.system, "prompts")
    user_template = _read_prompt(config.prompts.user, "prompts")
    user_prompt = user_template.format(
        program_name=config.program_name,
        transcript=transcript,
    )
    return PromptBundle(system=system_prompt, user=user_prompt)


def _response_to_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "dict"):
        return response.dict()
    return {"raw_response": str(response)}


def generate_description(transcript: str, config: AppConfig) -> GenerationResult:
    if not ensure_openai_api_key():
        raise StepError("openai", "OPENAI_API_KEY is not set")

    prompts = build_prompts(transcript, config)
    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model=config.openai.model,
            temperature=config.openai.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompts.system},
                {"role": "user", "content": prompts.user},
            ],
        )
    except Exception as exc:
        raise StepError("openai", f"OpenAI API request failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise StepError("openai", "OpenAI API returned an empty response")

    draft = parse_draft(content)
    description = strip_trailing_extras(render_description(draft, config))
    rendered_topics_line = topics_line(draft.topics, config.description)
    metadata = {
        "model": config.openai.model,
        "temperature": config.openai.temperature,
        "raw_content": content,
        "draft": asdict(draft),
        "topics_line": rendered_topics_line,
        "response": _response_to_dict(response),
    }

    return GenerationResult(description=description, metadata=metadata, topics_line=rendered_topics_line)
