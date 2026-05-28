from poddesc.transcript_cleaner import clean_transcript


def test_clean_transcript_removes_timestamps_and_blank_lines() -> None:
    raw = """
    [00:00.000 --> 00:02.000] こんにちは

    話者1: 今日は映画の話です
    [00:02.000 --> 00:04.000]
    """

    assert clean_transcript(raw) == "こんにちは\n今日は映画の話です"


def test_clean_transcript_collapses_spaces() -> None:
    raw = "  Sample   Podcast   の   話  "

    assert clean_transcript(raw) == "Sample Podcast の 話"
