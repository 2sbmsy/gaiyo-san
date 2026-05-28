from pathlib import Path

from poddesc.checker import CheckLevel, check_description, extract_topics, has_errors
from poddesc.config import load_config


def _config(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
links:
  - label: "Message Form"
    url: "https://example.com/form"
  - label: "Official Links"
    url: "https://example.com/links"
""",
        encoding="utf-8",
    )
    return load_config(config_path)


def _valid_description() -> str:
    return """第1回【文化】

▼番組紹介
Sample intro.

▼リンク
Message Form：https://example.com/form
Official Links：https://example.com/links

▼今回のトピック
映画 / 漫画 / ラジオ / 仕事 / 音楽 / 料理
"""


def test_extract_topics(tmp_path: Path) -> None:
    assert extract_topics(_valid_description(), _config(tmp_path)) == ["映画", "漫画", "ラジオ", "仕事", "音楽", "料理"]


def test_check_description_validates_required_items(tmp_path: Path) -> None:
    results = check_description(_valid_description(), _config(tmp_path))

    assert not has_errors(results)
    assert any(result.level == CheckLevel.OK and "Topic count is 6" in result.message for result in results)
    assert any("link matches config" in result.message for result in results)


def test_check_description_allows_more_culture_topics(tmp_path: Path) -> None:
    description = _valid_description().replace(
        "映画 / 漫画 / ラジオ / 仕事 / 音楽 / 料理",
        "映画 / 漫画 / ラジオ / 仕事 / 音楽 / 料理 / 友達 / 駅前 / 買い物 / 深夜の話 / 旅の記憶 / 最近のニュース",
    )

    results = check_description(description, _config(tmp_path))

    assert not has_errors(results)
    assert any(result.level == CheckLevel.OK and "Topic count is 12" in result.message for result in results)


def test_check_description_errors_on_missing_heading_and_bad_url(tmp_path: Path) -> None:
    description = _valid_description().replace("▼番組紹介", "番組紹介").replace("https://example.com/form", "https://bad.example")

    results = check_description(description, _config(tmp_path))

    assert has_errors(results)
    assert any(result.level == CheckLevel.ERROR and "Required heading missing: ▼番組紹介" in result.message for result in results)
    assert any(result.level == CheckLevel.ERROR and "Message Form link does not match" in result.message for result in results)


def test_check_description_warns_on_low_topic_count_and_errors_on_very_long_topic(tmp_path: Path) -> None:
    description = _valid_description().replace(
        "映画 / 漫画 / ラジオ / 仕事 / 音楽 / 料理",
        "映画 / とても長いトピック名なので掲載前に短くしたほうがよい話題タイトルですという説明がまだまだ続いてしまっていて結局ひとつのトピックではなく文章になっている状態",
    )

    results = check_description(description, _config(tmp_path))

    assert any(result.level == CheckLevel.WARN and "Topic count is 2" in result.message for result in results)
    assert any(result.level == CheckLevel.ERROR and "Topic is too long" in result.message for result in results)


def test_check_description_errors_on_excluded_marker_in_topics(tmp_path: Path) -> None:
    description = _valid_description().replace("映画 / 漫画 / ラジオ / 仕事 / 音楽 / 料理", "映画 / 募集テーマ / ラジオ / 仕事 / 音楽")

    results = check_description(description, _config(tmp_path))

    assert any(result.level == CheckLevel.ERROR and "excluded marker" in result.message for result in results)


def test_check_description_uses_configured_headings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
description:
  intro_heading: "## About"
  links_heading: "## URLs"
  topics_heading: "## Topics"
  topic_min: 2
links:
  - label: "Site"
    url: "https://example.com/site"
""",
        encoding="utf-8",
    )
    config = load_config(config_path)
    description = """Episode

## About
Intro.

## URLs
Site：https://example.com/site

## Topics
映画 / 音楽
"""

    results = check_description(description, config)

    assert not has_errors(results)
    assert any(result.message == "Required heading found: ## Topics" for result in results)
