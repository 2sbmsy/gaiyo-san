class PoddescError(Exception):
    """Base exception for user-facing CLI failures."""


class StepError(PoddescError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"[{step}] {message}")
        self.step = step
        self.message = message
