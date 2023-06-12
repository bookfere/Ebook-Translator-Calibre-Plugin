import json

from .base import Base
from .languages import google


try:
    from http.client import IncompleteRead
except ImportError:
    from httplib import IncompleteRead

load_translations()


class ChatgptTranslate(Base):
    name = 'ChatGPT'
    alias = 'ChatGPT (OpenAI)'
    lang_codes = Base.load_lang_codes(google)
    endpoint = 'https://api.openai.com/v1/chat/completions'
    # api_key_hint = 'sk-xxx...xxx'
    # https://help.openai.com/en/collections/3808446-api-error-codes-explained
    api_key_errors = ['401', 'unauthorized', 'quota']

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the content from <slang> to <tlang>.')
    models = ['gpt-3.5-turbo', 'gpt-3.5-turbo-0301', 'gpt-4', 'gpt-4-0314',
              'gpt-4-32k', 'gpt-4-32k-0314']
    model = 'gpt-3.5-turbo'
    samplings = ['temperature', 'top_p']
    sampling = 'temperature'
    temperature = 1
    top_p = 1
    stream = True

    def __init__(self):
        Base.__init__(self)
        self.endpoint = self.config.get('endpoint', self.endpoint)
        self.prompt = self.config.get('prompt', self.prompt)
        self.model = self.config.get('model', self.model)
        self.sampling = self.config.get('sampling', self.sampling)
        self.temperature = self.config.get('temperature', self.temperature)
        self.top_p = self.config.get('top_p', self.top_p)
        self.stream = self.config.get('stream', self.stream)

    def set_prompt(self, prompt):
        self.prompt = prompt

    def get_prompt(self):
        prompt = self.prompt.replace('<tlang>', self.target_lang)
        if self._is_auto_lang():
            prompt = prompt.replace('<slang>', 'detect language')
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
            'Authorization': 'Bearer %s' % self.api_key
        }

    def translate(self, text):
        prompt = self.get_prompt()
        headers = self.get_headers()

        data = {
            'stream': self.stream,
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': text}
            ]
        }

        sampling_value = getattr(self, self.sampling)
        data.update({self.sampling: sampling_value})

        callback = self.parse_stream if self.stream else self.parse
        return self.get_result(
            self.endpoint, json.dumps(data), headers, method='POST',
            stream=self.stream, callback=callback)

    def parse_stream(self, data):
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
                chunk = line.split('data: ')[1]
                if chunk == '[DONE]':
                    break
                delta = json.loads(chunk)['choices'][0]['delta']
                if 'content' in delta:
                    yield delta['content']

    def parse(self, data):
        return json.loads(data)['choices'][0]['message']['content']


class AzureChatgptTranslate(ChatgptTranslate):
    name = 'ChatGPT(Azure)'
    alias = 'ChatGPT (Azure)'
    endpoint = ('https://{your-resource-name}.openai.azure.com/openai/'
                'deployments/{deployment-id}/chat/completions'
                '?api-version={api-version}')

    def get_headers(self):
        return {
            'Content-Type': 'application/json',
            'api-key': self.api_key
        }
