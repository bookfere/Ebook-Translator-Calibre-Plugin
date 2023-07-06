import re
import unittest
from unittest.mock import patch, Mock

from ..engines.base import Base
from ..engines.deepl import DeeplTranslate


load_translations()


class TestBase(unittest.TestCase):
    def setUp(self):
        self.mark, self.pattern = Base.placeholder

    def test_placeholder(self):
        marks = [
            '{{id_1}}', '{id_1} }', '{{id_1}', '{ { id_1 }}', '{ { id _ 1 }']
        for mark in marks:
            with self.subTest(mark=mark):
                self.assertIsNotNone(
                    re.search(self.pattern.format(1), 'xxx %s xxx' % mark))


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

        # bad response
        result.return_value = '<dummy info>'
        with self.assertRaises(Exception) as e:
            self.translator.translate('Hello World!')
        self.assertIn(
            _('Can not parse returned response. Raw data: {}')
            .format('\n<dummy info>\n') + 'Traceback',
            str(e.exception))
