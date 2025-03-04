from abc import ABC, abstractmethod

from .base import Base


class GenAI(Base, ABC):
    """Each GenAI model should inherit this class to use specific methods."""

    @abstractmethod
    def get_models(self) -> list[str]:
        """Automatically get the models for the engine."""
