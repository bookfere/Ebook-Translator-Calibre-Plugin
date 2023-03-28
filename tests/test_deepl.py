import json
import unittest
from unittest.mock import MagicMock

from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate


class TestDeepl(unittest.TestCase):
    def setUp(self):
        self.translator = DeeplTranslate(
            'DeepL', 'xxx', 'English', 'Chinese (Simplified)')
        self.translator.br = MagicMock()
        self.result = self.translator.br.open.return_value.read \
            .return_value.decode

    def test_lang_codes_matches(self):
        codes = json.loads(get_resources('engines/lang.json'))
        codes = [code.lower() for code in codes.values()]
        for code in DeeplTranslate.source_lang_codes:
            with self.subTest(code=code):
                self.assertTrue(code.lower() in codes)

        for code in DeeplTranslate.target_lang_codes:
            with self.subTest(code=code):
                self.assertIn(code.lower(), codes)

    def test_get_endpoint(self):
        self.assertEqual(
            'https://api-free.deepl.com/v2/translate',
            self.translator.get_endpoint())

    def test_translate(self):
        self.result.return_value = '{"translations":[{' \
            '"detected_source_language":"EN","text":"你好世界！"}]}'
        self.assertEqual('你好世界！', self.translator.translate('Hello World!'))

        # bad response
        self.result.return_value = ''
        with self.assertRaises(Exception) as e:
            self.translator.translate('Hello World!')
        self.assertIn('Expecting value', str(e.exception))
