from .openai import ChatgptTranslate

load_translations()  # type: ignore


class DeepseekTranslate(ChatgptTranslate):
    name = 'DeepSeek'
    alias = 'DeepSeek (Chat)'
    endpoint = 'https://api.deepseek.com/v1/chat/completions'
    temperature = 1.3

    concurrency_limit = 0
    request_interval = 0.0

    models: list[str] = ['deepseek-chat', 'deepseek-reasoner']
    model: str | None = models[0]

    def __init__(self):
        super().__init__()
        self.model = self.config.get('model', self.model)

    def get_models(self):
        return self.models
