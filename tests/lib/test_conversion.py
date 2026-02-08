import unittest
from pathlib import Path
from typing import Callable
from unittest.mock import patch, Mock

from ...lib.conversion import ConversionWorker
from ...lib.ebook import Ebook


module_name = 'calibre_plugins.ebook_translator.lib.conversion'


class TestConversionWorker(unittest.TestCase):
    def setUp(self):
        self.gui = Mock()
        self.icon = Mock()
        self.worker = ConversionWorker(self.gui, self.icon)
        self.worker.db = Mock()
        self.worker.api = Mock()

        self.ebook = Mock(Ebook)
        self.job = Mock()
        self.worker.working_jobs = {
            self.job: (self.ebook, str(Path('/path/to/test.epub')))}

    def test_create_worker(self):
        self.assertIsInstance(self.worker, ConversionWorker)

    def test_translate_done_job_failed_debug(self):
        self.job.failed = True
        with patch(module_name + '.DEBUG', True):
            self.worker.translate_done(self.job)
            self.gui.job_exception.assert_not_called()

    def test_translate_done_job_failed_not_debug(self):
        with patch(module_name + '.DEBUG', False):
            self.worker.translate_done(self.job)
            self.gui.job_exception.assert_called_once_with(
                self.job, dialog_title='Translation job failed')

    @patch(module_name + '.os')
    @patch(module_name + '.open')
    @patch(module_name + '.get_metadata')
    @patch(module_name + '.set_metadata')
    def test_translate_done_ebook_to_library(
            self, mock_set_metadata, mock_get_metadata, mock_open, mock_os):
        self.job.failed = False
        self.job.description = 'test description'
        self.job.log_path = '/path/to/log'
        metadata_config = {
            'subjects': ['test subject 1', 'test subject 2'],
            'lang_code': True,
            'lang_mark': True,
        }
        self.worker.config = {
            'ebook_metadata': metadata_config,
            'to_library': True,
        }
        self.ebook.is_extra_format.return_value = False
        self.ebook.title = 'test title'
        self.ebook.input_format = 'epub'
        self.ebook.output_format = 'epub'
        self.ebook.custom_title = 'test custom title'
        self.ebook.target_lang = 'German'
        self.ebook.target_direction = None
        self.ebook.lang_code = 'de'
        file = Mock()
        mock_open.return_value.__enter__.return_value = file
        metadata = Mock()
        metadata.title = 'test title'
        metadata.tags = []
        metadata.language = 'en'
        mock_get_metadata.return_value = metadata

        self.worker.db.create_book_entry.return_value = 89
        self.worker.api.format_abspath.return_value = '/path/to/test[m].epub'

        self.worker.translate_done(self.job)

        mock_open.assert_called_once_with(
            str(Path('/path/to/test.epub')), 'r+b')
        mock_get_metadata.assert_called_once_with(file, 'epub')
        mock_set_metadata.assert_called_once_with(file, metadata, 'epub')
        self.assertEqual('test custom title [German]', metadata.title)
        self.assertEqual('de', metadata.language)
        self.assertEqual([
            'test subject 1', 'test subject 2', 'Translated by Ebook '
            'Translator: https://translator.bookfere.com'], metadata.tags)

        self.worker.db.create_book_entry.assert_called_once_with(metadata)
        self.worker.api.add_format.assert_called_once_with(
            89, 'epub', str(Path('/path/to/test.epub')), run_hooks=False)
        self.worker.gui.library_view.model.assert_called_once()
        self.worker.gui.library_view.model().books_added \
            .assert_called_once_with(1)
        self.worker.api.format_abspath.assert_called_once_with(89, 'epub')

        self.worker.gui.status_bar.show_message.assert_called_once_with(
            'test description completed', 5000)
        arguments = self.worker.gui.proceed_question.mock_calls[0].args
        self.assertIsInstance(arguments[0], Callable)
        self.assertIs(self.worker.gui.job_manager.launch_gui_app, arguments[1])
        self.assertEqual('/path/to/log', arguments[2])
        self.assertEqual('Ebook Translation Log', arguments[3])
        self.assertEqual('Translation Completed', arguments[4])
        self.assertEqual(
            'The translation of "test custom title [German]" was completed. '
            'Do you want to open the book?',
            arguments[5])

        mock_payload = Mock()
        arguments[0](mock_payload)
        mock_payload.assert_called_once_with(
            'ebook-viewer',
            kwargs={'args': ['ebook-viewer', '/path/to/test[m].epub']})

        arguments = self.worker.gui.proceed_question.mock_calls[0].kwargs
        self.assertEqual(True, arguments.get('log_is_file'))
        self.assertIs(self.icon, arguments.get('icon'))


    @patch(module_name + '.open')
    @patch(module_name + '.open_path')
    @patch(module_name + '.os.rename')
    @patch(module_name + '.get_metadata')
    @patch(module_name + '.set_metadata')
    def test_translate_done_ebook_to_path(
            self, mock_set_metadata, mock_get_metadata, mock_os_rename,
            mock_open_path, mock_open):
        self.job.failed = False
        self.job.description = 'test description'
        self.job.log_path = str(Path('/path/to/log'))
        metadata_config = {
            'subjects': ['test subject 1', 'test subject 2'],
            'lang_code': True,
            'lang_mark': True,
        }
        self.worker.config = {
            'ebook_metadata': metadata_config,
            'to_library': False,
        }
        self.ebook.is_extra_format.return_value = False
        self.ebook.title = 'test title'
        self.ebook.input_format = 'epub'
        self.ebook.output_format = 'epub'
        self.ebook.custom_title = 'test: custom title*'
        self.ebook.target_lang = 'German'
        self.ebook.target_direction = None
        self.ebook.lang_code = 'de'
        file = Mock()
        mock_open.return_value.__enter__.return_value = file
        metadata = Mock()
        metadata.title = 'test title'
        metadata.tags = []
        metadata.language = 'en'
        mock_get_metadata.return_value = metadata

        self.worker.translate_done(self.job)

        original_path = str(Path('/path/to/test.epub'))
        new_path = str(Path('/path/to/test_ custom title_ [German].epub'))

        mock_open.assert_called_once_with(original_path, 'r+b')
        mock_os_rename.assert_called_once_with(original_path, new_path)
        self.worker.gui.status_bar.show_message.assert_called_once_with(
            'test description ' + 'completed', 5000)
        arguments = self.worker.gui.proceed_question.mock_calls[0].args
        self.assertIsInstance(arguments[0], Callable)
        self.assertIs(self.worker.gui.job_manager.launch_gui_app, arguments[1])
        self.assertEqual(str(Path('/path/to/log')), arguments[2])
        self.assertEqual('Ebook Translation Log', arguments[3])
        self.assertEqual('Translation Completed', arguments[4])
        self.assertEqual(
            'The translation of "test: custom title* [German]" was completed. '
            'Do you want to open the book?',
            arguments[5])

        mock_payload = Mock()
        arguments[0](mock_payload)
        mock_payload.assert_called_once_with(
            'ebook-viewer', kwargs={'args': [
                'ebook-viewer',
                str(Path('/path/to/test_ custom title_ [German].epub'))]})

        arguments = self.worker.gui.proceed_question.mock_calls[0].kwargs
        self.assertEqual(True, arguments.get('log_is_file'))
        self.assertIs(self.icon, arguments.get('icon'))


    @patch(module_name + '.open_path')
    @patch(module_name + '.os.rename')
    @patch(module_name + '.open')
    def test_translate_done_other_to_library(
            self, mock_open, mock_os_rename, mock_open_path):
        self.job.failed = False
        self.job.description = 'test description'
        self.job.log_path = str(Path('/path/to/log'))
        metadata_config = {'lang_mark': True}
        self.worker.config = {
            'ebook_metadata': metadata_config,
            'to_library': True,
        }
        self.ebook.is_extra_format.return_value = True
        self.ebook.id = 89
        self.ebook.title = 'test title'
        self.ebook.custom_title = 'test custom title'
        self.ebook.input_format = 'srt'
        self.ebook.output_format = 'srt'
        self.ebook.custom_title = 'test custom title'
        self.ebook.target_lang = 'German'
        self.worker.working_jobs = {
            self.job: (self.ebook, str(Path('/path/to/test.srt')))}
        metadata = Mock()
        self.worker.api.get_metadata.return_value = metadata
        self.worker.api.format_abspath.return_value = \
            str(Path('/path/to/test[m].srt'))
        self.worker.db.create_book_entry.return_value = 90

        self.worker.translate_done(self.job)

        self.worker.api.get_metadata.assert_called_once_with(89)
        self.worker.db.create_book_entry.assert_called_once_with(metadata)
        self.worker.api.add_format.assert_called_once_with(
            90, 'srt', str(Path('/path/to/test.srt')), run_hooks=False)
        self.worker.gui.library_view.model.assert_called_once()
        self.worker.gui.library_view.model().books_added \
            .assert_called_once_with(1)
        self.worker.api.format_abspath.assert_called_once_with(90, 'srt')
        self.worker.gui.status_bar.show_message.assert_called_once_with(
            'test description ' + 'completed', 5000)
        self.assertEqual('test custom title [German]', metadata.title)

        arguments = self.worker.gui.proceed_question.mock_calls[0].args
        self.assertIsInstance(arguments[0], Callable)
        self.assertIs(self.worker.gui.job_manager.launch_gui_app, arguments[1])
        self.assertEqual(str(Path('/path/to/log')), arguments[2])
        self.assertEqual('Ebook Translation Log', arguments[3])
        self.assertEqual('Translation Completed', arguments[4])
        self.assertEqual(
            'The translation of "test custom title [German]" was completed. '
            'Do you want to open the book?',
            arguments[5])

        mock_payload = Mock()
        arguments[0](mock_payload)
        mock_open_path.assert_called_once_with(
            str(Path('/path/to/test[m].srt')))

        arguments = self.worker.gui.proceed_question.mock_calls[0].kwargs
        self.assertEqual(True, arguments.get('log_is_file'))
        self.assertIs(self.icon, arguments.get('icon'))

    @patch(module_name + '.open_path')
    @patch(module_name + '.os.rename')
    @patch(module_name + '.open')
    def test_translate_done_other_to_path(
            self, mock_open, mock_os_rename, mock_open_path):
        self.job.failed = False
        self.job.description = 'test description'
        self.job.log_path = str(Path('/path/to/log'))
        metadata_config = {'lang_mark': True}
        self.worker.config = {
            'ebook_metadata': metadata_config,
            'to_library': False,
        }
        self.ebook.is_extra_format.return_value = True
        self.ebook.id = 89
        self.ebook.title = 'test title'
        self.ebook.custom_title = 'test custom title'
        self.ebook.input_format = 'srt'
        self.ebook.output_format = 'srt'
        self.ebook.custom_title = 'test: custom title*'
        self.ebook.target_lang = 'German'
        self.worker.working_jobs = {
            self.job: (self.ebook, str(Path('/path/to/test.srt')))}
        metadata = Mock()
        self.worker.api.get_metadata.return_value = metadata

        self.worker.translate_done(self.job)

        self.worker.api.get_metadata.assert_called_once_with(89)
        mock_os_rename.assert_called_once_with(
            str(Path('/path/to/test.srt')),
            str(Path('/path/to/test_ custom title_ [German].srt')))
        self.worker.gui.status_bar.show_message.assert_called_once_with(
            'test description ' + 'completed', 5000)
        arguments = self.worker.gui.proceed_question.mock_calls[0].args
        self.assertIsInstance(arguments[0], Callable)
        self.assertIs(self.worker.gui.job_manager.launch_gui_app, arguments[1])
        self.assertEqual(str(Path('/path/to/log')), arguments[2])
        self.assertEqual('Ebook Translation Log', arguments[3])
        self.assertEqual('Translation Completed', arguments[4])
        self.assertEqual(
            'The translation of "test: custom title* [German]" was completed. '
            'Do you want to open the book?',
            arguments[5])

        mock_payload = Mock()
        arguments[0](mock_payload)
        mock_open_path.assert_called_once_with(
            str(Path('/path/to/test_ custom title_ [German].srt')))

        arguments = self.worker.gui.proceed_question.mock_calls[0].kwargs
        self.assertEqual(True, arguments.get('log_is_file'))
        self.assertIs(self.icon, arguments.get('icon'))
