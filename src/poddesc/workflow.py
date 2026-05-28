from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from poddesc.checker import CheckResult, check_description, has_errors
from poddesc.config import AppConfig, load_config
from poddesc.debug_log import append_debug_log
from poddesc.description_generator import GenerationResult, PromptBundle, build_prompts, generate_description
from poddesc.errors import StepError
from poddesc.renderer import is_topics_line_too_long
from poddesc.transcript_cleaner import clean_transcript
from poddesc.whisper_runner import run_whisper


DescriptionGenerator = Callable[[str, AppConfig], GenerationResult]


@dataclass(frozen=True)
class TranscriptResult:
    output_dir: Path
    debug_log_path: Path
    transcript_path: Path
    transcript_text: str
    whisper_output_path: Path | None = None
    skipped_whisper: bool = False


@dataclass(frozen=True)
class DescriptionWorkflowResult:
    output_dir: Path
    debug_log_path: Path | None
    cleaned_transcript: str
    cleaned_transcript_path: Path
    dry_run: bool
    prompts: PromptBundle | None = None
    description: str | None = None
    description_path: Path | None = None
    metadata: dict | None = None
    metadata_path: Path | None = None
    topics_line: str | None = None
    topics_line_too_long: bool = False

    @property
    def culture_line(self) -> str | None:
        return self.topics_line

    @property
    def culture_line_too_long(self) -> bool:
        return self.topics_line_too_long


@dataclass(frozen=True)
class CheckWorkflowResult:
    debug_log_path: Path
    results: list[CheckResult]
    has_errors: bool


@dataclass(frozen=True)
class AudioWorkflowResult:
    transcript: TranscriptResult
    description: DescriptionWorkflowResult


def episode_output_dir(root: Path, source_file: Path) -> Path:
    return root / source_file.stem


def resolve_description_save_path(
    description_path: Path | str | None,
    source_name: str,
    output_dir: Path | str | None,
) -> Path:
    if description_path is not None:
        return Path(description_path)
    if output_dir is None:
        raise ValueError("output_dir is required when description_path is None")
    return episode_output_dir(Path(output_dir), Path(source_name)) / "description.md"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_uploaded_file(content: bytes, output_dir: Path, filename: str) -> Path:
    path = output_dir / Path(filename).name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def build_dry_run_prompts(transcript: str, config_path: Path, debug_log_path: Path | None = None) -> PromptBundle:
    config = load_config(config_path)
    prompts = build_prompts(transcript, config)
    append_debug_log(debug_log_path, f"dry_run.system_prompt_chars={len(prompts.system)}")
    append_debug_log(debug_log_path, f"dry_run.user_prompt_chars={len(prompts.user)}")
    return prompts


def transcribe_audio(
    audio_file: Path,
    config_path: Path,
    *,
    skip_whisper: bool = False,
    app_config: AppConfig | None = None,
) -> TranscriptResult:
    config = app_config or load_config(config_path)
    output_dir = episode_output_dir(config.output_dir, audio_file)
    debug_log_path = output_dir / "debug.log"
    transcript_path = output_dir / "transcript.txt"

    if skip_whisper:
        if not transcript_path.exists():
            append_debug_log(debug_log_path, f"whisper.skip.error missing_transcript={transcript_path}")
            raise StepError("whisper", f"--skip-whisper requires existing transcript: {transcript_path}")
        append_debug_log(debug_log_path, f"whisper.skipped=true transcript_path={transcript_path}")
        return TranscriptResult(
            output_dir=output_dir,
            debug_log_path=debug_log_path,
            transcript_path=transcript_path,
            transcript_text=transcript_path.read_text(encoding="utf-8"),
            skipped_whisper=True,
        )

    if not audio_file.exists():
        append_debug_log(debug_log_path, f"input.error audio not found: {audio_file}")
        raise StepError("input", f"audio file not found: {audio_file}")
    if not audio_file.is_file():
        append_debug_log(debug_log_path, f"input.error audio path is not file: {audio_file}")
        raise StepError("input", f"audio path is not a file: {audio_file}")

    whisper_output_path = run_whisper(audio_file, output_dir, config.whisper, debug_log_path=debug_log_path)
    transcript_text = whisper_output_path.read_text(encoding="utf-8")
    write_text(transcript_path, transcript_text)
    append_debug_log(debug_log_path, f"transcript.path={transcript_path}")

    return TranscriptResult(
        output_dir=output_dir,
        debug_log_path=debug_log_path,
        transcript_path=transcript_path,
        transcript_text=transcript_text,
        whisper_output_path=whisper_output_path,
    )


def generate_from_text(
    transcript_text: str,
    output_dir: Path,
    config_path: Path,
    *,
    dry_run: bool = False,
    debug_log_path: Path | None = None,
    description_generator: DescriptionGenerator = generate_description,
) -> DescriptionWorkflowResult:
    config = load_config(config_path)
    append_debug_log(debug_log_path, f"step.generate_from_text.start output_dir={output_dir}")
    append_debug_log(debug_log_path, f"config.path={config_path}")
    append_debug_log(debug_log_path, f"transcript.raw_chars={len(transcript_text)}")

    cleaned = clean_transcript(transcript_text)
    if not cleaned:
        append_debug_log(debug_log_path, "transcript.error=empty after cleaning")
        raise StepError("transcript", "transcript is empty after cleaning")
    append_debug_log(debug_log_path, f"transcript.cleaned_chars={len(cleaned)}")

    cleaned_path = output_dir / "transcript_cleaned.txt"
    write_text(cleaned_path, cleaned)
    append_debug_log(debug_log_path, f"transcript.cleaned_path={cleaned_path}")

    if dry_run:
        append_debug_log(debug_log_path, "dry_run=true openai.called=false")
        prompts = build_prompts(cleaned, config)
        append_debug_log(debug_log_path, f"dry_run.system_prompt_chars={len(prompts.system)}")
        append_debug_log(debug_log_path, f"dry_run.user_prompt_chars={len(prompts.user)}")
        return DescriptionWorkflowResult(
            output_dir=output_dir,
            debug_log_path=debug_log_path,
            cleaned_transcript=cleaned,
            cleaned_transcript_path=cleaned_path,
            dry_run=True,
            prompts=prompts,
        )

    append_debug_log(debug_log_path, f"openai.request.start model={config.openai.model}")
    result = description_generator(cleaned, config)
    append_debug_log(debug_log_path, "openai.request.done=true")

    metadata_path = output_dir / "metadata.json"
    write_json(metadata_path, result.metadata)
    append_debug_log(debug_log_path, f"metadata.path={metadata_path}")

    description_path = output_dir / "description.md"
    write_text(description_path, result.description)
    append_debug_log(debug_log_path, f"description.path={description_path}")
    append_debug_log(debug_log_path, f"description.chars={len(result.description)}")
    append_debug_log(debug_log_path, "step.generate_from_text.done")

    return DescriptionWorkflowResult(
        output_dir=output_dir,
        debug_log_path=debug_log_path,
        cleaned_transcript=cleaned,
        cleaned_transcript_path=cleaned_path,
        dry_run=False,
        description=result.description,
        description_path=description_path,
        metadata=result.metadata,
        metadata_path=metadata_path,
        topics_line=result.topics_line,
        topics_line_too_long=is_topics_line_too_long(result.topics_line, config.description),
    )


def generate_from_transcript_file(
    transcript_file: Path,
    config_path: Path,
    *,
    dry_run: bool = False,
    description_generator: DescriptionGenerator = generate_description,
) -> DescriptionWorkflowResult:
    config = load_config(config_path)
    if not transcript_file.exists():
        raise StepError("input", f"transcript file not found: {transcript_file}")
    if not transcript_file.is_file():
        raise StepError("input", f"transcript path is not a file: {transcript_file}")

    output_dir = episode_output_dir(config.output_dir, transcript_file)
    debug_log_path = output_dir / "debug.log"
    raw_transcript = transcript_file.read_text(encoding="utf-8")
    return generate_from_text(
        raw_transcript,
        output_dir,
        config_path,
        dry_run=dry_run,
        debug_log_path=debug_log_path,
        description_generator=description_generator,
    )


def generate_from_audio(
    audio_file: Path,
    config_path: Path,
    *,
    skip_whisper: bool = False,
    dry_run: bool = False,
    description_generator: DescriptionGenerator = generate_description,
) -> AudioWorkflowResult:
    config = load_config(config_path)
    transcript = transcribe_audio(audio_file, config_path, skip_whisper=skip_whisper, app_config=config)
    description = generate_from_text(
        transcript.transcript_text,
        transcript.output_dir,
        config_path,
        dry_run=dry_run,
        debug_log_path=transcript.debug_log_path,
        description_generator=description_generator,
    )
    return AudioWorkflowResult(transcript=transcript, description=description)


def check_description_text(description: str, config_path: Path, debug_log_path: Path) -> CheckWorkflowResult:
    config = load_config(config_path)
    results = check_description(description, config)
    for result in results:
        append_debug_log(debug_log_path, f"check.{result.level.value}={result.message}")
    return CheckWorkflowResult(debug_log_path=debug_log_path, results=results, has_errors=has_errors(results))


def check_description_file(description_file: Path, config_path: Path) -> CheckWorkflowResult:
    if not description_file.exists():
        raise StepError("input", f"description file not found: {description_file}")
    if not description_file.is_file():
        raise StepError("input", f"description path is not a file: {description_file}")

    debug_log_path = description_file.parent / "debug.log"
    description = description_file.read_text(encoding="utf-8")
    return check_description_text(description, config_path, debug_log_path)
