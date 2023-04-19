import json
import unittest
from unittest.mock import MagicMock

from calibre_plugins.ebook_translator.engines.custom import (
    get_engine_template, load_engine_data, CustomTranslate)


load_translations()


class TestCustom(unittest.TestCase):
    def test_get_engine_template(self):
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

        self.assertEqual(expect, get_engine_template('New Engine'))

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
            load_engine_data('{"name":"Google"}'))
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

    def test_custom_translate(self):
        engine_data = """{
    "name": "New Engine",
    "languages": {
        "source": {"English": "en"},
        "target": {"Chinese": "zh"}
    },
    "request": {
        "url": "https://example.api",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
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
        CustomTranslate.set_lang_codes(engine_data.get('languages'))

        translator = CustomTranslate()
        translator.set_source_lang('English')
        translator.set_target_lang('Chinese')
        translator.br = MagicMock()
        result = translator.br.open.return_value.read.return_value.decode
        result.return_value = '{"text": "你好世界！"}'

        self.assertEqual('你好世界！', translator.translate('Hello World!'))
