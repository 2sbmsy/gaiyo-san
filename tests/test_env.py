from pathlib import Path

from poddesc.env import ensure_openai_api_key, load_local_env


def test_load_local_env_reads_openai_api_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        """
# ignored
OPENAI_API_KEY=sk-test-local
""",
        encoding="utf-8",
    )

    loaded = load_local_env([env_file])

    assert loaded == {"OPENAI_API_KEY"}
    assert ensure_openai_api_key()


def test_load_local_env_does_not_override_existing_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "already-set")
    env_file = tmp_path / ".env.local"
    env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")

    loaded = load_local_env([env_file])

    assert loaded == set()
    assert ensure_openai_api_key()
