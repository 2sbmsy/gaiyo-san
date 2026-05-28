from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from poddesc.config import AppConfig


class CheckLevel(str, Enum):
    OK = "OK"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class CheckResult:
    level: CheckLevel
    message: str


def _section_body(text: str, heading: str) -> str:
    pattern = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""

    rest = text[match.end() :]
    next_heading = re.search(r"^▼.+$", rest, re.MULTILINE)
    if next_heading:
        rest = rest[: next_heading.start()]
    return rest.strip()


def extract_topics(description: str, config: AppConfig | None = None) -> list[str]:
    config = config or AppConfig()
    body = _section_body(description, config.description.topics_heading)
    if not body:
        return []

    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if not first_line:
        return []

    return [topic.strip() for topic in first_line.split(config.description.topic_separator.strip()) if topic.strip()]


def extract_culture_topics(description: str) -> list[str]:
    return extract_topics(description)


def check_description(description: str, config: AppConfig) -> list[CheckResult]:
    results: list[CheckResult] = []

    required_headings = (
        config.description.intro_heading,
        config.description.links_heading,
        config.description.topics_heading,
    )
    for heading in required_headings:
        if heading in description:
            results.append(CheckResult(CheckLevel.OK, f"Required heading found: {heading}"))
        else:
            results.append(CheckResult(CheckLevel.ERROR, f"Required heading missing: {heading}"))

    topics = extract_topics(description, config)
    topic_count = len(topics)
    if config.description.topic_min <= topic_count <= config.description.topic_max:
        results.append(CheckResult(CheckLevel.OK, f"Topic count is {topic_count}"))
    elif topic_count == 0:
        results.append(CheckResult(CheckLevel.ERROR, "Topics were not found"))
    else:
        results.append(
            CheckResult(
                CheckLevel.WARN,
                f"Topic count is {topic_count}; recommended range is {config.description.topic_min}-{config.description.topic_max}",
            )
        )

    long_topics = [topic for topic in topics if len(topic) > config.description.topic_error_length]
    warn_topics = [
        topic
        for topic in topics
        if config.description.topic_warn_length < len(topic) <= config.description.topic_error_length
    ]
    if long_topics:
        results.append(CheckResult(CheckLevel.ERROR, f"Topic is too long: {long_topics[0]}"))
    elif warn_topics:
        results.append(CheckResult(CheckLevel.WARN, f"Topic may be too long: {warn_topics[0]}"))
    elif topics:
        results.append(CheckResult(CheckLevel.OK, "Topic lengths look good"))

    topics_body = _section_body(description, config.description.topics_heading)
    if any(marker in topics_body for marker in config.description.exclude_topic_markers):
        results.append(CheckResult(CheckLevel.ERROR, "Topics contain excluded marker wording"))
    elif topics_body:
        results.append(CheckResult(CheckLevel.OK, "Topics do not contain excluded marker wording"))

    link_body = _section_body(description, config.description.links_heading)
    for link in config.links:
        if link.label in link_body and link.url in link_body:
            results.append(CheckResult(CheckLevel.OK, f"{link.label} link matches config"))
        elif link.url in link_body:
            results.append(CheckResult(CheckLevel.OK, f"{link.label} URL matches config"))
        else:
            results.append(CheckResult(CheckLevel.ERROR, f"{link.label} link does not match config: {link.url}"))

    return results


def has_errors(results: list[CheckResult]) -> bool:
    return any(result.level == CheckLevel.ERROR for result in results)
