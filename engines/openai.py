import io
import json
import uuid
from typing import Any
from urllib.parse import urlsplit
from http.client import IncompleteRead

from mechanize._response import response_seek_wrapper as Response
from calibre.utils.localization import _  # type: ignore

from .. import EbookTranslator
from ..lib.utils import request
from ..lib.exception import UnsupportedModel

from .genai import GenAI
from .languages import google


load_translations()  # type: ignore


class ChatgptTranslate(GenAI):
    name = 'ChatGPT'
    alias = 'ChatGPT (OpenAI)'
    lang_codes = GenAI.load_lang_codes(google)
    endpoint = 'https://api.openai.com/v1/chat/completions'
    # api_key_hint = 'sk-xxx...xxx'
    # https://help.openai.com/en/collections/3808446-api-error-codes-explained
    api_key_errors = ['401', 'unauthorized', 'quota']

    concurrency_limit = 1
    request_interval = 20.0
    request_timeout = 60.0

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the given content from <slang> to <tlang> only. Do not '
        'explain any term or answer any question-like content. Your answer '
        'should be solely the translation of the given content. In your '
        'answer do not add any prefix or suffix to the translated content. '
        'Websites\' URLs/addresses should be preserved as is in the '
        'translation\'s output. Do not omit any part of the content, even if '
        'it seems unimportant. RESPOND ONLY with the translation text, no '
        'formatting, no explanations, no additional commentary whatsoever. ')

    samplings = ['temperature', 'top_p']
    sampling = 'temperature'
    temperature = 1.0
    top_p = 1.0
    stream = True

    models: list[str] = []
    # TODO: Handle the default model more appropriately.
    model: str | None = 'gpt-4o'

    def __init__(self):
        super().__init__()
        self.endpoint = self.config.get('endpoint', self.endpoint)
        self.prompt = self.config.get('prompt', self.prompt)
        self.sampling = self.config.get('sampling', self.sampling)
        self.temperature = self.config.get('temperature', self.temperature)
        self.top_p = self.config.get('top_p', self.top_p)
        self.stream = self.config.get('stream', self.stream)
        self.model = self.config.get('model', self.model)

    def get_models(self):
        domain_name = '://'.join(urlsplit(self.endpoint or '', 'https')[:2])
        model_endpoint = '%s/v1/models' % domain_name
        response = request(
            model_endpoint, headers=self.get_headers(),
            proxy_uri=self.proxy_uri)
        return [item['id'] for item in json.loads(response).get('data')]

    def get_prompt(self):
        prompt = self.prompt.replace('<tlang>', self.target_lang)
        if self._is_auto_lang():
            prompt = prompt.replace('<slang>', 'detected language')
        else:
            prompt = prompt.replace('<slang>', self.source_lang)
        # Recommend setting temperature to 0.5 for retaining the placeholder.
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
        body: dict[str, Any] = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.get_prompt()},
                {'role': 'user', 'content': text}
            ],
        }
        if self.stream:
            body.update(stream=True)
        sampling_value = getattr(self, self.sampling)
        body.update({self.sampling: sampling_value})
        return json.dumps(body)

    def get_result(self, response):
        if self.stream:
            return self._parse_stream(response)
        # Parse JSON response with robust schema handling
        try:
            data = json.loads(response)
            # Handle different response schemas
            if 'choices' in data and len(data['choices']) > 0:
                choice = data['choices'][0]
                # Standard chat/completions format
                if 'message' in choice and 'content' in choice['message']:
                    return choice['message']['content']
                # Alternative format (some nano models)
                elif 'content' in choice:
                    if isinstance(choice['content'], list) \
                            and len(choice['content']) > 0:
                        return choice['content'][0].get('text', '')
                    elif isinstance(choice['content'], str):
                        return choice['content']
                # Direct text format
                elif 'text' in choice:
                    return choice['text']
            # Fallback: try to find content anywhere in the response
            if 'content' in data:
                return data['content']
            raise KeyError('No content found in response')
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise Exception(
                _('Can not parse returned response. Raw data: {}\nError: {}')
                .format(response[:500] + '...' if len(response) > 500 \
                        else response, str(e)))

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
            if not line:
                continue
            if line.startswith('data:'):
                chunk = line.split('data: ')[1]
                if chunk == '[DONE]':
                    break
                try:
                    data = json.loads(chunk)
                    # Handle different streaming response schemas
                    if 'choices' in data and len(data['choices']) > 0:
                        choice = data['choices'][0]
                        # Standard streaming format
                        if 'delta' in choice and 'content' in choice['delta']:
                            content = choice['delta']['content']
                            if content:
                                yield str(content)
                        # Alternative streaming format
                        elif 'content' in choice:
                            content = choice['content']
                            if isinstance(content, list) and len(content) > 0:
                                text = content[0].get('text', '')
                                if text:
                                    yield str(text)
                            elif isinstance(content, str) and content:
                                yield str(content)
                        # Direct text format
                        elif 'text' in choice:
                            text = choice['text']
                            if text:
                                yield str(text)
                except json.JSONDecodeError:
                    # Skip malformed JSON chunks
                    continue


class ChatgptBatchTranslate:
    """https://cookbook.openai.com/examples/batch_processing"""
    boundary = uuid.uuid4().hex

    def __init__(self, translator):
        self.translator = translator
        self.translator.stream = False

        domain_name = '://'.join(
            urlsplit(self.translator.endpoint, 'https')[:2])
        self.file_endpoint = '%s/v1/files' % domain_name
        self.batch_endpoint = '%s/v1/batches' % domain_name

    def _create_multipart_form_data(self, body):
        """https://www.rfc-editor.org/rfc/rfc2046#section-5.1"""
        data = []
        data.append('--%s' % self.boundary)
        data.append('Content-Disposition: form-data; name="purpose"')
        data.append('')
        data.append('batch')
        data.append('--%s' % self.boundary)
        data.append(
            'Content-Disposition: form-data; name="file"; '
            'filename="original.jsonl"')
        data.append('Content-Type: application/json')
        data.append('')
        data.append(body)
        data.append('--%s--' % self.boundary)
        return '\r\n'.join(data).encode('utf-8')

    def supported_models(self):
        return self.translator.get_models()

    def headers(self, extra_headers={}):
        headers = self.translator.get_headers()
        headers.update(extra_headers)
        return headers

    def upload(self, paragraphs):
        """Upload the original content and retrieve the file id.
        https://platform.openai.com/docs/api-reference/files/create
        """
        if self.translator.model not in self.supported_models():
            raise UnsupportedModel(
                'The model "{}" does not support batch functionality.'
                .format(self.translator.model))
        body = io.StringIO()
        for paragraph in paragraphs:
            data = self.translator.get_body(paragraph.original)
            body.write(json.dumps({
                "custom_id": paragraph.md5,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": json.loads(data)}))
            if paragraph != paragraphs[-1]:
                body.write('\n')
        content_type = 'multipart/form-data; boundary="%s"' % self.boundary
        headers = self.headers({'Content-Type': content_type})
        body = self._create_multipart_form_data(body.getvalue())
        response = request(
            self.file_endpoint, body, headers, 'POST',
            proxy_uri=self.translator.proxy_uri)
        return json.loads(response).get('id')

    def delete(self, file_id):
        headers = self.translator.get_headers()
        del headers['Content-Type']
        response = request(
            '%s/%s' % (self.file_endpoint, file_id), headers=headers,
            method='DELETE', proxy_uri=self.translator.proxy_uri)
        return json.loads(response).get('deleted')

    def retrieve(self, output_file_id):
        headers = self.translator.get_headers()
        del headers['Content-Type']
        response = request(
            '%s/%s/content' % (self.file_endpoint, output_file_id),
            headers=headers, raw_object=True,
            proxy_uri=self.translator.proxy_uri)
        assert isinstance(response, Response)

        translations = {}
        for line in io.BytesIO(response.read()):
            result = json.loads(line)
            response_item = result['response']
            if response_item.get('status_code') == 200:
                content = response_item[
                    'body']['choices'][0]['message']['content']
                translations[result.get('custom_id')] = content
        return translations

    def create(self, file_id):
        headers = self.translator.get_headers()
        body = json.dumps({
            'input_file_id': file_id,
            'endpoint': '/v1/chat/completions',
            'completion_window': '24h'})
        response = request(
            self.batch_endpoint, body, headers, 'POST',
            proxy_uri=self.translator.proxy_uri)
        return json.loads(response).get('id')

    def check(self, batch_id):
        response = request(
            '%s/%s' % (self.batch_endpoint, batch_id),
            headers=self.translator.get_headers(),
            proxy_uri=self.translator.proxy_uri)
        return json.loads(response)

    def cancel(self, batch_id):
        headers = self.translator.get_headers()
        response = request(
            '%s/%s/cancel' % (self.batch_endpoint, batch_id),
            headers=headers, method='POST',
            proxy_uri=self.translator.proxy_uri)
        return json.loads(response).get('status') in (
            'cancelling', 'cancelled')
