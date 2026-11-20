import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ..advanced import PreparationWorker
from ..lib.ebook import Ebook


module_name = 'calibre_plugins.ebook_translator.advanced'


class TestPreparationWorker(unittest.TestCase):
    def setUp(self):
        self.ebook = Ebook(
            1, 'Test', {'epub': 'test.epub'}, 'epub', 'English')
        self.ebook.set_target_lang('Chinese')
        engine = SimpleNamespace(name='Test', placeholder='', separator='')
        self.worker = PreparationWorker(engine, self.ebook)
        self.failures = []
        self.closed = []
        self.finished = []
        self.worker.failed.connect(
            lambda message, detail: self.failures.append((message, detail)))
        self.worker.close.connect(
            lambda result: self.closed.append((result, self.worker.on_working)))
        self.worker.finished.connect(self.finished.append)

        self.cache = Mock()
        self.cache.is_fresh.return_value = True
        self.cache.is_persistence.return_value = True
        self.handler = Mock()
        self.handler.get_merge_length.return_value = 0
        self.handler.prepare_original.return_value = []
        for name, value in [
                ('get_cache', self.cache),
                ('get_element_handler', self.handler),
                ('extract_item', [])]:
            patcher = patch(f'{module_name}.{name}', return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def assert_failed(self, exception_text):
        self.worker.prepare_ebook_data()

        self.assertFalse(self.worker.on_working)
        self.assertEqual(self.closed, [(1, False)])
        self.assertEqual(self.finished, [])
        self.assertEqual(len(self.failures), 1)
        message, detail = self.failures[0]
        self.assertTrue(message)
        self.assertIn(exception_text, detail)

    def test_cache_open_failure_reports_details(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'missing' / 'cache.db'
            self.get_cache.side_effect = lambda identity: sqlite3.connect(
                str(database))
            self.assert_failed(
                'OperationalError: unable to open database file')
        self.cache.destroy.assert_not_called()

    def test_extraction_failure_reports_details(self):
        self.extract_item.side_effect = ValueError('invalid ebook')
        self.assert_failed('ValueError: invalid ebook')
        self.cache.destroy.assert_called_once()

    def test_filter_failure_reports_details(self):
        self.handler.prepare_original.side_effect = ValueError('invalid content')
        self.assert_failed('ValueError: invalid content')
        self.cache.destroy.assert_called_once()

    def test_cache_save_failure_reports_details(self):
        self.cache.save.side_effect = sqlite3.OperationalError('disk is full')
        self.assert_failed('OperationalError: disk is full')
        self.cache.destroy.assert_called_once()

    def test_success_does_not_report_failure(self):
        self.worker.prepare_ebook_data()

        self.assertFalse(self.worker.on_working)
        self.assertEqual(self.failures, [])
        self.assertEqual(self.closed, [])
        self.assertEqual(len(self.finished), 1)
        self.cache.destroy.assert_not_called()

    def test_cancel_does_not_report_failure(self):
        self.worker.set_canceled(True)
        self.worker.prepare_ebook_data()

        self.assertFalse(self.worker.on_working)
        self.assertEqual(self.failures, [])
        self.assertEqual(self.closed, [(1, False)])
        self.assertEqual(self.finished, [])
        self.cache.destroy.assert_called_once()
