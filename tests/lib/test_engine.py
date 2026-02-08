import io
import re
import json
import unittest
from pathlib import Path
from types import GeneratorType
from unittest.mock import patch, Mock

from mechanize import HTTPError  # type: ignore
from mechanize._response import (  # type: ignore
    closeable_response as mechanize_response)

from ...lib.cache import Paragraph
from ...engines.base import Base
from ...lib.exception import UnexpectedResult, UnsupportedModel
from ...engines.genai import GenAI
from ...engines.deepl import DeeplTranslate
from ...engines.openai import ChatgptTranslate, ChatgptBatchTranslate
from ...engines.microsoft import AzureChatgptTranslate
from ...engines.anthropic import ClaudeTranslate
from ...engines.custom import (
    create_engine_template, load_engine_data, CustomTranslate)


module_name = 'calibre_plugins.ebook_translator.engines'


class MockEngine(Base):
    endpoint = 'https://example.com/api'

    def get_headers(self):
        return {
            'Authorization': 'Bearer a', 'Content-Type': 'application/json'}

    def get_body(self, text):
        return json.dumps({'text': text})


class TestBase(unittest.TestCase):
    def setUp(self):
        self.translator = MockEngine()

    def test_class(self):
        self.assertIsNone(Base.name)
        self.assertIsNone(Base.alias)
        self.assertFalse(Base.free)

        self.assertEqual({}, Base.lang_codes)
        self.assertEqual({}, Base.config)
        self.assertIsNone(Base.endpoint)
        self.assertEqual('POST', Base.method)
        self.assertFalse(Base.stream)

        self.assertTrue(Base.need_api_key)
        self.assertEqual('API Keys', Base.api_key_hint)
        self.assertEqual(r'^[^\s]+$', Base.api_key_pattern)
        self.assertEqual(['401'], Base.api_key_errors)
        self.assertEqual('\n\n', Base.separator)
        self.assertEqual(
            ('{{{{id_{}}}}}', r'({{\s*)+id\s*_\s*{}\s*(\s*}})+'),
            Base.placeholder)
        self.assertIsNone(Base.using_tip)

        self.assertEqual(0, Base.concurrency_limit)
        self.assertEqual(0.0, Base.request_interval)
        self.assertEqual(3, Base.request_attempt)
        self.assertEqual(10.0, Base.request_timeout)
        self.assertEqual(10, Base.max_error_count)

    @patch.dict(Base.config, {
        'api_keys': ['a', 'b', 'c'],
        'concurrency_limit': 5,
        'request_interval': 10,
        'request_attempt': 3,
        'request_timeout': 10,
        'max_error_count': 20})
    def test_create_translator(self):
        translator = Base()

        # self.assertIsNone(translator.source_lang)
        # self.assertIsNone(translator.target_lang)
        self.assertEqual([], translator.search_paths)

        self.assertIsNone(translator.proxy_type)
        self.assertIsNone(translator.proxy_host)
        self.assertIsNone(translator.proxy_port)

        self.assertFalse(translator.merge_enabled)
        self.assertEqual(['b', 'c'], translator.api_keys)
        self.assertEqual([], translator.bad_api_keys)
        self.assertEqual('a', translator.api_key)

        self.assertEqual(5, translator.concurrency_limit)
        self.assertEqual(10, translator.request_interval)
        self.assertEqual(3, translator.request_attempt)
        self.assertEqual(10, translator.request_timeout)
        self.assertEqual(20, translator.max_error_count)

    def test_placeholder(self):
        marks = [
            '{{id_1}}', '{id_1} }', '{{id_1}', '{ { id_1 }}', '{ { id _ 1 }']
        for mark in marks:
            with self.subTest(mark=mark):
                self.assertIsNotNone(re.search(
                    Base.placeholder[1].format(1), 'xxx %s xxx' % mark))

    def test_get_api_key_no_need_api_key(self):
        self.translator.need_api_key = False
        self.assertIsNone(self.translator.get_api_key())

    def test_get_api_key_with_empty_keys(self):
        self.translator.need_api_key = True
        self.translator.api_keys = []
        self.assertIsNone(self.translator.get_api_key())

    def test_get_api_key(self):
        self.translator.need_api_key = True
        self.translator.api_keys = ['a', 'b']
        self.assertEqual('a', self.translator.get_api_key())

    def test_swap_api_key_in_bad_keys(self):
        self.translator.api_key = 'a'
        self.translator.bad_api_keys = []
        self.assertFalse(self.translator.swap_api_key())

    def test_swap_api_key_with_none_new_api_key(self):
        self.translator.api_key = 'a'
        self.translator.bad_api_keys = []

        with patch.object(self.translator, 'get_api_key') as mock_get_api_key:
            mock_get_api_key.return_value = None
            self.assertFalse(self.translator.swap_api_key())

        self.assertEqual(['a'], self.translator.bad_api_keys)
        self.assertEqual(None, self.translator.api_key)

    def test_swap_api_key(self):
        self.translator.api_key = 'a'
        self.translator.bad_api_keys = []

        with patch.object(self.translator, 'get_api_key') as mock_get_api_key:
            mock_get_api_key.return_value = 'b'
            self.assertTrue(self.translator.swap_api_key())

        self.assertEqual(['a'], self.translator.bad_api_keys)
        self.assertEqual('b', self.translator.api_key)

    def test_need_swap_api_key_no_need_api_key(self):
        self.translator.need_api_key = False
        self.assertFalse(self.translator.need_swap_api_key('test error'))

    def test_need_swap_api_key_with_empty_keys(self):
        self.translator.need_api_key = True
        self.translator.api_keys = []
        self.assertFalse(self.translator.need_swap_api_key('test error'))

    def test_need_swap_api_key_without_key_errors(self):
        self.translator.need_api_key = True
        self.translator.api_keys = ['a']
        self.translator.api_key_errors = []
        self.assertFalse(self.translator.need_swap_api_key('test error'))

    def test_need_swap_api_key(self):
        self.translator.need_api_key = True
        self.translator.api_keys = ['a']
        self.translator.api_key_errors = ['error']
        self.assertTrue(self.translator.need_swap_api_key('test error'))

    @patch(module_name + '.base.os.path.isfile')
    def test_get_external_program(self, mock_os_path_isfile):
        mock_os_path_isfile.side_effect = lambda path: path in [
            str(Path('/path/to/real')), str(Path('/path/to/folder/real')),
            str(Path('/path/to/specify/real'))]

        self.translator.search_paths = [str(Path('/path/to/real'))]
        self.assertEqual(
            str(Path('/path/to/real')),
            self.translator.get_external_program('real'))

        self.translator.search_paths = [str(Path('/path/to/folder'))]
        self.assertEqual(
            str(Path('/path/to/folder/real')),
            self.translator.get_external_program('real'))
        self.assertEqual(
            str(Path('/path/to/specify/real')),
            self.translator.get_external_program(
                'real', [str(Path('/path/to/specify'))]))

        self.assertIsNone(
            self.translator.get_external_program(str(Path('/path/to/fake'))))

    @patch(module_name + '.base.request')
    def test_translate(self, mock_request):
        self.translator.stream = False
        mock_request.return_value = '{"text": "你好世界"}'

        self.assertEqual(
            '{"text": "你好世界"}', self.translator.translate('Hello World'))

        mock_request.assert_called_once_with(
            url='https://example.com/api', data='{"text": "Hello World"}',
            headers={
                'Authorization': 'Bearer a', 'Content-Type': 'application/json'
            }, method='POST', timeout=10.0, proxy_uri=None, raw_object=False)

    @patch(module_name + '.base.request')
    def test_translate_with_stream(self, mock_request):
        self.translator.stream = True
        mock_response = Mock(mechanize_response)
        mock_request.return_value = mock_response

        self.assertIs(mock_response, self.translator.translate('Hello World'))

        mock_request.assert_called_once_with(
            url='https://example.com/api', data='{"text": "Hello World"}',
            headers={
                'Authorization': 'Bearer a', 'Content-Type': 'application/json'
            }, method='POST', timeout=10.0, proxy_uri=None, raw_object=True)

    @patch(module_name + '.base.request')
    def test_translate_with_http_error(self, mock_request):
        mock_request.side_effect = Exception(
            'HTTP Error 409: Too many requests\n\n{"error": "any error"}')

        with self.assertRaises(Exception) as cm:
            self.translator.translate('Hello World')
        self.assertRegex(
            str(cm.exception), 'HTTP Error 409: Too many requests')
        self.assertRegex(str(cm.exception), '{"error": "any error"}')

    @patch(module_name + '.base.request')
    def test_translate_with_http_stream_parse_error(self, mock_request):
        self.translator.stream = True
        mock_response = Mock(mechanize_response)
        mock_request.return_value = mock_response

        with patch.object(self.translator, 'get_result') as mock_get_result:
            with self.assertRaises(Exception) as cm:
                mock_get_result.side_effect = Exception('test parse error')
                self.translator.translate('Hello World')
            self.assertRegex(str(cm.exception), 'test parse error')

    @patch(module_name + '.base.request')
    def test_translate_with_http_parse_error(self, mock_request):
        self.translator.stream = False
        mock_request.return_value = 'any unexpected result'

        with patch.object(self.translator, 'get_result') as mock_get_result:
            with self.assertRaises(Exception) as cm:
                mock_get_result.side_effect = Exception('test parse error')
                self.translator.translate('Hello World')
            self.assertRegex(
                str(cm.exception), 'test parse error\n\nany unexpected result')

    @patch(module_name + '.base.Base.need_swap_api_key')
    @patch(module_name + '.base.request')
    def test_translate_no_need_swap_api_keys(
            self, mock_request, mock_need_swap_api_key):
        mock_request.side_effect = Exception
        mock_need_swap_api_key.return_value = False

        self.assertRaises(
            UnexpectedResult, self.translator.translate, 'Hello World')
        self.assertEqual(1, mock_request.call_count)

    @patch(module_name + '.base.Base.swap_api_key')
    @patch(module_name + '.base.Base.need_swap_api_key')
    @patch(module_name + '.base.request')
    def test_translate_swap_api_keys_when_unavailable(
            self, mock_request, mock_need_swap_api_key, mock_swap_api_key):
        mock_request.side_effect = Exception
        mock_need_swap_api_key.return_value = True
        mock_swap_api_key.return_value = False

        self.assertRaises(
            UnexpectedResult, self.translator.translate, 'Hello World')
        self.assertEqual(1, mock_request.call_count)

    @patch(module_name + '.base.Base.swap_api_key')
    @patch(module_name + '.base.Base.need_swap_api_key')
    @patch(module_name + '.base.request')
    def test_translate_swap_api_keys_with_http_error(
            self, mock_request, mock_need_swap_api_key, mock_swap_api_key):
        self.translator.stream = True
        mock_response = Mock(mechanize_response)
        mock_request.side_effect = [HTTPError, HTTPError, mock_response]
        mock_need_swap_api_key.return_value = True
        mock_swap_api_key.return_value = True

        self.assertIs(mock_response, self.translator.translate('Hello World'))
        self.assertEqual(3, mock_request.call_count)

    @patch(module_name + '.base.Base.swap_api_key')
    @patch(module_name + '.base.Base.need_swap_api_key')
    @patch(module_name + '.base.request')
    def test_translate_swap_api_keys_with_http_error_without_result(
            self, mock_request, mock_need_swap_api_key, mock_swap_api_key):
        mock_request.side_effect = HTTPError(
            'https://example.com/api', 409, 'Too many requests', {},
            io.BytesIO(b'{"error": "any error"}'))
        mock_need_swap_api_key.side_effect = [True, True, False]

        self.assertRaises(
            UnexpectedResult, self.translator.translate, 'Hello World')

        self.assertEqual(3, mock_request.call_count)
        calls = mock_need_swap_api_key.mock_calls
        self.assertRegex(calls[0].args[0], 'Too many requests')
        self.assertRegex(calls[1].args[0], 'Too many requests')
        self.assertRegex(calls[2].args[0], 'Too many requests')

    @patch(module_name + '.base.Base.swap_api_key')
    @patch(module_name + '.base.Base.need_swap_api_key')
    @patch(module_name + '.base.Base.get_result')
    @patch(module_name + '.base.request')
    def test_translate_swap_api_keys_with_parse_error(
            self, mock_request, mock_get_result, mock_need_swap_api_key,
            mock_swap_api_key):
        self.translator.stream = True
        mock_get_result.side_effect = [Exception, Exception, '你好世界']
        mock_need_swap_api_key.return_value = True
        mock_swap_api_key.return_value = True

        self.assertEqual('你好世界', self.translator.translate('Hello World'))
        self.assertEqual(3, mock_request.call_count)

    @patch(module_name + '.base.Base.swap_api_key')
    @patch(module_name + '.base.Base.need_swap_api_key')
    @patch(module_name + '.base.Base.get_result')
    @patch(module_name + '.base.request')
    def test_translate_swap_api_keys_with_parse_error_without_result(
            self, mock_request, mock_get_result, mock_need_swap_api_key,
            mock_swap_api_key):
        self.translator.stream = True
        mock_get_result.side_effect = Exception('any unexpected error')
        mock_need_swap_api_key.side_effect = [True, True, False]

        self.assertRaises(
            UnexpectedResult, self.translator.translate, 'Hello World')

        self.assertEqual(3, mock_request.call_count)
        calls = mock_need_swap_api_key.mock_calls
        self.assertRegex(calls[0].args[0], 'any unexpected error')
        self.assertRegex(calls[1].args[0], 'any unexpected error')
        self.assertRegex(calls[2].args[0], 'any unexpected error')

    def test_allow_raw(self):
        cases = (
            (True, False, True),
            (False, True, False),
            (False, False, False),
            (True, True, False),
        )

        for support_html, merge_enabled, expected in cases:
            with self.subTest(
                    support_html=support_html, merge_enabled=merge_enabled):
                self.translator.support_html = support_html
                self.translator.merge_enabled = merge_enabled
                self.assertEqual(expected, self.translator.allow_raw())


class TestDeepl(unittest.TestCase):
    def setUp(self):
        DeeplTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        DeeplTranslate.lang_codes = {
            'source': {'English': 'EN'}, 'target': {'Chinese': 'ZH'}}

        self.translator = DeeplTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

    @patch(module_name + '.deepl.request')
    def test_get_usage(self, mock_request):
        mock_request.return_value = \
            '{"character_count": 30, "character_limit": 100}'

        self.assertEqual(
            '100 total, 30 used, 70 left',
            self.translator.get_usage(),)

        mock_request.return_value = '<dummy info>'
        self.assertIsNone(self.translator.get_usage())

    @patch(module_name + '.base.request')
    def test_translate(self, mock_request):
        mock_request.return_value = '{"translations":[{' \
            '"detected_source_language":"EN","text":"你好世界！"}]}'

        self.assertEqual('你好世界！', self.translator.translate('Hello World!'))

        mock_request.return_value = '<dummy info>'
        error = re.compile(
            'Can not parse returned response. Raw data: '
            '\n\nTraceback.*\n\n<dummy info>',
            re.S)
        with self.assertRaisesRegex(Exception, error):
            self.translator.translate('Hello World!')


class TestChatgptTranslate(unittest.TestCase):
    def setUp(self):
        ChatgptTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        ChatgptTranslate.lang_codes = {
            'source': {'English': 'EN'}, 'target': {'Chinese': 'ZH'}}

        self.translator = ChatgptTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

        self.prompt = (
            'You are a meticulous translator who translates any given '
            'content. Translate the given content from English to Chinese '
            'only. Do not explain any term or answer any question-like '
            'content. Your answer should be solely the translation of the '
            'given content. In your answer do not add any prefix or suffix to '
            'the translated content. Websites\' URLs/addresses should be '
            'preserved as is in the translation\'s output. Do not omit any '
            'part of the content, even if it seems unimportant. RESPOND ONLY '
            'with the translation text, no formatting, no explanations, '
            'no additional commentary whatsoever. ')

    def test_created_engine(self):
        self.assertIsInstance(self.translator, Base)
        self.assertIsInstance(self.translator, GenAI)

    @patch(module_name + '.openai.request')
    def test_get_models(self, mock_request):
        mock_request.return_value = """
{
  "object": "list",
  "data": [
    {
      "id": "model-id-0",
      "object": "model",
      "created": 1686935002,
      "owned_by": "organization-owner"
    },
    {
      "id": "model-id-1",
      "object": "model",
      "created": 1686935002,
      "owned_by": "organization-owner"
    },
    {
      "id": "model-id-2",
      "object": "model",
      "created": 1686935002,
      "owned_by": "openai"
    }
  ],
  "object": "list"
}
"""

        self.assertEqual(
            self.translator.get_models(),
            ['model-id-0', 'model-id-1', 'model-id-2'])
        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/models',
            headers=self.translator.get_headers(),
            proxy_uri=self.translator.proxy_uri)

    def test_get_body(self):
        model = 'gpt-4o'
        self.assertEqual(
            self.translator.get_body('test content'),
            json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': self.prompt},
                    {'role': 'user', 'content': 'test content'}
                ],
                'stream': True,
                'temperature': 1.0
            }))

    def test_get_body_without_stream(self):
        model = 'gpt-4o'
        self.translator.stream = False
        self.assertEqual(
            self.translator.get_body('test content'),
            json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': self.prompt},
                    {'role': 'user', 'content': 'test content'}
                ],
                'temperature': 1.0
            }))

    @patch(module_name + '.openai.EbookTranslator')
    @patch(module_name + '.base.request')
    def test_translate_stream(self, mock_request, mock_et):
        model = 'gpt-4o'
        data = json.dumps({
            'model': model,
            'messages': [
                {'role': 'system', 'content': self.prompt},
                {'role': 'user', 'content': 'Hello World!'}
            ],
            'stream': True,
            'temperature': 1.0,
        })
        mock_et.__version__ = '1.0.0'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer a',
            'User-Agent': 'Ebook-Translator/1.0.0'}
        template = b'data: {"choices":[{"delta":{"content":"%b"}}]}'
        mock_response = Mock()
        mock_response.readline.side_effect = [
            template % i.encode() for i in '你好世界！'] \
            + ['data: [DONE]'.encode()]
        mock_request.return_value = mock_response
        url = 'https://api.openai.com/v1/chat/completions'
        result = self.translator.translate('Hello World!')

        mock_request.assert_called_with(
            url=url, data=data, headers=headers, method='POST', timeout=60.0,
            proxy_uri=None, raw_object=True)
        self.assertIsInstance(result, GeneratorType)
        self.assertEqual('你好世界！', ''.join(result))

    @patch(module_name + '.base.request')
    def test_translate_normal(self, mock_request):
        mock_request.return_value = \
            '{"choices": [{"message": {"content": "你好世界！"}}]}'
        self.translator.stream = False
        result = self.translator.translate('Hello World!')

        self.assertEqual('你好世界！', result)


class TestChatgptBatchTranslate(unittest.TestCase):
    def setUp(self):
        self.mock_translator = Mock(ChatgptTranslate)
        self.mock_translator.endpoint = 'https://api.openai.com/test'
        self.mock_translator.proxy_uri = {}
        self.mock_headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer abc',
            'User-Agent': 'Ebook-Translator/v1.0.0'}
        self.mock_translator.get_headers.return_value = self.mock_headers
        self.batch_translator = ChatgptBatchTranslate(self.mock_translator)

    def test_class_object(self):
        self.assertRegex(ChatgptBatchTranslate.boundary, r'(?a)^\w+$')

    def test_created_translator(self):
        self.assertIsInstance(self.batch_translator, ChatgptBatchTranslate)
        self.assertIs(self.mock_translator, self.batch_translator.translator)
        self.assertFalse(self.mock_translator.stream)
        self.assertEqual(
            self.batch_translator.file_endpoint,
            'https://api.openai.com/v1/files')
        self.assertEqual(
            self.batch_translator.batch_endpoint,
            'https://api.openai.com/v1/batches')

    def test_supported_models(self):
        self.mock_translator.get_models.return_value = [
            'model-id-0', 'model-id-1', 'model-id-2']
        self.assertEqual(
            self.batch_translator.supported_models(),
            ['model-id-0', 'model-id-1', 'model-id-2'])

    @patch(module_name + '.openai.ChatgptBatchTranslate.supported_models')
    def test_upload_with_unsupported_model(self, mock_supported_models):
        model = 'gpt-4o'
        mock_supported_models.return_value = [model]
        self.mock_translator.model = 'fake-model'
        self.mock_translator.stream = True
        with self.assertRaises(UnsupportedModel) as cm:
            self.batch_translator.upload([Mock(Paragraph)])
        self.assertEqual(
            str(cm.exception),
            'The model "fake-model" does not support batch functionality.')

    @patch.object(ChatgptBatchTranslate, 'boundary', new='xxxxxxxxxx')
    @patch(module_name + '.openai.ChatgptBatchTranslate.supported_models')
    @patch(module_name + '.openai.request')
    def test_upload(self, mock_request, mock_supported_models):
        mock_request.return_value = """
{
  "id": "test-file-id",
  "object": "file",
  "bytes": 120000,
  "created_at": 1677610602,
  "filename": "mydata.jsonl",
  "purpose": "fine-tune"
}
"""
        model = 'gpt-4o'
        mock_supported_models.return_value = [model]

        mock_paragraph_1 = Mock(Paragraph)
        mock_paragraph_1.md5 = 'abc'
        mock_paragraph_1.original = 'test content 1'
        mock_paragraph_2 = Mock(Paragraph)
        mock_paragraph_2.md5 = 'def'
        mock_paragraph_2.original = 'test content 2'
        self.mock_translator.model = model
        self.mock_translator.api_key = 'abc'
        self.mock_translator.proxy_uri = {}

        def mock_get_body(text):
            return json.dumps({
                'model': model,
                'messages': [
                    {'role': 'system', 'content': 'some prompt...'},
                    {'role': 'user', 'content': text}],
                'temperature': 1.0
            })
        self.mock_translator.get_body.side_effect = mock_get_body

        file_id = self.batch_translator.upload(
            [mock_paragraph_1, mock_paragraph_2])

        self.assertEqual(file_id, 'test-file-id')
        mock_body = (
            '--xxxxxxxxxx\r\n'
            'Content-Disposition: form-data; name="purpose"\r\n'
            '\r\nbatch\r\n'
            '--xxxxxxxxxx\r\n'
            'Content-Disposition: form-data; name="file"; '
            'filename="original.jsonl"\r\n'
            'Content-Type: application/json\r\n'
            '\r\n{"custom_id": "abc", "method": "POST", '
            '"url": "/v1/chat/completions", '
            '"body": {"model": "' + model + '", '
            '"messages": [{"role": "system", '
            '"content": "some prompt..."}, {"role": "user", '
            '"content": "test content 1"}], "temperature": 1.0}}\n'
            '{"custom_id": "def", "method": "POST", '
            '"url": "/v1/chat/completions", '
            '"body": {"model": "' + model + '", '
            '"messages": [{"role": "system", '
            '"content": "some prompt..."}, {"role": "user", '
            '"content": "test content 2"}], "temperature": 1.0}}\r\n'
            '--xxxxxxxxxx--').encode()
        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/files', mock_body, self.mock_headers,
            'POST', proxy_uri=self.mock_translator.proxy_uri)

    @patch(module_name + '.openai.request')
    def test_delete(self, mock_request):
        mock_request.return_value = json.dumps({
            'id': 'test-file-id',
            'object': 'file',
            'deleted': True})

        self.assertTrue(self.batch_translator.delete('test-file-id'))

        headers = {
            'Authorization': 'Bearer abc',
            'User-Agent': 'Ebook-Translator/v1.0.0'}
        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/files/test-file-id',
            headers=headers, method='DELETE',
            proxy_uri=self.mock_translator.proxy_uri)

    @patch(module_name + '.openai.request')
    def test_retrieve(self, mock_request):
        line_1 = (
            b'{"custom_id":"abc","response":{"status_code":200,"body":{'
            b'"choices": [{"message": {"content": "A"}}]}}}')
        line_2 = (
            b'{"custom_id":"def","response":{"status_code":200,"body":{'
            b'"choices": [{"message": {"content": "B"}}]}}}')
        mock_request.return_value.read.return_value = line_1 + b'\n' + line_2
        self.mock_translator.get_headers.return_value = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer abc',
            'User-Agent': 'Ebook-Translator/v1.0.0'}

        self.assertEqual(
            self.batch_translator.retrieve('test-batch-id'),
            {'abc': 'A', 'def': 'B'})

        headers = {
            'Authorization': 'Bearer abc',
            'User-Agent': 'Ebook-Translator/v1.0.0'}
        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/files/test-batch-id/content',
            headers=headers, raw_object=True,
            proxy_uri=self.mock_translator.proxy_uri)
        mock_request().read.assert_called_once()

    @patch(module_name + '.openai.request')
    def test_create(self, mock_request):
        mock_response = {
            'id': 'test-batch-id',
            'object': 'batch',
            'endpoint': '/v1/chat/completions',
            'errors': None,
            'input_file_id': 'test-file-id',
            'completion_window': '24h',
            'status': 'validating',
            'output_file_id': None,
            'error_file_id': None,
            'created_at': 1711471533,
            'in_progress_at': None,
            'expires_at': None,
            'finalizing_at': None,
            'completed_at': None,
            'failed_at': None,
            'expired_at': None,
            'cancelling_at': None,
            'cancelled_at': None,
            'request_counts': {
                'total': 0,
                'completed': 0,
                'failed': 0
            },
            'metadata': {
                'customer_id': 'user_123456789',
                'batch_description': 'Nightly eval job'
            }}
        mock_request.return_value = json.dumps(mock_response)

        self.assertEqual(
            self.batch_translator.create('test-file-id'), 'test-batch-id')

        body = json.dumps({
            'input_file_id': 'test-file-id',
            'endpoint': '/v1/chat/completions',
            'completion_window': '24h'})
        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/batches',
            body, self.mock_headers, 'POST',
            proxy_uri=self.mock_translator.proxy_uri)

    @patch(module_name + '.openai.request')
    def test_check(self, mock_request):
        mock_response = {
            'id': 'test-batch-id',
            'object': 'batch',
            'endpoint': '/v1/completions',
            'errors': None,
            'input_file_id': 'file-abc123',
            'completion_window': '24h',
            'status': 'completed',
            'output_file_id': 'file-cvaTdG',
            'error_file_id': 'file-HOWS94',
            'created_at': 1711471533,
            'in_progress_at': 1711471538,
            'expires_at': 1711557933,
            'finalizing_at': 1711493133,
            'completed_at': 1711493163,
            'failed_at': None,
            'expired_at': None,
            'cancelling_at': None,
            'cancelled_at': None,
            'request_counts': {
                'total': 100,
                'completed': 95,
                'failed': 5
            },
            'metadata': {
                'customer_id': 'user_123456789',
                'batch_description': 'Nightly eval job',
            }}
        mock_request.return_value = json.dumps(mock_response)

        self.assertEqual(
            self.batch_translator.check('test-batch-id'), mock_response)

        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/batches/test-batch-id',
            headers=self.mock_headers,
            proxy_uri=self.mock_translator.proxy_uri)

    @patch(module_name + '.openai.request')
    def test_cancel(self, mock_request):
        mock_response = {
            'id': 'test-batch-id',
            'object': 'batch',
            'endpoint': '/v1/chat/completions',
            'errors': None,
            'input_file_id': 'test-file-id',
            'completion_window': '24h',
            'status': 'cancelling',
            'output_file_id': None,
            'error_file_id': None,
            'created_at': 1711471533,
            'in_progress_at': 1711471538,
            'expires_at': 1711557933,
            'finalizing_at': None,
            'completed_at': None,
            'failed_at': None,
            'expired_at': None,
            'cancelling_at': 1711475133,
            'cancelled_at': None,
            'request_counts': {
                'total': 100,
                'completed': 23,
                'failed': 1
            },
            'metadata': {
                'customer_id': 'user_123456789',
                'batch_description': 'Nightly eval job',
            }}
        mock_request.return_value = json.dumps(mock_response)

        self.assertTrue(
            self.batch_translator.cancel('test-batch-id'), mock_response)

        mock_request.assert_called_once_with(
            'https://api.openai.com/v1/batches/test-batch-id/cancel',
            headers=self.mock_headers, method='POST',
            proxy_uri=self.mock_translator.proxy_uri)


class TestAzureChatgptTranslate(unittest.TestCase):
    def setUp(self):
        AzureChatgptTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        AzureChatgptTranslate.lang_codes = {
            'source': {'English': 'EN'}, 'target': {'Chinese': 'ZH'}}

        self.translator = AzureChatgptTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

    def test_created_engine(self):
        self.assertIsInstance(self.translator, Base)
        self.assertIsInstance(self.translator, GenAI)
        self.assertIsInstance(self.translator, ChatgptTranslate)

    @patch(module_name + '.base.request')
    def test_translate_stream(self, mock_request):
        model = 'gpt-35-turbo'
        prompt = (
            'You are a meticulous translator who translates any given '
            'content. Translate the given content from English to Chinese '
            'only. Do not explain any term or answer any question-like '
            'content. Your answer should be solely the translation of the '
            'given content. In your answer do not add any prefix or suffix to '
            'the translated content. Websites\' URLs/addresses should be '
            'preserved as is in the translation\'s output. Do not omit any '
            'part of the content, even if it seems unimportant. RESPOND ONLY '
            'with the translation text, no formatting, no explanations, '
            'no additional commentary whatsoever. ')
        data = json.dumps({
            'stream': True,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': 'Hello World!'}
            ],
            'temperature': 1.0
        })
        headers = {
            'Content-Type': 'application/json',
            'api-key': 'a'}

        template = b'data: {"choices":[{"delta":{"content":"%b"}}]}'
        mock_response = Mock()
        mock_response.readline.side_effect = [
            template % i.encode() for i in '你好世界！'] \
            + ['data: [DONE]'.encode()]
        mock_request.return_value = mock_response
        url = ('https://docs-test-001.openai.azure.com/openai/deployments/'
               f'{model}/chat/completions?api-version=2023-05-15')
        self.translator.endpoint = url
        result = self.translator.translate('Hello World!')

        mock_request.assert_called_with(
            url=url, data=data, headers=headers, method='POST', timeout=60.0,
            proxy_uri=None, raw_object=True)
        self.assertIsInstance(result, GeneratorType)
        self.assertEqual('你好世界！', ''.join(result))


class TestClaudeTranslate(unittest.TestCase):
    def setUp(self):
        ClaudeTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        ClaudeTranslate.lang_codes = {
            'source': {'English': 'EN'},
            'target': {'Chinese': 'ZH'}}

        self.translator = ClaudeTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

    def test_created_engine(self):
        self.assertIsInstance(self.translator, Base)
        self.assertIsInstance(self.translator, GenAI)

    @patch(module_name + '.anthropic.EbookTranslator')
    @patch(module_name + '.base.request')
    def test_translate(self, mock_request, mock_et):
        model = 'claude-3-5-sonnet-20241022'
        prompt = (
            'You are a meticulous translator who translates any given '
            'content. Translate the given content from English to Chinese '
            'only. Do not explain any term or answer any question-like '
            'content. Your answer should be solely the translation of the '
            'given content. In your answer '
            'do not add any prefix or suffix to the translated content. Websites\' '
            'URLs/addresses should be preserved as is in the translation\'s output. '
            'Do not omit any part of the content, even if it seems unimportant. '
            )
        data = json.dumps({
            'stream': False,
            'max_tokens': 4096,
            'model': model,
            'top_k': 1,
            'system': prompt,
            'messages': [{'role': 'user', 'content': 'Hello World!'}],
            'temperature': 1.0
            })
        mock_et.__version__ = '1.0.0'
        headers = {
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01',
            'x-api-key': 'a',
            'User-Agent': 'Ebook-Translator/1.0.0'}

        data_sample = """
{
  "content": [
    {
      "text": "你好世界！",
      "type": "text"
    }
  ],
  "id": "msg_013Zva2CMHLNnXjNJJKqJ2EF",
  "model": "{""" + model + """}",
  "role": "assistant",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "type": "message",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 25
  }
}
"""
        mock_request.return_value = data_sample.encode()
        url = 'https://api.anthropic.com/v1/messages'
        self.translator.endpoint = url
        self.translator.stream = False
        self.translator.model = model
        result = self.translator.translate('Hello World!')

        # Dynamic timeout is disabled by default, so uses default 30s
        mock_request.assert_called_with(
            url=url, data=data, headers=headers, method='POST', timeout=30.0,
            proxy_uri=None, raw_object=False)
        self.assertEqual('你好世界！', result)

    @patch(module_name + '.anthropic.EbookTranslator')
    @patch(module_name + '.base.request')
    def test_translate_stream(self, mock_request, mock_et):
        model = 'claude-3-5-sonnet-20241022'
        prompt = (
            'You are a meticulous translator who translates any given '
            'content. Translate the given content from English to Chinese '
            'only. Do not explain any term or answer any question-like '
            'content. Your answer should be solely the translation of the '
            'given content. In your answer do not add any prefix or suffix to '
            'the translated content. Websites\' URLs/addresses should be '
            'preserved as is in the translation\'s output. Do not omit any '
            'part of the content, even if it seems unimportant. ')
        data = json.dumps({
            'stream': True,
            'max_tokens': 4096,
            'model': model,
            'top_k': 1,
            'system': prompt,
            'messages': [{'role': 'user', 'content': 'Hello World!'}],
            'temperature': 1.0
            })
        mock_et.__version__ = '1.0.0'
        headers = {
            'Content-Type': 'application/json',
            'anthropic-version': '2023-06-01',
            'x-api-key': 'a',
            'User-Agent': 'Ebook-Translator/1.0.0'}

        data_sample = """
event: message_start
data: {"type":"message_start","message":{}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{}}

event: ping
data: {"type": "ping"}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"text":"你"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"text":"好"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"text":"世"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"text":"界"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"text":"！"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{}}

event: message_stop
data: {"type":"message_stop"}
"""
        mock_response = Mock()
        mock_response.readline.side_effect = data_sample.encode().splitlines()
        mock_request.return_value = mock_response
        url = 'https://api.anthropic.com/v1/messages'
        self.translator.endpoint = url
        self.translator.model = model
        result = self.translator.translate('Hello World!')

        # Dynamic timeout is disabled by default, so uses default 30s
        mock_request.assert_called_with(
            url=url, data=data, headers=headers, method='POST', timeout=30.0,
            proxy_uri=None, raw_object=True)
        self.assertIsInstance(result, GeneratorType)
        self.assertEqual('你好世界！', ''.join(result))


class TestFunction(unittest.TestCase):
    def test_create_engine_template(self):
        expect = """{
    "name": "New Engine",
    "languages": {
        "source": {
            "Source Language": "code"
        },
        "target": {
            "Target Language": "code"
        }
    },
    "request": {
        "url": "https://example.api",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "data": {
            "source": "<source>",
            "target": "<target>",
            "text": "<text>"
        }
    },
    "response": "response"
}"""

        self.assertEqual(expect, create_engine_template('New Engine'))

    def test_load_engine_data(self):
        self.assertEqual(
            (False, 'Engine data must be in valid JSON format.'),
            load_engine_data('<fake data>'))
        self.assertEqual(
            (False, 'Invalid engine data.'), load_engine_data('""'))
        self.assertEqual(
            (False, 'Engine name is required.'), load_engine_data('{}'))
        self.assertEqual(
            (False, 'Engine name must be different from builtin engine name.'),
            load_engine_data('{"name":"Google(Free)"}'))
        self.assertEqual(
            (False, 'Language codes are required.'),
            load_engine_data('{"name":"Test"}'))
        self.assertEqual(
            (False, 'Language codes are required.'),
            load_engine_data('{"name":"Test","languages":{}}'))
        self.assertEqual(
            (False, 'Source and target must be added in pair.'),
            load_engine_data('{"name":"Test","languages":{"source":{}}}'))
        self.assertEqual(
            (False, 'Source and target must be added in pair.'),
            load_engine_data('{"name":"Test","languages":{"target":{}}}'))
        self.assertEqual(
            (False, 'Request information is required.'),
            load_engine_data('{"name":"Test","languages":{"English":"EN"}}'))
        self.assertEqual(
            (False, 'API URL is required.'), load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"test":null}}'))
        self.assertEqual(
            (False, 'Placeholder <text> is required.'), load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":{}}}'))
        self.assertEqual(
            (False, 'Request headers must be an JSON object.'),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":"<text>",'
                '"headers":"abc"}}'))
        self.assertEqual(
            (False, 'A appropriate Content-Type in headers is required.'),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":"<text>"}}'))
        self.assertEqual(
            (False, 'Expression to parse response is required.'),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":"<text>",'
                '"headers":{"Content-Type":"application/anything"}}}'))
        json_data = (
            '{"name":"Test","languages":{"English":"EN"},'
            '"request":{"url":"https://test.api","data":{"test":"<text>"},'
            '"headers":{"Content-Type":"application/anything"}},'
            '"response":"response"}')
        self.assertEqual(
            (True, json.loads(json_data)), load_engine_data(json_data))


class TestCustom(unittest.TestCase):
    def setUp(self):
        engine_data = """{
    "name": "New Engine",
    "languages": {
        "source": {
            "English": "en"
        },
        "target": {
            "Chinese": "zh"
        }
    },
    "request": {
        "url": "https://example.api",
        "method": "POST",
        "headers": {
            "Content-Type": "application/json"
        },
        "data": {
            "source": "<source>",
            "target": "<target>",
            "text": "<text>"
        }
    },
    "response": "response['text']"
}"""

        engine_data = json.loads(engine_data)
        CustomTranslate.set_engine_data(engine_data)

    @patch(module_name + '.base.request')
    def test_translate(self, mock_request):
        translator = CustomTranslate()
        translator.set_source_lang('English')
        translator.set_target_lang('Chinese')
        # JSON response
        mock_request.return_value = '{"text": "你好世界"}'
        self.assertEqual('你好世界', translator.translate('Hello "World"'))
        mock_request.assert_called_with(
            url='https://example.api', data=b'{"source": "en", "target": "zh",'
            b' "text": "Hello \\"World\\""}',
            headers={'Content-Type': 'application/json'}, method='POST',
            timeout=10.0, proxy_uri=None, raw_object=False)
        # XML response
        translator.response = 'response.text'
        mock_request.return_value = '<test>你好世界</test>'
        self.assertEqual('你好世界', translator.translate('Hello World'))
        # Plain response
        translator.response = 'response'
        mock_request.return_value = '你好世界'
        self.assertEqual('你好世界', translator.translate('Hello World'))

    @patch(module_name + '.base.request')
    def test_translate_urlencoded(self, mock_request):
        translator = CustomTranslate()
        # Mock content type: application/x-www-form-urlencoded
        del translator.request['headers']
        translator.set_source_lang('English')
        translator.set_target_lang('Chinese')
        mock_request.return_value = '{"text": "\\"你好\\"\\n世界"}'
        self.assertEqual(
            '\"你好\"\n世界', translator.translate('\"Hello\"\nWorld'))
