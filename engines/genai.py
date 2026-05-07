from abc import ABC, abstractmethod

from .base import Base


class GenAI(Base, ABC):
    """Each GenAI model should inherit this class to use specific methods."""

    prompt: str
    models: list[str]
    model: str | None
    samplings: list
    sampling: str
    temperature: float
    top_p: float
    top_k: int

    # Fixed rules that must always be applied, even with custom prompts
    context_rules = (
        'CRITICAL: Your output must ONLY contain the translation of the current '
        'input. Never include, summarize, or acknowledge any text from the '
        'provided context block. If the input is a short marker (e.g., "TL notes:"), '
        'translate it literally or keep it as is. DO NOT replace the input with '
        'placeholders or content found in the context block. HTML entities '
        '(e.g., "&nbsp;", "&amp;", etc.) must be preserved exactly as they are. '
        'CRITICAL: The length and meaning of your output must strictly correspond '
        'to the input. Never expand a short input, symbol, or HTML entity into a '
        'full sentence using information from the context.')

    @abstractmethod
    def get_models(self) -> list[str]:
        """Automatically get the models for the engine."""
