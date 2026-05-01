import json
from .languages import google
from .genai import GenAI


class LaraTranslate(GenAI):
    name = 'LaraTranslate(Free)'
    alias = 'Lara Translate (Free)'
    free = True
    lang_codes = GenAI.load_lang_codes(google)
    need_api_key = False

    samplings = ['static']
    sampling = 'static'

    endpoint = 'https://webapi.laratranslate.com/translate/segmented'
    api_key_errors: list[str] = ['401']

    concurrency_limit = 1
    request_interval: float = 1.0
    request_timeout: float = 30.0
    
    temperature = 1.0
    top_p = 1.0
    top_k = 1
    stream = False
    not_need_tlang = True

    prompt = (
        'Your answer should be solely the translation of the given content. In your '
        'answer do not add any prefix or suffix to the translated content. '
        "Websites' URLs/addresses should be preserved as is in the "
        "translation's output. Do not omit any part of the content, even if "
        'it seems unimportant. '
    )

    models: list[str] = []
    model: str | None = None

    def __init__(self):
        super().__init__()
        self.prompt = self.config.get('prompt', self.prompt)

    def _prompt(self, _text):
        return self.prompt

    def get_models(self):
        return []

    def get_headers(self):
        return {'Content-Type': 'application/json'}

    def get_body(self, text):
        source = self._get_source_code()
        if source == 'auto':
            source = ''
        return json.dumps(
            {
                'adapt_to': [],
                'content_type': 'text/plain',
                'glossaries': [],
                'instructions': [self.prompt],
                'q': text,
                'source': source,
                'style': 'faithful',
                'target': self._get_target_code()
            }
        )

    def get_result(self, response):
        return json.loads(response)['content']['translations'][0]['translation']
