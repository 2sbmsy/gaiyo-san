from poddesc.config import AppConfig, DescriptionConfig, LinkConfig
from poddesc.renderer import (
    DescriptionDraft,
    is_culture_line_too_long,
    is_topics_line_too_long,
    render_description,
    strip_trailing_extras,
)


def test_render_description_uses_required_format() -> None:
    result = render_description(
        DescriptionDraft(
            episode_number="第12回",
            title="映画と近況",
            topics=["映画館", "最近の買い物", "仕事の話", "漫画"],
        )
    )

    assert result.startswith("第12回【映画と近況】")
    assert "▼番組紹介" in result
    assert "Message Form：https://example.com/message" in result
    assert "▼今回のトピック\n映画館 / 最近の買い物 / 仕事の話 / 漫画" in result


def test_render_description_uses_configured_template() -> None:
    config = AppConfig(
        description=DescriptionConfig(
            intro_heading="## About",
            links_heading="## Links",
            topics_heading="## Topics",
            intro_text="Custom intro",
            topic_separator=" | ",
        ),
        links=(LinkConfig(label="Website", url="https://example.com/site"),),
    )

    result = render_description(
        DescriptionDraft(episode_number="", title="Custom", topics=["A", "B"]),
        config,
    )

    assert "## About\nCustom intro" in result
    assert "## Links\nWebsite：https://example.com/site" in result
    assert "## Topics\nA | B" in result


def test_render_description_filters_letter_theme_from_culture_topics() -> None:
    result = render_description(
        DescriptionDraft(
            episode_number="",
            title="募集告知を除外する回",
            topics=["映画", "お便りテーマ：夏の思い出", "音楽"],
        )
    )

    assert "お便りテーマ" not in result
    assert "▼今回のトピック\n映画 / 音楽" in result


def test_strip_trailing_extras_removes_unwanted_tail() -> None:
    result = strip_trailing_extras("本文\n\n以上です。\n")

    assert result == "本文\n"


def test_is_culture_line_too_long_detects_long_topics() -> None:
    assert is_culture_line_too_long("あ" * 221)
    assert not is_culture_line_too_long("あ" * 220)
    assert is_topics_line_too_long("a" * 6, DescriptionConfig(topic_line_warning_length=5))
