from calibre.utils.localization import _  # type: ignore

from .openai import ChatgptTranslate


load_translations()  # type: ignore


class LitellmTranslate(ChatgptTranslate):
    name = 'LiteLLM'
    alias = 'LiteLLM (AI Gateway)'
    endpoint = 'http://localhost:4000/v1/chat/completions'
    api_key_hint = _('LiteLLM Proxy Key (master or virtual key)')

    concurrency_limit = 0
    request_interval = 0.0

    models: list[str] = []
    model: str | None = None

    def __init__(self):
        super().__init__()
        self.model = self.config.get('model', self.model)
