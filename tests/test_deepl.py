import json
import unittest
from unittest.mock import MagicMock

from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate


load_translations()


class TestDeepl(unittest.TestCase):
    def setUp(self):
        self.translator = DeeplTranslate(
            'xxx', 'English', 'Chinese (simplified)')
        self.translator.br = MagicMock()
        self.response = self.translator.br.open
        self.result = self.response.return_value.read \
            .return_value.decode

    def test_endpoint(self):
        self.assertEqual(
            'https://api-free.deepl.com/v2/translate',
            self.translator.endpoint)

    def test_translate(self):
        self.response.return_value.code = 200
        self.result.return_value = '{"translations":[{' \
            '"detected_source_language":"EN","text":"你好世界！"}]}'
        self.assertEqual('你好世界！', self.translator.translate('Hello World!'))

        # bad response
        self.response.return_value.code = 403
        self.result.return_value = ''
        with self.assertRaises(Exception) as e:
            self.translator.translate('Hello World!')
        self.assertEqual(
            _('Translate engine return bad response.'), str(e.exception))
