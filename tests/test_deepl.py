import unittest
from unittest.mock import MagicMock

from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate


load_translations()


class TestDeepl(unittest.TestCase):
    def setUp(self):
        lang_codes = {
            'source': {'English': 'EN'},
            'target': {'Chinese': 'ZH'}
        }
        self.translator = DeeplTranslate()
        self.translator.set_lang_codes(lang_codes)
        self.translator.set_api_key('xxx')
        self.translator.set_source_lang('English')
        self.translator.set_target_lang('Chinese')
        self.translator.br = MagicMock()
        self.response = self.translator.br.open
        self.result = self.response.return_value.read \
            .return_value.decode

    def test_get_usage(self):
        self.result.return_value = '{"character_count": 30, ' \
            '"character_limit": 100}'
        self.assertEqual(
            '100 total, 30 used, 70 left', self.translator.get_usage(),)

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
