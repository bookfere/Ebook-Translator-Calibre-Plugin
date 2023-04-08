import unittest
from calibre.utils.run_tests import run_cli
from calibre_plugins.ebook_translator.tests import (
    test_utils, test_config, test_deepl)


def get_tests(module):
    return unittest.defaultTestLoader.loadTestsFromModule(module)


def get_test_suite():
    suite = unittest.TestSuite()
    suite.addTests(get_tests(test_utils))
    suite.addTests(get_tests(test_config))
    suite.addTests(get_tests(test_deepl))

    return suite


if __name__ == '__main__':
    run_cli(get_test_suite())
