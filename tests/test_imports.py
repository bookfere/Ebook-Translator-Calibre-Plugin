import unittest
from importlib import import_module


class TestUiModuleImports(unittest.TestCase):
    def test_token_usage_ui_modules_import(self):
        package = 'calibre_plugins.ebook_translator'

        self.assertIsNotNone(import_module(f'{package}.advanced'))
        self.assertIsNotNone(import_module(f'{package}.setting'))
