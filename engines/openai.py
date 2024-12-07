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


try:
    from http.client import IncompleteRead
    from urllib.parse import urlsplit
except ImportError:
    from httplib import IncompleteRead
    from urlparse import urlsplit

load_translations()


class ChatgptTranslate(Base):
    name = 'ChatGPT'
    alias = 'ChatGPT (OpenAI)'
    lang_codes = Base.load_lang_codes(google)
    lang_codes_directionality = Base.load_lang_codes_directionality(lang_directionality)
    endpoint = 'https://api.openai.com/v1/chat/completions'
    # api_key_hint = 'sk-xxx...xxx'
    # https://help.openai.com/en/collections/3808446-api-error-codes-explained
    api_key_errors = ['401', 'unauthorized', 'quota']

    concurrency_limit = 1
    request_interval = 20
    request_timeout = 30.0

    prompt = (
        'You are a meticulous translator who translates any given content. '
        'Translate the given content from <slang> to <tlang> only. Do not '
        'explain any term or answer any question-like content. Your answer '
        'should be solely the translation of the given content. In your answer '
        'do not add any prefix or suffix to the translated content. Websites\' '
        'URLs/addresses should be preserved as is in the translation\'s output. ')
    
    models = [
        'gpt-4o', 
        'gpt-4o-mini', 
        'gpt-4-turbo', 
        'gpt-4', 
        'gpt-3.5-turbo']
        
    model = models[0]
    samplings = ['temperature', 'top_p']
    sampling = 'temperature'
    temperature = 1.0
    top_p = 1.0
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
        self.stream = self.config.get('stream', self.stream)

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


class ChatgptBatchTranslate:
    """https://cookbook.openai.com/examples/batch_processing"""
    boundary = uuid.uuid4().hex

    def __init__(self, translator):
        self.translator = translator
        self.translator.stream = False

        domain_name = '://'.join(
            urlsplit(self.translator.endpoint, 'https')[:2])
        self.model_endpint = '%s/v1/models' % domain_name
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
        response = request(
            self.model_endpint, headers=self.translator.get_headers())
        return [item['id'] for item in json.loads(response).get('data')]

    def headers(self, extra_headers={}):
        headers = self.translator.get_headers()
        headers.update(extra_headers)
        return headers

    def upload(self, paragraphs):
        # time.sleep(2)
        # return 'test-file-id'

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
        response = request(self.file_endpoint, body, headers, 'POST')
        return json.loads(response).get('id')

    def delete(self, file_id):
        # time.sleep(2)
        # return True

        headers = self.translator.get_headers()
        del headers['Content-Type']
        response = request(
            '%s/%s' % (self.file_endpoint, file_id), headers=headers,
            method='DELETE')
        return json.loads(response).get('deleted')

    def retrieve(self, output_file_id):
        # time.sleep(2)
        # return {
        #     '0ac5d998596c8a7b0517be70784654e8': 'AAAA',
        #     'f3994e8e7c2ce9be789811df77f721de': 'BBBB',
        #     'de03c04fb55cb9fbc24f6acbf4847ce7': 'CCCC',
        # }

        headers = self.translator.get_headers()
        del headers['Content-Type']
        response = request(
            '%s/%s/content' % (self.file_endpoint, output_file_id),
            headers=headers, raw_object=True)
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
        # time.sleep(2)
        # return 'test-batch-id'

        headers = self.translator.get_headers()
        body = json.dumps({
            'input_file_id': file_id,
            'endpoint': '/v1/chat/completions',
            'completion_window': '24h'})
        response = request(self.batch_endpoint, body, headers, 'POST')
        return json.loads(response).get('id')

    def check(self, batch_id):
        # time.sleep(2)
        # return {
        #     'status': 'failed',
        #     'output_file_id': 'xxxx',
        #     'errors': {
        #         'object': 'list',
        #         'data': [
        #             {
        #                 'code': 'error-code',
        #                 'message': 'error-message',
        #                 'param': 'error-param',
        #                 'line': 'error-line',
        #             }
        #         ]
        #     },
        # }
        # return {
        #     'status': 'completed',
        #     'output_file_id': 'xxxx',
        #     'request_counts': {
        #         'total': 100,
        #         'completed': 95,
        #         'failed': 5
        #     },
        # }

        response = request(
            '%s/%s' % (self.batch_endpoint, batch_id),
            headers=self.translator.get_headers())
        return json.loads(response)

    def cancel(self, batch_id):
        # time.sleep(2)
        # return True

        headers = self.translator.get_headers()
        response = request(
            '%s/%s/cancel' % (self.batch_endpoint, batch_id),
            headers=headers, method='POST')
        return json.loads(response).get('status') in (
            'cancelling', 'cancelled')
