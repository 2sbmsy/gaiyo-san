from pathlib import Path

from poddesc.config import load_config
from poddesc.description_generator import build_prompts, parse_draft


def _write_config(tmp_path: Path) -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/system.md").write_text("system prompt", encoding="utf-8")
    (tmp_path / "prompts/user.md").write_text(
        "番組: {program_name}\n本文: {transcript}",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
program_name: "Sample Podcast"
output_dir: "outputs"
prompts:
  system: "prompts/system.md"
  user: "prompts/user.md"
""",
        encoding="utf-8",
    )
    return config_path


def test_build_prompts_uses_prompt_files_and_transcript(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    prompts = build_prompts("今日は映画の話", config)

    assert prompts.system == "system prompt"
    assert "Sample Podcast" in prompts.user
    assert "今日は映画の話" in prompts.user


def test_parse_draft_reads_json_response() -> None:
    draft = parse_draft('{"episode_number": "第1回", "title": "映画", "topics": ["映画館"]}')

    assert draft.episode_number == "第1回"
    assert draft.title == "映画"
    assert draft.topics == ["映画館"]
