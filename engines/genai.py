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

    # Marker consumed by the novel translation pipeline (lib/novel.py) and
    # by the UI: only engines that expose an LLM chat interface should be
    # eligible for novel mode, since it relies on a system prompt carrying
    # a running summary and glossary. Non-GenAI engines (Google, DeepL, ...)
    # leave this at False on ``Base``.
    supports_novel_mode: bool = True

    @abstractmethod
    def get_models(self) -> list[str]:
        """Automatically get the models for the engine."""

    # ------------------------------------------------------------------
    # Novel mode support: transient prompt override.
    # ------------------------------------------------------------------
    #
    # The default paragraph-per-request pipeline uses ``self.prompt`` as the
    # system prompt for every call. The novel pipeline instead wants to
    # inject a *different* system prompt for each request (containing the
    # running summary and the dynamic glossary) without permanently mutating
    # the engine configuration.
    #
    # ``override_prompt`` saves the current prompt (once, so nested calls
    # remain safe) and swaps in the new one; ``restore_prompt`` puts the
    # original prompt back. Sub-classes that build the message payload from
    # ``self.prompt`` (ChatGPT, Claude, Gemini) do not need any further
    # change: they will naturally pick up the overridden value.

    def override_prompt(self, prompt_text):
        if not hasattr(self, '_prompt_stash'):
            self._prompt_stash = self.prompt
        self.prompt = prompt_text

    def restore_prompt(self):
        if hasattr(self, '_prompt_stash'):
            self.prompt = self._prompt_stash
            del self._prompt_stash
