import unittest
from unittest.mock import Mock

from ...components.engine import EngineWorker


class TestEngineWorker(unittest.TestCase):
    def test_invalid_model_error_completes_request(self):
        translator = Mock()
        translator.translate.side_effect = Exception('Unknown model: typo')
        worker = EngineWorker(translator)
        failures = []
        completed = []

        worker.failure.connect(failures.append)
        worker.complete.connect(lambda: completed.append(True))
        worker.translate_text('Hello World!')

        self.assertEqual(1, len(failures))
        self.assertIn('Unknown model: typo', failures[0])
        self.assertEqual([True], completed)

    def test_usage_failure_is_ignored(self):
        translator = Mock()
        translator.get_usage.side_effect = Exception('Usage unavailable')
        worker = EngineWorker(translator)
        usages = []

        worker.usage.connect(usages.append)
        worker.check_usage()

        self.assertEqual([None], usages)
