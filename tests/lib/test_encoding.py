import codecs
import unittest

from ...lib.encodings import encoding_list


class TestEncodingList(unittest.TestCase):
    def test_encoding_list(self):
        for encoding in encoding_list:
            with self.subTest(encoding=encoding):
                self.assertIsInstance(
                    codecs.lookup(encoding), codecs.CodecInfo)
