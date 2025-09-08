import unittest
from unittest.mock import MagicMock, Mock, patch, DEFAULT, call

from qt.core import QApplication, QWidget  # type: ignore

from ..batch import BatchTranslation
from ..lib.conversion import ConversionWorker
from ..lib.ebook import Ebooks


module_name = 'calibre_plugins.ebook_translator.batch'


class TestBatchTranslation(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication([])
        self.app.is_dark_theme = False
        self.parent = QWidget()

        self.mock_woker = Mock(ConversionWorker)
        self.mock_ebooks = MagicMock(Ebooks)

        with patch.multiple(
            f'{module_name}',
            AlertMessage=DEFAULT,
            get_config=DEFAULT,
            ConversionWorker=DEFAULT,
            Ebooks=DEFAULT,
        ) as mocks:
            self.mock_alert = mocks['AlertMessage']
            self.mock_get_config = mocks['get_config']
            self.mock_conversionworker = mocks['ConversionWorker']
            self.mock_ebooks_class = mocks['Ebooks']
            self.batch = BatchTranslation(
                self.parent, self.mock_woker, self.mock_ebooks)

    def test_created_batch_translation(self):
        self.assertIsInstance(self.batch, BatchTranslation)
        self.assertTrue(hasattr(self.batch, 'translate_ebooks'))
        self.assertTrue(callable(getattr(self.batch, 'translate_ebooks')))

    def test_translate_ebooks_with_none_path(self):
        def side_effect(key, default=None):
            return {'output_path': None, 'to_library': False}.get(key, default)
        self.mock_get_config.return_value.get.side_effect = side_effect

        self.batch.translate_ebooks()

        self.mock_alert().pop.assert_called_with(
            'The specified path does not exist.', 'warning')

    @patch(f'{module_name}.os.path')
    def test_translate_ebooks_with_non_exists_path(self, mock_os_path):
        mock_os_path.exists.return_value = False

        def side_effect(key, default=None):
            return {
                'output_path': '/path/to/fake/dir', 'to_library': False
            }.get(key, default)
        self.mock_get_config.return_value.get.side_effect = side_effect

        self.batch.translate_ebooks()

        mock_os_path.exists.assert_called_with('/path/to/fake/dir')
        self.mock_alert().pop.assert_called_with(
            'The specified path does not exist.', 'warning')

    @patch(f'{module_name}.BatchTranslation.done')
    def test_translate_ebooks(self, mock_done):
        def side_effect(key, default=None):
            return {
                'output_path': '/path/to/real/dir', 'to_library': True
            }.get(key, default)
        self.mock_get_config.return_value.get.side_effect = side_effect
        self.mock_ebooks.__iter__.return_value = [
            mock_ebook_1 := Mock(), mock_ebook_2 := Mock()]

        self.batch.translate_ebooks()

        self.assertEqual(self.mock_woker.translate_ebook.call_count, 2)
        self.assertEqual(self.mock_woker.translate_ebook.call_args_list, [
            call(mock_ebook_1, is_batch=True),
            call(mock_ebook_2, is_batch=True)])
        self.mock_ebooks.clear.assert_called_once()
        mock_done.assert_called_once_with(0)

    def tearDown(self):
        self.app.quit()
        del self.app
