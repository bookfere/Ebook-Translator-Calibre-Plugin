import unittest
from unittest.mock import patch, Mock, call

from ..lib.translation import Glossary, ProgressBar, Translation
from ..lib.exception import (
    NoAvailableApiKey, TranslationCanceled, TranslationFailed)
from ..engines.base import Base
from ..engines.deepl import DeeplTranslate


class TestGlossary(unittest.TestCase):
    @patch('calibre_plugins.ebook_translator.lib.translation.open')
    def test_load_from_file(self, mock_open):
        def mock_open_method(path, mode, newline=None):
            if path == '/path/to/glossary.txt':
                file = Mock()
                file.read.return_value.strip.return_value = 'a\n\n\nb\nZ\n'
                mock_open.__enter__.return_value = file
                return mock_open
            else:
                raise TypeError('any glossary error.')
        mock_open.side_effect = mock_open_method

        glossary = Glossary(Base.placeholder)
        self.assertEqual([], glossary.glossary)
        glossary.load_from_file('/path/to/glossary.txt')
        self.assertEqual([('a', 'a'), ('b', 'Z')], glossary.glossary)

        glossary = Glossary(Base.placeholder)
        self.assertEqual([], glossary.glossary)
        glossary.load_from_file('/path/to/fake.txt')
        self.assertEqual([], glossary.glossary)

    def test_replace(self):
        glossary = Glossary(Base.placeholder)
        glossary.glossary = [('a', 'a'), ('b', 'Z')]
        self.assertEqual(
            '{{id_000000}} {{id_000001}} c', glossary.replace('a b c'))

        glossary = Glossary(DeeplTranslate.placeholder)
        glossary.glossary = [('a', 'a'), ('b', 'Z')]
        self.assertEqual(
            '<m id=000000 /> <m id=000001 /> c', glossary.replace('a b c'))

    def test_restore(self):
        glossary = Glossary(Base.placeholder)
        glossary.glossary = [('a', 'a'), ('b', 'Z')]
        self.assertEqual(
            'a Z c', glossary.restore('{{id_000000}} {{id_000001}} c'))

        glossary = Glossary(DeeplTranslate.placeholder)
        glossary.glossary = [('a', 'a'), ('b', 'Z')]
        self.assertEqual(
            'a Z c', glossary.restore('<m id=000000 /> <m id=000001 /> c'))


class TestProgressBar(unittest.TestCase):
    def test_load(self):
        progress_bar = ProgressBar()
        progress_bar.load(100)
        self.assertEqual(100, progress_bar.total)
        self.assertEqual(0.0, progress_bar.length)
        self.assertEqual(0.01, progress_bar.step)

    def test_count(self):
        progress_bar = ProgressBar()
        progress_bar.load(100)
        for count in range(1, 101):
            with self.subTest(count=count):
                self.assertEqual(count, progress_bar.count)
        self.assertEqual(1.0, round(progress_bar.length, 8))


class TestTranslation(unittest.TestCase):
    def setUp(self):
        self.translator = Mock()
        self.glossary = Mock()
        self.paragraph = Mock()
        self.streaming = Mock()
        self.translation = Translation(self.translator, self.glossary)

    def test_translate_paragraph_exception(self):
        self.translation.set_cancel_request(lambda: True)

        self.assertRaises(
            TranslationCanceled,
            self.translation.translate_paragraph,
            self.paragraph)

    def test_translate_paragraph_cached(self):
        self.paragraph.translation = '你好世界'
        self.translation.translate_paragraph(self.paragraph)

        self.assertTrue(self.paragraph.is_cache)

    def test_translate_paragraph_fresh(self):
        self.translation.set_fresh(True)
        self.translation.set_streaming(self.streaming)
        self.paragraph.translation = '你好世界'
        self.translator.translate.return_value = '你好世界'
        self.glossary.restore.return_value = '你好呀世界'
        self.translator.name = 'Google'
        self.translator.get_target_lang.return_value = 'zh'
        self.translation.translate_paragraph(self.paragraph)

        self.streaming.assert_has_calls([call(''), call(_('Translating...'))])
        self.glossary.restore.assert_called_with('你好世界')

        self.assertEqual('你好呀世界', self.paragraph.translation)
        self.assertEqual('Google', self.paragraph.engine_name)
        self.assertEqual('zh', self.paragraph.target_lang)
        self.assertFalse(self.paragraph.is_cache)

    @patch('calibre_plugins.ebook_translator.lib.translation.time')
    def test_translate_paragraph_streaming(self, mock_time):
        self.translation.set_streaming(self.streaming)
        self.translator.translate.return_value = (i for i in '你好世界')
        self.translator.name = 'Google'
        self.translator.get_target_lang.return_value = 'zh'
        self.glossary.restore.return_value = '你好呀世界'
        self.paragraph.translation = ''
        self.translation.total = 1
        self.translation.translate_paragraph(self.paragraph)

        self.streaming.assert_has_calls([
            call(''), call(_('Translating...')), call(''), call('你'),
            call('好'), call('世'), call('界')])
        mock_time.sleep.assert_called_with(0.05)

        self.assertEqual('你好呀世界', self.paragraph.translation)

        # More than one paragraph to translate.
        self.streaming.reset_mock()
        mock_time.reset_mock()
        self.paragraph.translation = ''
        self.translation.total = 2
        self.translation.translate_paragraph(self.paragraph)

        self.streaming.assert_has_calls([call(''), call(_('Translating...'))])
        mock_time.sleep.assert_not_called()

        self.assertEqual('你好呀世界', self.paragraph.translation)
