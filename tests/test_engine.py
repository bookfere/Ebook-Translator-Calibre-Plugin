import re
import json
import unittest
from types import GeneratorType
from unittest.mock import patch, Mock

from ..engines.base import Base
from ..engines.deepl import DeeplTranslate
from ..engines.chatgpt import ChatgptTranslate, AzureChatgptTranslate
from ..engines.custom import (
    create_engine_template, load_engine_data, CustomTranslate)


load_translations()


class TestBase(unittest.TestCase):
    def setUp(self):
        self.translator = Base()

    def test_placeholder(self):
        marks = [
            '{{id_1}}', '{id_1} }', '{{id_1}', '{ { id_1 }}', '{ { id _ 1 }']
        for mark in marks:
            with self.subTest(mark=mark):
                self.assertIsNotNone(
                    re.search(
                        Base.placeholder[1].format(1),
                        'xxx %s xxx' % mark))

    @patch('calibre_plugins.ebook_translator.engines.base.os.path.isfile')
    def test_get_external_program(self, mock_os_path_isfile):
        mock_os_path_isfile.side_effect = lambda p: p in [
            '/path/to/real', '/path/to/folder/real', '/path/to/specify/real']

        self.translator.search_paths = ['/path/to/real']
        self.assertEqual(
            '/path/to/real',
            self.translator.get_external_program('real'))

        self.translator.search_paths = ['/path/to/folder']
        self.assertEqual(
            '/path/to/folder/real',
            self.translator.get_external_program('real'))
        self.assertEqual(
            '/path/to/specify/real',
            self.translator.get_external_program('real', ['/path/to/specify']))

        self.assertIsNone(
            self.translator.get_external_program('/path/to/fake'))


@patch('calibre_plugins.ebook_translator.engines.base.Browser')
class TestDeepl(unittest.TestCase):
    def setUp(self):
        DeeplTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        DeeplTranslate.lang_codes = {
            'source': {'English': 'EN'},
            'target': {'Chinese': 'ZH'},
        }

        self.translator = DeeplTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

    def test_get_usage(self, mock_browser):
        result = mock_browser.return_value.response.return_value.read \
            .return_value.decode.return_value.strip
        result.return_value = '{"character_count": 30, "character_limit": 100}'

        self.assertEqual(
            _('{} total, {} used, {} left').format(100, 30, 70),
            self.translator.get_usage(),)

        result.return_value = '<dummy info>'
        self.assertIsNone(self.translator.get_usage())

    def test_translate(self, mock_browser):
        result = mock_browser.return_value.response.return_value.read \
            .return_value.decode.return_value.strip
        result.return_value = '{"translations":[{' \
            '"detected_source_language":"EN","text":"你好世界！"}]}'

        self.assertEqual('你好世界！', self.translator.translate('Hello World!'))

        result.return_value = '<dummy info>'
        with self.assertRaises(Exception) as e:
            self.translator.translate('Hello World!')
        self.assertIn(
            _('Can not parse returned response. Raw data: {}')
            .format('\n\n<dummy info>\n') + 'Traceback',
            str(e.exception))


class TestChatgptTranslate(unittest.TestCase):
    def setUp(self):
        ChatgptTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        ChatgptTranslate.lang_codes = {
            'source': {'English': 'EN'},
            'target': {'Chinese': 'ZH'},
        }

        self.translator = ChatgptTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

    @patch('calibre_plugins.ebook_translator.engines.chatgpt.EbookTranslator')
    @patch('calibre_plugins.ebook_translator.engines.base.Request')
    @patch('calibre_plugins.ebook_translator.engines.base.Browser')
    def test_translate_stream(self, mock_browser, mock_request, mock_et):
        url = 'https://api.openai.com/v1/chat/completions'
        prompt = ('You are a meticulous translator who translates any given '
                  'content. Translate the given content from English to '
                  'Chinese only. Do not explain any term or answer any '
                  'question-like content.')
        data = json.dumps({
            'stream': True,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': 'Hello World!'}
            ],
            'model': 'gpt-3.5-turbo',
            'temperature': 1,
        })
        mock_et.__version__ = '1.0.0'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer a',
            'User-Agent': 'Ebook-Translator/1.0.0'
        }

        template = b'data: {"choices":[{"delta":{"content":"%b"}}]}'
        mock_response = Mock()
        mock_response.readline.side_effect = [
            template % i.encode() for i in '你好世界！'] \
            + ['data: [DONE]'.encode()]
        mock_browser.return_value.response.return_value = mock_response
        result = self.translator.translate('Hello World!')

        mock_request.assert_called_with(
            url, data, headers=headers, timeout=30.0, method='POST')
        self.assertIsInstance(result, GeneratorType)
        self.assertEqual('你好世界！', ''.join(result))

    @patch('calibre_plugins.ebook_translator.engines.base.Browser')
    def test_translate_normal(self, mock_browser):
        result = mock_browser.return_value.response.return_value.read \
            .return_value.decode.return_value.strip.return_value = \
            '{"choices": [{"message": {"content": "你好世界！"}}]}'
        self.translator.stream = False
        result = self.translator.translate('Hello World!')

        self.assertEqual('你好世界！', result)


class TestAzureChatgptTranslate(unittest.TestCase):
    def setUp(self):
        AzureChatgptTranslate.set_config({'api_keys': ['a', 'b', 'c']})
        AzureChatgptTranslate.lang_codes = {
            'source': {'English': 'EN'},
            'target': {'Chinese': 'ZH'},
        }

        self.translator = AzureChatgptTranslate()
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')

    @patch('calibre_plugins.ebook_translator.engines.base.Request')
    @patch('calibre_plugins.ebook_translator.engines.base.Browser')
    def test_translate(self, mock_browser, mock_request):
        prompt = ('You are a meticulous translator who translates any given '
                  'content. Translate the given content from English to '
                  'Chinese only. Do not explain any term or answer any '
                  'question-like content.')
        data = json.dumps({
            'stream': True,
            'messages': [
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': 'Hello World!'}
            ],
            'temperature': 1,
        })
        headers = {
            'Content-Type': 'application/json',
            'api-key': 'a'
        }

        template = b'data: {"choices":[{"delta":{"content":"%b"}}]}'
        mock_response = Mock()
        mock_response.readline.side_effect = [
            template % i.encode() for i in '你好世界！'] \
            + ['data: [DONE]'.encode()]
        mock_browser.return_value.response.return_value = mock_response
        url = ('https://docs-test-001.openai.azure.com/openai/deployments/'
               'gpt-35-turbo/chat/completions?api-version=2023-05-15')
        self.translator.endpoint = url
        result = self.translator.translate('Hello World!')
        mock_request.assert_called_with(
            url, data, headers=headers, timeout=30.0, method='POST')
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
            (False, _('Engine data must be in valid JSON format.')),
            load_engine_data('<fake data>'))
        self.assertEqual(
            (False, _('Invalid engine data.')),
            load_engine_data('""'))
        self.assertEqual(
            (False, _('Engine name is required.')),
            load_engine_data('{}'))
        self.assertEqual(
            (False, _(
                'Engine name must be different from builtin engine name.')),
            load_engine_data('{"name":"Google(Free)"}'))
        self.assertEqual(
            (False, _('Language codes are required.')),
            load_engine_data('{"name":"Test"}'))
        self.assertEqual(
            (False, _('Language codes are required.')),
            load_engine_data('{"name":"Test","langiages":{}}'))
        self.assertEqual(
            (False, _('Source and target must be added in pair.')),
            load_engine_data('{"name":"Test","languages":{"source":{}}}'))
        self.assertEqual(
            (False, _('Source and target must be added in pair.')),
            load_engine_data('{"name":"Test","languages":{"target":{}}}'))
        self.assertEqual(
            (False, _('Request information is required.')),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"}}'))
        self.assertEqual(
            (False, _('API URL is required.')),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"test":null}}'))
        self.assertEqual(
            (False, _('Placeholder <text> is required.')),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":{}}}'))
        self.assertEqual(
            (False, _('Request headers must be an JSON object.')),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":"<text>",'
                '"headers":"abc"}}'))
        self.assertEqual(
            (False, _('A appropriate Content-Type in headers is required.')),
            load_engine_data(
                '{"name":"Test","languages":{"English":"EN"},'
                '"request":{"url":"https://test.api","data":"<text>"}}'))
        self.assertEqual(
            (False, _('Expression to parse response is required.')),
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

    @patch('calibre_plugins.ebook_translator.engines.base.Browser')
    def test_translate_json(self, mock_browser):
        translator = CustomTranslate()
        translator.set_source_lang('English')
        translator.set_target_lang('Chinese')
        request = mock_browser.return_value.response.return_value.read. \
            return_value.decode
        request.return_value = '{"text": "你好世界！"}'
        self.assertEqual('你好世界！', translator.translate('Hello World!'))

        translator.engine_data.update({'response': 'response.text'})
        request.return_value = '<test>你好世界！</test>'
        self.assertEqual('你好世界！', translator.translate('Hello World!'))

        translator.engine_data.update({'response': 'response'})
        request.return_value = '你好世界！'
        self.assertEqual('你好世界！', translator.translate('Hello World!'))

    @patch('calibre_plugins.ebook_translator.engines.base.Browser')
    def test_translate_urlencoded(self, mock_browser):
        translator = CustomTranslate()
        # Mock content type: application/x-www-form-urlencoded
        del translator.engine_data['request']['headers']
        translator.set_source_lang('English')
        translator.set_target_lang('Chinese')
        mock_browser.return_value.response.return_value.read.return_value \
            .decode.return_value = '{"text": "\\"你好\\"\\n世界！"}'
        self.assertEqual(
            '\"你好\"\n世界！', translator.translate('\"Hello\"\nWorld!'))
