import unittest
from unittest.mock import patch, Mock

from ..lib.translation import Glossary
from ..engines.base import Base


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

    def test_restore(self):
        glossary = Glossary(Base.placeholder)
        glossary.glossary = [('a', 'a'), ('b', 'Z')]
        self.assertEqual(
            'a Z c', glossary.restore('{{id_000000}} {{id_000001}} c'))
