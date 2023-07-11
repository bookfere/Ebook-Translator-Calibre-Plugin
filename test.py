import sys
import unittest

# from calibre.utils.run_tests import run_cli
from calibre_plugins.ebook_translator.tests import (
    test_utils, test_config, test_engine, test_custom, test_element,
    test_translation)


def get_tests(module):
    return unittest.defaultTestLoader.loadTestsFromModule(module)


def get_test_suite():
    suite = unittest.TestSuite()
    klasses = [
        test_utils, test_config, test_engine, test_custom, test_element,
        test_translation]
    suite.addTests(get_tests(klass) for klass in klasses)
    return suite


if __name__ == '__main__':
    args = sys.argv[1:]
    patterns = None if len(args) < 1 else ['*%s' % p for p in args]
    unittest.defaultTestLoader.testNamePatterns = patterns
    runner = unittest.TextTestRunner(verbosity=1, failfast=True)
    runner.run(get_test_suite())
    # run_cli(get_test_suite(), buffer=False)
