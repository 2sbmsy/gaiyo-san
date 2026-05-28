from __future__ import annotations

import re


TIMESTAMP_RE = re.compile(r"\[?\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*-->\s*\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\]?")
SPEAKER_PREFIX_RE = re.compile(r"^\s*(話者|speaker)\s*\d+\s*[:：]\s*", re.IGNORECASE)


def clean_transcript(text: str) -> str:
    lines: list[str] = []

    for raw_line in text.splitlines():
        line = TIMESTAMP_RE.sub("", raw_line)
        line = SPEAKER_PREFIX_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            continue
        lines.append(line)

    return "\n".join(lines).strip()
