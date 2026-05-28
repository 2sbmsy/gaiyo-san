from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated

import typer

from poddesc.checker import CheckLevel
from poddesc.config import load_config
from poddesc.debug_log import append_debug_log
from poddesc.description_generator import generate_description
from poddesc.errors import PoddescError, StepError
from poddesc.renderer import is_topics_line_too_long
from poddesc.workflow import (
    build_dry_run_prompts,
    check_description_file,
    episode_output_dir,
    generate_from_text as workflow_generate_from_text,
    transcribe_audio,
    write_json,
    write_text,
)

app = typer.Typer(help="Generate podcast descriptions from audio or transcripts.")


def _episode_output_dir(root: Path, source_file: Path) -> Path:
    return episode_output_dir(root, source_file)


def _write_text(path: Path, content: str) -> None:
    write_text(path, content)


def _write_json(path: Path, content: dict) -> None:
    write_json(path, content)


def _copy_to_clipboard(content: str, debug_log_path: Path | None = None) -> None:
    try:
        subprocess.run(["pbcopy"], input=content, text=True, check=True)
        append_debug_log(debug_log_path, "clipboard.copied=true")
    except FileNotFoundError:
        append_debug_log(debug_log_path, "clipboard.error=pbcopy command not found")
        typer.secho(
            "Warning: pbcopy was not found. Description was saved to a file but not copied to the clipboard.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    except subprocess.CalledProcessError:
        append_debug_log(debug_log_path, "clipboard.error=pbcopy failed")
        typer.secho(
            "Warning: pbcopy failed. Description was saved to a file but not copied to the clipboard.",
            fg=typer.colors.YELLOW,
            err=True,
        )


def _print_dry_run_prompts(transcript: str, config_path: Path, debug_log_path: Path | None = None) -> None:
    prompts = build_dry_run_prompts(transcript, config_path, debug_log_path=debug_log_path)
    typer.echo("----- description_system.md -----")
    typer.echo(prompts.system)
    typer.echo("----- description_user.md -----")
    typer.echo(prompts.user)


def _generate_from_text(
    transcript_text: str,
    output_dir: Path,
    config_path: Path,
    dry_run: bool = False,
    copy: bool = True,
    debug_log_path: Path | None = None,
) -> Path | None:
    typer.echo("Cleaning transcript...")

    if dry_run:
        typer.echo("Dry run: OpenAI API will not be called.")
        result = workflow_generate_from_text(
            transcript_text,
            output_dir,
            config_path,
            dry_run=True,
            debug_log_path=debug_log_path,
            description_generator=generate_description,
        )
        if result.prompts is not None:
            typer.echo("----- description_system.md -----")
            typer.echo(result.prompts.system)
            typer.echo("----- description_user.md -----")
            typer.echo(result.prompts.user)
        return None

    typer.echo("Generating description with OpenAI API...")
    result = workflow_generate_from_text(
        transcript_text,
        output_dir,
        config_path,
        dry_run=False,
        debug_log_path=debug_log_path,
        description_generator=generate_description,
    )
    typer.echo(f"Metadata saved: {result.metadata_path}")

    if result.topics_line and is_topics_line_too_long(result.topics_line, load_config(config_path).description):
        append_debug_log(debug_log_path, f"warning.topics_line_too_long chars={len(result.topics_line)}")
        typer.secho(
            f"Warning: topics line is long ({len(result.topics_line)} characters). Consider shortening topics before publishing.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    if copy:
        typer.echo("Copying description to clipboard...")
        _copy_to_clipboard(result.description or "", debug_log_path=debug_log_path)
    else:
        append_debug_log(debug_log_path, "clipboard.skipped=true")
    return result.description_path


@app.command()
def generate(
    audio_file: Annotated[Path, typer.Argument(help="Audio file to transcribe.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config.yaml.")] = Path("config.yaml"),
    skip_whisper: Annotated[
        bool,
        typer.Option("--skip-whisper", help="Reuse outputs/<audio file name>/transcript.txt instead of running Whisper."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the OpenAI prompts without calling the OpenAI API."),
    ] = False,
    copy: Annotated[
        bool,
        typer.Option("--copy/--no-copy", help="Copy the generated description to the macOS clipboard when possible."),
    ] = True,
) -> None:
    """Transcribe an audio file with local Whisper and generate a podcast description."""
    try:
        app_config = load_config(config)
        output_dir = _episode_output_dir(app_config.output_dir, audio_file)
        debug_log_path = output_dir / "debug.log"
        append_debug_log(debug_log_path, "command.generate.start")
        append_debug_log(debug_log_path, f"audio_file={audio_file}")
        append_debug_log(debug_log_path, f"skip_whisper={skip_whisper}")
        append_debug_log(debug_log_path, f"dry_run={dry_run}")
        typer.echo(f"Output: {output_dir}")
        typer.echo(f"Debug log: {debug_log_path}")

        if skip_whisper:
            transcript_path = output_dir / "transcript.txt"
            typer.echo(f"Skipping Whisper. Using existing transcript: {transcript_path}")
        else:
            typer.echo("Running Whisper transcription...")
            typer.echo("Saving transcript...")

        transcript = transcribe_audio(audio_file, config, skip_whisper=skip_whisper, app_config=app_config)

        description_path = _generate_from_text(
            transcript.transcript_text,
            output_dir,
            config,
            dry_run=dry_run,
            copy=copy,
            debug_log_path=debug_log_path,
        )
        if description_path is not None:
            typer.echo(f"Description saved: {description_path}")
            if copy:
                typer.echo("Clipboard copy attempted.")
        append_debug_log(debug_log_path, "command.generate.done")
    except PoddescError as exc:
        if "debug_log_path" in locals():
            append_debug_log(debug_log_path, f"command.generate.error={exc}")
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command("from-transcript")
def from_transcript(
    transcript_file: Annotated[Path, typer.Argument(help="Existing transcript text file.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config.yaml.")] = Path("config.yaml"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the OpenAI prompts without calling the OpenAI API."),
    ] = False,
    copy: Annotated[
        bool,
        typer.Option("--copy/--no-copy", help="Copy the generated description to the macOS clipboard when possible."),
    ] = True,
) -> None:
    """Generate a podcast description from an existing transcript."""
    try:
        app_config = load_config(config)
        if not transcript_file.exists():
            raise StepError("input", f"transcript file not found: {transcript_file}")
        if not transcript_file.is_file():
            raise StepError("input", f"transcript path is not a file: {transcript_file}")

        output_dir = _episode_output_dir(app_config.output_dir, transcript_file)
        debug_log_path = output_dir / "debug.log"
        append_debug_log(debug_log_path, "command.from_transcript.start")
        append_debug_log(debug_log_path, f"transcript_file={transcript_file}")
        append_debug_log(debug_log_path, f"dry_run={dry_run}")
        typer.echo(f"Output: {output_dir}")
        typer.echo(f"Debug log: {debug_log_path}")
        raw_transcript = transcript_file.read_text(encoding="utf-8")
        description_path = _generate_from_text(
            raw_transcript,
            output_dir,
            config,
            dry_run=dry_run,
            copy=copy,
            debug_log_path=debug_log_path,
        )
        if description_path is not None:
            typer.echo(f"Description saved: {description_path}")
            if copy:
                typer.echo("Clipboard copy attempted.")
        append_debug_log(debug_log_path, "command.from_transcript.done")
    except PoddescError as exc:
        if "debug_log_path" in locals():
            append_debug_log(debug_log_path, f"command.from_transcript.error={exc}")
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def check(
    description_file: Annotated[Path, typer.Argument(help="Generated description.md file to check.")],
    config: Annotated[Path, typer.Option("--config", "-c", help="Path to config.yaml.")] = Path("config.yaml"),
) -> None:
    """Check a generated podcast description for publishing quality."""
    try:
        debug_log_path = description_file.parent / "debug.log"
        append_debug_log(debug_log_path, "command.check.start")
        append_debug_log(debug_log_path, f"description_file={description_file}")
        typer.echo(f"Debug log: {debug_log_path}")
        check_result = check_description_file(description_file, config)
        for result in check_result.results:
            color = {
                CheckLevel.OK: typer.colors.GREEN,
                CheckLevel.WARN: typer.colors.YELLOW,
                CheckLevel.ERROR: typer.colors.RED,
            }[result.level]
            typer.secho(f"{result.level.value}: {result.message}", fg=color)

        if check_result.has_errors:
            append_debug_log(debug_log_path, "command.check.done has_errors=true")
            raise typer.Exit(code=1)
        append_debug_log(debug_log_path, "command.check.done has_errors=false")
    except PoddescError as exc:
        if "debug_log_path" in locals():
            append_debug_log(debug_log_path, f"command.check.error={exc}")
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
