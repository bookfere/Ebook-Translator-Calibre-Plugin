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

    @abstractmethod
    def get_models(self) -> list[str]:
        """Automatically get the models for the engine."""
