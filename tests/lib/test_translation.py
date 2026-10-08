import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock, call

from ...lib.utils import dummy
from ...lib.translation import (
    Glossary, ProgressBar, Translation, get_translation)
from ...lib.exception import TranslationCanceled, TranslationFailed
from ...engines.base import Base
from ...engines.deepl import DeeplTranslate


module_name = 'calibre_plugins.ebook_translator.lib.translation'


class TestGlossary(unittest.TestCase):
    @patch(f'{module_name}.open')
    def test_load_from_file(self, mock_open):
        def mock_open_function(path, mode, newline=None):
            if path == '/path/to/glossary.txt':
                file = Mock()
                file.read.return_value.strip.return_value = 'a\n\n\nb\nZ\n'
                mock_open.__enter__.return_value = file
                return mock_open
            else:
                raise TypeError('any glossary error.')
        mock_open.side_effect = mock_open_function

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
        self.cancel_request = Mock(return_value=False)
        self.log = Mock()
        self.translation = Translation(self.translator, self.glossary)

    def test_created_translation(self):
        self.assertIs(self.translation.translator, self.translator)
        self.assertIs(self.translation.glossary, self.glossary)

        self.assertFalse(self.translation.fresh)
        self.assertFalse(self.translation.batch)
        self.assertIs(dummy, self.translation.progress)
        self.assertIs(dummy, self.translation.log)
        self.assertIs(dummy, self.translation.streaming)
        self.assertIs(dummy, self.translation.callback)
        self.assertIs(dummy, self.translation.cancel_request)

        self.assertEqual(0, self.translation.total)
        self.assertIsInstance(self.translation.progress_bar, ProgressBar)
        self.assertEqual(0, self.translation.abort_count)

        self.assertTrue(hasattr(self.translation, 'token_usage'))
        self.assertEqual(0, self.translation.token_usage['total_tokens'])
        self.assertEqual(0, self.translation.token_limit)

    @patch(f'{module_name}.get_config')
    def test_factory_applies_engine_token_limit(self, mock_get_config):
        mock_get_config.return_value = {
            'glossary_enabled': False, 'log_translation': False}
        translator = Mock(placeholder=Base.placeholder, token_limit=321)

        translation = get_translation(translator)

        self.assertEqual(321, translation.token_limit)

    def test_accumulates_request_token_usage_and_emits_snapshot(self):
        self.assertTrue(hasattr(self.translation, 'record_token_usage'))
        usage_callback = Mock()
        self.translation.set_token_usage_callback(usage_callback)
        self.translator.free = False
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=12, output_tokens=7, total_tokens=19,
            estimated=False)

        self.translation.record_token_usage(
            self.translator, 'source', 'translation')

        self.assertEqual(19, self.translation.token_usage['total_tokens'])
        usage_callback.assert_called_once_with(self.translation.token_usage)

    def test_does_not_count_free_engine_usage(self):
        self.translator.free = True
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=12, output_tokens=7, total_tokens=19,
            estimated=False)
        usage_callback = Mock()
        self.translation.set_token_usage_callback(usage_callback)

        self.translation.record_token_usage(
            self.translator, 'source', 'translation')

        self.assertEqual(0, self.translation.token_usage['total_tokens'])
        self.translator.consume_token_usage.assert_not_called()
        usage_callback.assert_not_called()

    def test_estimates_when_engine_returns_invalid_usage(self):
        self.translator.free = False
        self.translator.consume_token_usage.return_value = Mock()

        usage = self.translation.record_token_usage(
            self.translator, 'source text', 'translated text')

        self.assertTrue(usage['estimated'])
        self.assertGreater(usage['total_tokens'], 0)

    def test_estimates_input_for_engine_that_bypasses_base_translate(self):
        self.translator.free = False
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=0, output_tokens=4, total_tokens=4,
            estimated=True)

        usage = self.translation.record_token_usage(
            self.translator, 'source text', 'translated text')

        self.assertGreater(usage['input_tokens'], 0)
        self.assertEqual(4, usage['output_tokens'])
        self.assertEqual(
            usage['input_tokens'] + 4, usage['total_tokens'])

    def test_translate_text_records_successful_request_usage(self):
        self.translator.free = False
        self.translator.translate.return_value = 'translated'
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=8, output_tokens=3, total_tokens=11,
            estimated=False)

        result = self.translation.translate_text(0, 'source')

        self.assertEqual('translated', result)
        self.assertEqual(11, self.translation.token_usage['total_tokens'])

    @patch(f'{module_name}.Handler')
    def test_token_limit_forces_serial_requests(self, mock_handler):
        self.translator.free = False
        self.translator.concurrency_limit = 8
        self.translator.request_interval = 0
        translation = Translation(
            self.translator, self.glossary, token_limit=100)
        paragraph = Mock(original='source')

        translation.handle([paragraph])

        self.assertEqual(1, mock_handler.call_args.args[1])

    @patch(f'{module_name}.Handler')
    def test_free_engine_ignores_token_limit(self, mock_handler):
        self.translator.free = True
        self.translator.concurrency_limit = 8
        self.translator.request_interval = 0
        translation = Translation(
            self.translator, self.glossary, token_limit=100)
        paragraph = Mock(original='source')

        translation.handle([paragraph])

        self.assertEqual(0, translation.token_limit)
        self.assertEqual(8, mock_handler.call_args.args[1])

    def test_stops_before_next_paragraph_after_soft_limit(self):
        self.translator.free = False
        self.translator.concurrency_limit = 4
        self.translator.request_interval = 0
        self.translator.merge_enabled = False
        self.translator.name = 'Paid Engine'
        self.translator.get_target_lang.return_value = 'zh'
        self.translator.translate.return_value = 'translated'
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=7, output_tokens=3, total_tokens=10,
            estimated=False)
        self.glossary.replace.side_effect = lambda text: text
        self.glossary.restore.side_effect = lambda text: text
        paragraphs = [
            Mock(row=1, original='first', translation=''),
            Mock(row=2, original='second', translation=''),
        ]
        translation = Translation(
            self.translator, self.glossary, token_limit=10)

        completed = translation.handle(paragraphs)

        self.assertFalse(completed)
        self.translator.translate.assert_called_once_with('first')
        self.assertEqual('translated', paragraphs[0].translation)
        self.assertEqual('', paragraphs[1].translation)
        self.assertTrue(translation.token_usage['reached'])

    def test_finishes_when_last_paragraph_reaches_soft_limit(self):
        self.translator.free = False
        self.translator.concurrency_limit = 4
        self.translator.request_interval = 0
        self.translator.merge_enabled = False
        self.translator.name = 'Paid Engine'
        self.translator.get_target_lang.return_value = 'zh'
        self.translator.translate.return_value = 'translated'
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=7, output_tokens=3, total_tokens=10,
            estimated=False)
        self.glossary.replace.side_effect = lambda text: text
        self.glossary.restore.side_effect = lambda text: text
        paragraph = Mock(row=1, original='only', translation='')
        translation = Translation(
            self.translator, self.glossary, token_limit=10)

        completed = translation.handle([paragraph])

        self.assertTrue(completed)
        self.assertEqual('translated', paragraph.translation)
        self.assertTrue(translation.token_usage['reached'])

    def test_failed_only_request_reaching_limit_is_incomplete(self):
        self.translator.free = False
        self.translator.concurrency_limit = 1
        self.translator.request_interval = 0
        self.translator.translate.side_effect = RuntimeError('request failed')
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=10, output_tokens=0, total_tokens=10,
            estimated=True)
        paragraph = Mock(row=1, original='only', translation='')
        translation = Translation(
            self.translator, self.glossary, token_limit=10)

        completed = translation.handle([paragraph])

        self.assertFalse(completed)
        self.assertTrue(translation.token_usage['reached'])

    def test_stream_failure_reaching_limit_stops_before_next_paragraph(self):
        self.translator.free = False
        self.translator.concurrency_limit = 1
        self.translator.request_interval = 0
        self.translator.merge_enabled = False
        self.translator.consume_token_usage.return_value = SimpleNamespace(
            input_tokens=7, output_tokens=3, total_tokens=10,
            estimated=False)
        self.glossary.replace.side_effect = lambda text: text

        def failed_stream():
            yield 'partial'
            raise RuntimeError('stream failed')

        self.translator.translate.side_effect = lambda _: failed_stream()
        paragraphs = [
            Mock(row=1, original='first', translation=''),
            Mock(row=2, original='second', translation=''),
        ]
        translation = Translation(
            self.translator, self.glossary, token_limit=10)

        completed = translation.handle(paragraphs)

        self.assertFalse(completed)
        self.translator.translate.assert_called_once_with('first')
        self.assertEqual('', paragraphs[1].translation)

    def test_set_fresh(self):
        self.assertFalse(self.translation.fresh)
        self.translation.set_fresh(True)
        self.assertTrue(self.translation.fresh)

    def test_set_batch(self):
        self.assertFalse(self.translation.batch)
        self.translation.set_batch(True)
        self.assertTrue(self.translation.batch)

    def test_set_progress(self):
        self.assertIs(dummy, self.translation.progress)
        mock_progress = Mock()
        self.translation.set_progress(mock_progress)
        self.assertIs(mock_progress, self.translation.progress)

    def test_set_log(self):
        self.assertIs(dummy, self.translation.log)
        mock_log = Mock()
        self.translation.set_logging(mock_log)
        self.assertIs(mock_log, self.translation.log)

    def test_set_streaming(self):
        self.assertIs(dummy, self.translation.streaming)
        self.translation.set_streaming(self.streaming)
        self.assertIs(self.streaming, self.translation.streaming)

    def test_set_callback(self):
        self.assertIs(dummy, self.translation.callback)
        mock_callback = Mock()
        self.translation.set_callback(mock_callback)
        self.assertIs(mock_callback, self.translation.callback)

    def test_cancel_request(self):
        self.assertIs(dummy, self.translation.cancel_request)
        self.translation.set_cancel_request(self.cancel_request)
        self.assertIs(self.cancel_request, self.translation.cancel_request)

    def test_need_stop(self):
        self.translator.max_error_count = 0
        self.assertFalse(self.translation.need_stop())

        self.translator.max_error_count = 1
        self.translation.abort_count = 1
        self.assertTrue(self.translation.need_stop())

        self.translator.max_error_count = 1
        self.translation.abort_count = 2
        self.assertTrue(self.translation.need_stop())

    def test_translate_text_first_cancel(self):
        self.translation.cancel_request = self.cancel_request
        self.cancel_request.return_value = True
        self.assertRaises(
            TranslationCanceled, self.translation.translate_text, 0, 'test')
        self.assertEqual(1, self.cancel_request.call_count)

    def test_translate_text_second_cancel(self):
        self.translator.translate.side_effect = Exception
        self.translation.cancel_request = self.cancel_request
        self.cancel_request.side_effect = [False, True]
        self.assertRaises(
            TranslationCanceled, self.translation.translate_text, 0, 'test')
        self.assertEqual(2, self.cancel_request.call_count)

    @patch.object(Translation, 'need_stop', lambda self: True)
    def test_translate_text_need_cancel(self):
        self.translation.translator.translate.side_effect = Exception
        self.translation.cancel_request = self.cancel_request
        self.cancel_request.return_value = False
        self.assertRaises(
            TranslationCanceled, self.translation.translate_text, 0, 'text')

    @patch.object(Translation, 'need_stop', lambda self: False)
    @patch(f'{module_name}.traceback_error')
    @patch(f'{module_name}.time')
    def test_translate_text_retry_failed_translation(self, mock_time, mock_te):
        mock_te.return_value = 'test error trackback'
        self.translation.translator.match_error.return_value = False
        self.translation.translator.translate.side_effect = Exception(
            'network error')
        self.translation.log = self.log
        self.translation.cancel_request = self.cancel_request
        self.translator.request_attempt = 5

        with self.assertRaises(TranslationFailed) as cm:
            self.translation.translate_text(0, 'text')

        self.assertEqual(
            str(cm.exception),
            'Failed to retrieve data from translate engine API.\n'
            'network error')
        self.assertEqual(5, self.log.call_count)
        log_text = (
            '══════════════════════════════════════\n'
            'Row: 0\n'
            'Original: text\n'
            '┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n'
            'Status: Failed 1 times / Sleeping for 5 seconds\n'
            '┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n'
            'Error: test error trackback')
        self.log.assert_any_call(log_text, True)
        mock_time.sleep.assert_has_calls([
            call(5), call(10), call(15), call(20), call(25)])
        self.assertEqual(6, self.translation.abort_count)

    def test_translate_cancel_due_to_fatal_error(self):
        pass

    def test_translate_paragraph_cancel(self):
        self.translation.cancel_request = self.cancel_request
        self.cancel_request.return_value = True
        self.assertRaises(
            TranslationCanceled,
            self.translation.translate_paragraph,
            self.paragraph)
        self.assertEqual(1, self.cancel_request.call_count)

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

        self.streaming.assert_has_calls([call(''), call('Translating...')])
        self.glossary.restore.assert_called_with('你好世界')

        self.assertEqual('你好呀世界', self.paragraph.translation)
        self.assertEqual('Google', self.paragraph.engine_name)
        self.assertEqual('zh', self.paragraph.target_lang)
        self.assertFalse(self.paragraph.is_cache)

    @patch(f'{module_name}.time')
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
            call(''), call('Translating...'), call(''), call('你'),
            call('好'), call('世'), call('界')])
        mock_time.sleep.assert_called_with(0.05)

        self.assertEqual('你好呀世界', self.paragraph.translation)

        # More than one paragraph to translate.
        self.streaming.reset_mock()
        mock_time.reset_mock()
        self.paragraph.translation = ''
        self.translation.total = 2
        self.translation.translate_paragraph(self.paragraph)

        self.streaming.assert_has_calls([call(''), call('Translating...')])
        mock_time.sleep.assert_not_called()

        self.assertEqual('你好呀世界', self.paragraph.translation)

    def test_translate_paragraph_without_merge_enabled(self):
        self.translation.set_fresh(True)
        self.translator.merge_enabled = False

        self.translation.translate_paragraph(self.paragraph)

        self.paragraph.do_aligment.assert_not_called()

    def test_translate_paragraph_with_merge_enabled(self):
        self.translation.set_fresh(True)
        self.translator.separator = '\n\n'
        self.translator.merge_enabled = True

        self.translation.translate_paragraph(self.paragraph)

        self.paragraph.do_aligment.assert_called_once_with('\n\n')
