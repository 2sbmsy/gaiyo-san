from pathlib import Path

from typer.testing import CliRunner

import poddesc.cli as cli
from poddesc.cli import app
from poddesc.description_generator import GenerationResult


runner = CliRunner()


def _write_cli_config(tmp_path: Path) -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/description_system.md").write_text("system", encoding="utf-8")
    (tmp_path / "prompts/description_user.md").write_text(
        "program={program_name}\ntranscript={transcript}",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
program_name: "Sample Podcast"
output_dir: "{tmp_path / "outputs"}"
prompts:
  system: "prompts/description_system.md"
  user: "prompts/description_user.md"
links:
  - label: "Message Form"
    url: "https://example.com/form"
  - label: "Official Links"
    url: "https://example.com/links"
""",
        encoding="utf-8",
    )
    return config_path


def test_from_transcript_dry_run_prints_prompts_without_openai(tmp_path: Path) -> None:
    config_path = _write_cli_config(tmp_path)
    transcript = tmp_path / "episode.txt"
    transcript.write_text("映画の話をしました", encoding="utf-8")

    result = runner.invoke(app, ["from-transcript", str(transcript), "--config", str(config_path), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run: OpenAI API will not be called." in result.output
    assert "----- description_system.md -----" in result.output
    assert "transcript=映画の話をしました" in result.output
    assert not (tmp_path / "outputs/episode/description.md").exists()


def test_generate_skip_whisper_uses_existing_transcript_without_audio_file(tmp_path: Path) -> None:
    config_path = _write_cli_config(tmp_path)
    output_dir = tmp_path / "outputs/audio"
    output_dir.mkdir(parents=True)
    (output_dir / "transcript.txt").write_text("既存の文字起こし", encoding="utf-8")

    result = runner.invoke(
        app,
        ["generate", str(tmp_path / "audio.mp3"), "--config", str(config_path), "--skip-whisper", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "Skipping Whisper. Using existing transcript" in result.output
    assert "transcript=既存の文字起こし" in result.output


def test_generate_from_text_saves_metadata(monkeypatch, tmp_path: Path) -> None:
    config_path = _write_cli_config(tmp_path)

    monkeypatch.setattr(
        cli,
        "generate_description",
        lambda transcript, config: GenerationResult(
            description="第1回【映画】\n\n▼今回のトピック\n映画\n",
            metadata={"raw_content": '{"title":"映画"}'},
            topics_line="映画",
        ),
    )
    monkeypatch.setattr(cli, "_copy_to_clipboard", lambda content, debug_log_path=None: None)

    debug_log_path = tmp_path / "outputs/episode/debug.log"
    description_path = cli._generate_from_text(
        "映画の話",
        tmp_path / "outputs/episode",
        config_path,
        debug_log_path=debug_log_path,
    )

    assert description_path == tmp_path / "outputs/episode/description.md"
    assert (tmp_path / "outputs/episode/metadata.json").exists()
    assert '"raw_content": "{\\"title\\":\\"映画\\"}"' in (tmp_path / "outputs/episode/metadata.json").read_text(
        encoding="utf-8"
    )
    assert "openai.request.done=true" in debug_log_path.read_text(encoding="utf-8")


def test_check_command_reports_ok(tmp_path: Path) -> None:
    config_path = _write_cli_config(tmp_path)
    description = tmp_path / "description.md"
    description.write_text(
        """第1回【文化】

▼番組紹介
紹介文

▼リンク
Message Form：https://example.com/form
Official Links：https://example.com/links

▼今回のトピック
映画 / 漫画 / ラジオ / 仕事 / 音楽
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", str(description), "--config", str(config_path)])

    assert result.exit_code == 0
    assert "OK: Required heading found: ▼今回のトピック" in result.output
    assert "command.check.done has_errors=false" in (tmp_path / "debug.log").read_text(encoding="utf-8")


def test_check_command_exits_one_on_error(tmp_path: Path) -> None:
    config_path = _write_cli_config(tmp_path)
    description = tmp_path / "description.md"
    description.write_text("▼今回のトピック\n募集テーマ\n", encoding="utf-8")

    result = runner.invoke(app, ["check", str(description), "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR:" in result.output


def test_from_transcript_no_copy_succeeds_without_pbcopy(monkeypatch, tmp_path: Path) -> None:
    config_path = _write_cli_config(tmp_path)
    transcript = tmp_path / "episode.txt"
    transcript.write_text("映画の話をしました", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "generate_description",
        lambda transcript, config: GenerationResult(
            description="第1回【映画】\n\n▼今回のトピック\n映画 / 音楽 / 仕事 / 料理 / 旅\n",
            metadata={"raw_content": '{"title":"映画"}'},
            topics_line="映画 / 音楽 / 仕事 / 料理 / 旅",
        ),
    )
    monkeypatch.setattr(cli, "_copy_to_clipboard", lambda content, debug_log_path=None: (_ for _ in ()).throw(AssertionError))

    result = runner.invoke(app, ["from-transcript", str(transcript), "--config", str(config_path), "--no-copy"])

    assert result.exit_code == 0
    assert "Description saved:" in result.output
    assert "Clipboard copy attempted." not in result.output
