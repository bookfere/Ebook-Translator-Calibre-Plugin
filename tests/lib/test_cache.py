import os
import unittest
from tempfile import TemporaryDirectory

from ...lib.cache import Paragraph, TranslationCache


class TestParagraph(unittest.TestCase):
    def setUp(self):
        self.paragraph = Paragraph(
            1, 'TEST', 'a\n\nb\n\nc', 'a\n\nb\n\nc\n\n',
            translation='A\n\nB\n\nC', attributes='{"class": "test"}')

    def test_created_paragraph(self):
        self.assertIsInstance(self.paragraph, Paragraph)
        self.assertFalse(self.paragraph.is_cache)
        self.assertIsNone(self.paragraph.error)
        self.assertTrue(self.paragraph.aligned)

    def test_get_attributes(self):
        self.assertEqual({'class': 'test'}, self.paragraph.get_attributes())

    def test_check_translation(self):
        self.assertTrue(self.paragraph.is_alignment('\n\n'))

        self.paragraph.original = 'a\n\nb\n\nc'
        self.paragraph.translation = 'A\n\nB\nC\n\n'
        self.assertFalse(self.paragraph.is_alignment('\n\n'))

    def test_is_alignment(self):
        # Test with empty translation.
        self.paragraph.translation = None
        self.assertTrue(self.paragraph.is_alignment('\n\n'))

        self.paragraph.translation = ''
        self.assertTrue(self.paragraph.is_alignment('\n\n'))

        self.paragraph.translation = '   '
        self.assertTrue(self.paragraph.is_alignment('\n\n'))

        self.paragraph.original = 'a\n\nb\n\nc'
        self.paragraph.translation = 'A\n\nB\n\nC'
        self.assertTrue(self.paragraph.is_alignment('\n\n'))

        # Alignment determination ignores line breaks at the start and end.
        self.paragraph.translation = '\n\nA\n\nB\n\nC\n\n'
        self.assertTrue(self.paragraph.is_alignment('\n\n'))

        self.paragraph.original = 'a\n\nb'
        self.paragraph.translation = 'A\n\nB\n\nC'
        self.assertFalse(self.paragraph.is_alignment('\n\n'))

        self.paragraph.original = 'a\n\nb\n\nc'
        self.paragraph.translation = 'A\n\nB'
        self.assertFalse(self.paragraph.is_alignment('\n\n'))

    def test_do_alignment(self):
        # Test with empty translation
        self.paragraph.translation = None
        self.paragraph.do_aligment('\n\n')
        self.assertIsNone(self.paragraph.translation)

        self.paragraph.translation = ''
        self.paragraph.do_aligment('\n\n')
        self.assertEqual('', self.paragraph.translation)

        self.paragraph.translation = '   '
        self.paragraph.do_aligment('\n\n')
        self.assertEqual('   ', self.paragraph.translation)

        # Test with no alignment needed.
        self.paragraph.original = 'a\n\nb\n\nc'
        self.paragraph.translation = 'A\n\nB\n\nC'
        self.paragraph.do_aligment('\n')
        self.assertEqual('A\n\nB\n\nC', self.paragraph.translation)

        self.paragraph.translation = 'A\n\nB\nC'
        self.paragraph.do_aligment('\n\n')
        self.assertEqual('A\n\nB\n\nC', self.paragraph.translation)


class TestTranslationCacheRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.original_paths = (
            TranslationCache.dir_path,
            TranslationCache.cache_path,
            TranslationCache.temp_path,
        )
        TranslationCache.dir_path = self.temp_dir.name
        TranslationCache.cache_path = os.path.join(
            self.temp_dir.name, 'cache')
        TranslationCache.temp_path = os.path.join(
            self.temp_dir.name, 'temp')

    def tearDown(self):
        (
            TranslationCache.dir_path,
            TranslationCache.cache_path,
            TranslationCache.temp_path,
        ) = self.original_paths
        self.temp_dir.cleanup()

    def test_reopens_small_cache_with_completed_translation(self):
        cache = TranslationCache('small-book')
        cache.save([(
            1, 'paragraph-md5', '<p>Hello</p>', 'Hello', False, None,
            'chapter.xhtml')])
        paragraph = cache.paragraph(1)
        paragraph.translation = '你好'
        paragraph.engine_name = 'Primary'
        paragraph.target_lang = 'Chinese'
        cache.update_paragraph(paragraph)
        cache_path = cache.file_path
        cache.close()

        self.assertLess(os.path.getsize(cache_path), 50000)
        reopened = TranslationCache('small-book')
        try:
            self.assertFalse(reopened.is_fresh())
            self.assertEqual('你好', reopened.paragraph(1).translation)
        finally:
            reopened.close()
