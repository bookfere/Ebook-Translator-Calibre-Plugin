import inspect
import unittest
from unittest.mock import Mock

from ...lib.handler import Handler


class TestHandlerStopCondition(unittest.TestCase):
    def test_processes_completed_item_before_stopping_pending_queue(self):
        self.assertIn('should_stop', inspect.signature(Handler).parameters)
        paragraphs = [Mock(name='first'), Mock(name='second')]
        translated = []
        processed = []

        def translate(paragraph):
            translated.append(paragraph)
            paragraph.is_cache = False

        handler = Handler(
            paragraphs, 1, translate, processed.append, 0,
            should_stop=lambda: len(translated) == 1)

        handler.handle()

        self.assertEqual([paragraphs[0]], translated)
        self.assertEqual([paragraphs[0]], processed)
        self.assertTrue(handler.stopped_early)

    def test_reaching_condition_on_last_item_is_not_an_early_stop(self):
        paragraph = Mock(name='only')
        paragraph.is_cache = False
        reached = False

        def translate(_paragraph):
            nonlocal reached
            reached = True

        handler = Handler(
            [paragraph], 1, translate, lambda _: None, 0,
            should_stop=lambda: reached)

        handler.handle()

        self.assertFalse(handler.stopped_early)

    def test_exception_stops_pending_items_when_condition_is_reached(self):
        paragraphs = [Mock(name='first'), Mock(name='second')]
        translated = []
        processed = []
        reached = False

        def translate(paragraph):
            nonlocal reached
            translated.append(paragraph)
            reached = True
            raise RuntimeError('stream failed')

        handler = Handler(
            paragraphs, 1, translate, processed.append, 0,
            should_stop=lambda: reached)

        handler.handle()

        self.assertEqual([paragraphs[0]], translated)
        self.assertEqual([paragraphs[0]], processed)
        self.assertTrue(handler.stopped_early)
