from pathlib import Path

import pytest

from poddesc.description_generator import GenerationResult
from poddesc.errors import StepError
from poddesc.workflow import (
    check_description_file,
    generate_from_audio,
    generate_from_text,
    resolve_description_save_path,
    save_uploaded_file,
    transcribe_audio,
)


def _write_config(tmp_path: Path) -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/system.md").write_text("system prompt", encoding="utf-8")
    (tmp_path / "prompts/user.md").write_text(
        "番組: {program_name}\n本文: {transcript}",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
program_name: "Sample Podcast"
output_dir: "{tmp_path / "outputs"}"
prompts:
  system: "prompts/system.md"
  user: "prompts/user.md"
links:
  - label: "Message Form"
    url: "https://example.com/form"
  - label: "Official Links"
    url: "https://example.com/links"
""",
        encoding="utf-8",
    )
    return config_path


def test_generate_from_text_dry_run_returns_prompts_without_openai(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    def fail_if_called(transcript, config):  # pragma: no cover - assertion guard
        raise AssertionError("OpenAI generator should not be called during dry-run")

    result = generate_from_text(
        "[00:00 --> 00:01] 映画の話",
        tmp_path / "outputs/episode",
        config_path,
        dry_run=True,
        description_generator=fail_if_called,
    )

    assert result.dry_run is True
    assert result.cleaned_transcript == "映画の話"
    assert result.prompts is not None
    assert "本文: 映画の話" in result.prompts.user
    assert result.description_path is None
    assert (tmp_path / "outputs/episode/transcript_cleaned.txt").read_text(encoding="utf-8") == "映画の話"


def test_generate_from_text_saves_description_and_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    debug_log_path = tmp_path / "outputs/episode/debug.log"

    def fake_generator(transcript, config):
        return GenerationResult(
            description="第1回【映画】\n\n▼今回のトピック\n映画 / 漫画 / ラジオ / 仕事 / 音楽\n",
            metadata={"draft": {"title": "映画"}},
            topics_line="映画 / 漫画 / ラジオ / 仕事 / 音楽",
        )

    result = generate_from_text(
        "映画の話",
        tmp_path / "outputs/episode",
        config_path,
        debug_log_path=debug_log_path,
        description_generator=fake_generator,
    )

    assert result.description_path == tmp_path / "outputs/episode/description.md"
    assert result.metadata_path == tmp_path / "outputs/episode/metadata.json"
    assert result.description is not None
    assert "▼今回のトピック" in result.description
    assert '"title": "映画"' in result.metadata_path.read_text(encoding="utf-8")
    assert "openai.request.done=true" in debug_log_path.read_text(encoding="utf-8")


def test_generate_from_text_rejects_empty_cleaned_transcript(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    with pytest.raises(StepError, match="transcript is empty after cleaning"):
        generate_from_text("", tmp_path / "outputs/episode", config_path)


def test_transcribe_audio_skip_whisper_reads_existing_transcript(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    transcript_path = tmp_path / "outputs/audio/transcript.txt"
    transcript_path.parent.mkdir(parents=True)
    transcript_path.write_text("既存の文字起こし", encoding="utf-8")

    result = transcribe_audio(tmp_path / "audio.mp3", config_path, skip_whisper=True)

    assert result.skipped_whisper is True
    assert result.transcript_text == "既存の文字起こし"
    assert result.transcript_path == transcript_path


def test_generate_from_audio_transcribes_then_generates_description(monkeypatch, tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"audio")

    def fake_run_whisper(audio_path, output_dir, config, debug_log_path=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / f"{audio_path.stem}.txt"
        transcript_path.write_text("映画の話", encoding="utf-8")
        return transcript_path

    def fake_generator(transcript, config):
        return GenerationResult(
            description="第1回【映画】\n\n▼今回のトピック\n映画 / ラジオ\n",
            metadata={"draft": {"title": "映画"}},
            topics_line="映画 / ラジオ",
        )

    monkeypatch.setattr("poddesc.workflow.run_whisper", fake_run_whisper)

    result = generate_from_audio(audio_file, config_path, description_generator=fake_generator)

    assert result.transcript.transcript_text == "映画の話"
    assert result.transcript.transcript_path == tmp_path / "outputs/audio/transcript.txt"
    assert result.description.description_path == tmp_path / "outputs/audio/description.md"
    assert result.description.description == "第1回【映画】\n\n▼今回のトピック\n映画 / ラジオ\n"


def test_save_uploaded_file_uses_basename(tmp_path: Path) -> None:
    saved = save_uploaded_file(b"audio", tmp_path / "outputs", "../episode.mp3")

    assert saved == tmp_path / "outputs/episode.mp3"
    assert saved.read_bytes() == b"audio"


def test_resolve_description_save_path_uses_existing_path(tmp_path: Path) -> None:
    description_path = tmp_path / "custom" / "description.md"

    result = resolve_description_save_path(description_path, "episode.txt", None)

    assert result == description_path


def test_resolve_description_save_path_falls_back_to_source_stem(tmp_path: Path) -> None:
    result = resolve_description_save_path(None, "episode.transcript.txt", tmp_path / "outputs")

    assert result == tmp_path / "outputs" / "episode.transcript" / "description.md"


def test_check_description_file_returns_error_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    description = tmp_path / "outputs/episode/description.md"
    description.parent.mkdir(parents=True)
    description.write_text("▼今回のトピック\n募集テーマ\n", encoding="utf-8")

    result = check_description_file(description, config_path)

    assert result.has_errors is True
    assert any(item.level.value == "ERROR" for item in result.results)
    assert "check.ERROR=" in result.debug_log_path.read_text(encoding="utf-8")
