import sys
import unittest
from pkgutil import iter_modules
from importlib import import_module

from calibre.utils.run_tests import run_cli


def get_tests(module):
    return unittest.defaultTestLoader.loadTestsFromModule(module)


def get_test_suite():
    suite = unittest.TestSuite()
    for module in iter_modules(['tests']):
        module = import_module(
            'calibre_plugins.ebook_translator.tests.%s' % module.name)
        suite.addTests(get_tests(module))
    return suite


if __name__ == '__main__':
    args = sys.argv[1:]
    patterns = None if len(args) < 1 else ['*%s' % p for p in args]
    unittest.defaultTestLoader.testNamePatterns = patterns
    runner = unittest.TextTestRunner(verbosity=1, failfast=True)
    # result = runner.run(get_test_suite())
    # if not result.wasSuccessful():
    #     exit(1)
    run_cli(get_test_suite(), buffer=False)
