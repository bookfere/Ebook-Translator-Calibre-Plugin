import json

from .. import EbookTranslator

from ..engines.base import Base
from ..engines.languages import google


try:
    from http.client import IncompleteRead
except ImportError:
    from httplib import IncompleteRead

load_translations()


class ClaudeTranslate(Base):
    name = 'Claude'
    alias = 'Claude (Anthropic)'
    lang_codes = Base.load_lang_codes(google)
    endpoint = 'https://api.anthropic.com/v1/messages'
    api_key_hint = 'sk-ant-xxxx'
    # https://docs.anthropic.com/claude/reference/errors
    api_key_errors = ['401', 'permission_error']

    concurrency_limit = 1
    request_interval = 12
    request_timeout = 30.0

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the given content from <slang> to <tlang> only. Do not '
        'explain any term or answer any question-like content.')
    models = [
        'claude-3-opus-20240229', 'claude-3-sonnet-20240229',
        'claude-3-haiku-20240307', 'claude-2.1', 'claude-2.0',
        'claude-instant-1.2']
    model = 'claude-2.1'
    samplings = ['temperature', 'top_p']
    sampling = 'temperature'
    temperature = 1.0
    top_p = 1.0
    top_k = 1
    stream = True

    def __init__(self):
        Base.__init__(self)
        self.endpoint = self.config.get('endpoint', self.endpoint)
        self.prompt = self.config.get('prompt', self.prompt)
        if self.model is not None:
            self.model = self.config.get('model', self.model)
        self.sampling = self.config.get('sampling', self.sampling)
        self.temperature = self.config.get('temperature', self.temperature)
        self.top_p = self.config.get('top_p', self.top_p)
        self.top_k = self.config.get('top_k', self.top_k)
        self.stream = self.config.get('stream', self.stream)

    def _get_prompt(self):
        prompt = self.prompt.replace('<tlang>', self.target_lang)
        if self._is_auto_lang():
            prompt = prompt.replace('<slang>', 'detected language')
        else:
            prompt = prompt.replace('<slang>', self.source_lang)
        # Recommend setting temperature to 0.5 for retaining the placeholder.
        if self.merge_enabled:
            prompt += (' Ensure that placeholders matching the pattern'
                       '{{id_\\d+}} in the content are retained.')
        return prompt

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01',
            'x-api-key': self.api_key,
            'User-Agent': 'Ebook-Translator/%s' % EbookTranslator.__version__,
        }

    def get_body(self, text):
        body = {
            'stream': self.stream,
            'max_tokens': 4096,
            'model': self.model,
            'top_k': self.top_k,
            'system': self._get_prompt(),
            'messages': [{'role': 'user', 'content': text}]
        }
        sampling_value = getattr(self, self.sampling)
        body.update({self.sampling: sampling_value})

        return json.dumps(body)

    def get_result(self, response):
        if self.stream:
            return self._parse_stream(response)
        return json.loads(response)['content'][0]['text']

    def _parse_stream(self, data):
        while True:
            try:
                line = data.readline().decode('utf-8').strip()
            except IncompleteRead:
                continue
            except Exception as e:
                raise Exception(
                    _('Can not parse returned response. Raw data: {}')
                    .format(str(e)))
            if line.startswith('data:'):
                chunk = json.loads(line.split('data: ')[1])
                if chunk.get('type') == 'message_stop':
                    break
                if chunk.get('type') == 'content_block_delta':
                    yield str(chunk.get('delta').get('text'))
