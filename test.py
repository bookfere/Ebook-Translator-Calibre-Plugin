import sys
import unittest
from pathlib import Path
from importlib import import_module

from calibre.utils.run_tests import run_cli  # type: ignore


def get_test_suite(filenames=[]):
    suite = unittest.TestSuite()
    patterns = ['test_*.py']
    if len(filenames) > 0:
        patterns = []
        for filename in filenames:
            patterns.append(filename)
    for pattern in patterns:
        for path in Path('tests').rglob(pattern):
            module_name = '.'.join(path.with_suffix('').parts)
            test_module = import_module(
                f'calibre_plugins.ebook_translator.{module_name}')
            suite.addTests(
                unittest.defaultTestLoader.loadTestsFromModule(test_module))
    return suite


if __name__ == '__main__':
    filenames, methods = [], []
    for arg in sys.argv[1:]:
        if Path(arg).suffix == '.py':
            filenames.append(arg)
        else:
            methods.append(arg)
    patterns = [f'*{m}' for m in methods] if len(methods) > 0 else None
    unittest.defaultTestLoader.testNamePatterns = patterns
    suite = get_test_suite(filenames)
    # runner = unittest.TextTestRunner(verbosity=1, failfast=True)
    # result = runner.run(suite)
    # if not result.wasSuccessful():
    #     exit(1)
    run_cli(suite, verbosity=4, buffer=False)
