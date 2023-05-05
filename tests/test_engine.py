import re
import json
import unittest
from unittest.mock import MagicMock

from calibre_plugins.ebook_translator.engines.base import Base
from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate
from calibre_plugins.ebook_translator.engines.custom import (
    get_engine_template, load_engine_data, CustomTranslate)


load_translations()


class TestBase(unittest.TestCase):
    def setUp(self):
        self.mark, self.pattern = Base.placeholder

    def test_placeholder(self):
        marks = [
            '{{id_1}}', '{id_1}}', 'id_1}}', '{{id_1}', '{{id_1',
            '{ { id_1 }}', '{ { id _ 1 }', '{ { id _ 1', '{ id _ 1',
            'id_1 }}', 'id _ 1 }  }', 'id _ 1  }',
            'id_1', 'id _ 1', '  id _ 1   ',
        ]
        for mark in marks:
            with self.subTest(mark=mark):
                self.assertIsNotNone(
                    re.search(self.pattern.format(1), 'xxx %s xxx' % mark))


class TestDeepl(unittest.TestCase):
    def setUp(self):
        DeeplTranslate.set_lang_codes({
            'source': {'English': 'EN'},
            'target': {'Chinese': 'ZH'}
        })

        self.translator = DeeplTranslate()
        self.translator.set_api_key('xxx')
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')
        self.translator.br = MagicMock()
        self.response = self.translator.br.response
        self.result = self.response.return_value.read \
            .return_value.decode

    def test_get_usage(self):
        self.result.return_value = '{"character_count": 30, ' \
            '"character_limit": 100}'
        self.assertEqual(
            _('{} total, {} used, {} left').format(100, 30, 70),
            self.translator.get_usage(),)

        self.result.return_value = '<dummy info>'
        self.assertIsNone(self.translator.get_usage())

    def test_translate(self):
        self.result.return_value = '{"translations":[{' \
            '"detected_source_language":"EN","text":"你好世界！"}]}'
        self.assertEqual('你好世界！', self.translator.translate('Hello World!'))

        # bad response
        self.result.return_value = '<dummy info>'
        with self.assertRaises(Exception) as e:
            self.translator.translate('Hello World!')
        self.assertIn(
            _('Can not parse returned response. Raw data: {}')
            .format('<dummy info>') + ' ', str(e.exception))


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
        result = translator.br.response.return_value.read.return_value.decode
        result.return_value = '{"text": "你好世界！"}'

        self.assertEqual('你好世界！', translator.translate('Hello World!'))
