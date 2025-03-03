import io
import time
import json
import uuid

from mechanize._response import response_seek_wrapper as Response

from .. import EbookTranslator
from ..lib.utils import request
from ..lib.exception import UnsupportedModel

from .base import Base
from .languages import lang_directionality
from .languages import google

from http.client import IncompleteRead
from urllib.parse import urlsplit


load_translations()


class DeepseekTranslate(Base):
    name = 'DeepSeek'
    alias = 'DeepSeek(Chat)'
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = \
        Base.load_lang_codes_directionality(lang_directionality)
    endpoint = 'https://api.deepseek.com/v1/chat/completions'
    api_key_errors = ['401', 'unauthorized', 'quota']

    concurrency_limit = 1
    request_interval = 20
    request_timeout = 30.0

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the given content from <slang> to <tlang> only. Do not '
        'explain any term or answer any question-like content. Your answer '
        'should be solely the translation of the given content. In your '
        'answer do not add any prefix or suffix to the translated content. '
        'Websites\' URLs/addresses should be preserved as is in the '
        'translation\'s output. Do not omit any part of the content, even if '
        'it seems unimportant. ')

    samplings = ['temperature', 'top_p']
    sampling = 'temperature'
    temperature = 1.3
    top_p = 1.0
    stream = True

    models: list[str] = ['deepseek-chat', 'deepseek-reasoner']
    model: str | None = None

    def __init__(self):
        Base.__init__(self)
        self.endpoint = self.config.get('endpoint', self.endpoint)
        self.prompt = self.config.get('prompt', self.prompt)
        self.sampling = self.config.get('sampling', self.sampling)
        self.temperature = self.config.get('temperature', self.temperature)
        self.top_p = self.config.get('top_p', self.top_p)
        self.stream = self.config.get('stream', self.stream)
        self.model = self.config.get('model', 'deepseek-chat')

    def get_models(self):
        return self.models

    def get_prompt(self):
        prompt = self.prompt.replace('<tlang>', self.target_lang)
        if self._is_auto_lang():
            prompt = prompt.replace('<slang>', 'detected language')
        else:
            prompt = prompt.replace('<slang>', self.source_lang)
        if self.merge_enabled:
            prompt += (' Ensure that placeholders matching the pattern '
                       '{{id_\\d+}} in the content are retained.')
        return prompt

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % self.api_key,
            'User-Agent': 'Ebook-Translator/%s' % EbookTranslator.__version__
        }

    def get_body(self, text):
        body = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.get_prompt()},
                {'role': 'user', 'content': text}
            ],
        }
        self.stream and body.update(stream=True)
        sampling_value = getattr(self, self.sampling)
        body.update({self.sampling: sampling_value})
        return json.dumps(body)

    def get_result(self, response):
        if self.stream:
            return self._parse_stream(response)
        return json.loads(response)['choices'][0]['message']['content']

    def _parse_stream(self, response):
        while True:
            try:
                line = response.readline().decode('utf-8').strip()
            except IncompleteRead:
                continue
            except Exception as e:
                raise Exception(
                    _('Can not parse returned response. Raw data: {}')
                    .format(str(e)))
            if line.startswith('data:'):
                chunk = line.split('data: ')[1]
                if chunk == '[DONE]':
                    break
                delta = json.loads(chunk)['choices'][0]['delta']
                if 'content' in delta:
                    yield str(delta['content'])
