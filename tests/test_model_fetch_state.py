import unittest

from ..setting import ModelFetchState


class TestModelFetchState(unittest.TestCase):
    def test_automatic_failure_does_not_request_dialog(self):
        state = ModelFetchState()
        state.begin(manual=False)

        self.assertFalse(state.finish(success=False))

    def test_manual_failure_requests_dialog(self):
        state = ModelFetchState()
        state.begin(manual=True)

        self.assertTrue(state.finish(success=False))

    def test_completion_resets_manual_request_state(self):
        state = ModelFetchState()
        state.begin(manual=True)
        self.assertFalse(state.finish(success=True))
        state.begin(manual=False)

        self.assertFalse(state.finish(success=False))
