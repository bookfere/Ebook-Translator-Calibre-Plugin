import unittest
from types import GeneratorType

from ..lib.utils import uid, trim, chunk, group


class TestUtils(unittest.TestCase):
    def test_uid(self):
        self.assertEqual('202cb962ac59075b964b07152d234b70', uid('123'))
        self.assertEqual('202cb962ac59075b964b07152d234b70', uid(b'123'))
        self.assertEqual('e10adc3949ba59abbe56e057f20f883e', uid('123', '456'))

    def test_trim(self):
        self.assertEqual('abc', trim('   abc   '))
        self.assertEqual('a b c', trim(' a b c '))
        self.assertEqual('a b c', trim(' a    b   c '))

        # &#160;
        content = '{0}{0}{1}{1}a{2}{2}{1}b{2}{0}{2}c{1}{1}{0}{0}'.format(
            '\xa0', '\x1a', u'\u3000')
        self.assertEqual('a b c', trim(content))

    def test_chunk(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
        self.assertIsInstance(chunk(data, 3), GeneratorType)
        self.assertEqual([data], list(chunk(data, 1)))
        self.assertEqual(
            [[1, 2, 3], [4, 5, 6], [7, 8, 9, 0]], list(chunk(data, 3)))
        self.assertEqual(
            [[1, 2], [3, 4], [5, 6], [7, 8], [9, 0]], list(chunk(data, 5)))
        self.assertEqual(
            [[1], [2, 3], [4, 5], [6], [7, 8], [9, 0]],
            list(chunk(data, 6)))
        self.assertEqual(
            [[1], [2], [3], [4], [5], [6], [7], [8], [9], [0]],
            list(chunk(data, 10)))
        self.assertEqual(
            [[1], [2], [3], [4], [5], [6], [7], [8], [9], [0]],
            list(chunk(data, 10000000)))
        self.assertEqual(
            [[1], [2], [3], [4], [5], [6], [7], [8], [9], [0]],
            list(chunk(data, 0)))

    def test_group(self):
        self.assertEqual(
            [(1, 1), (3, 3), (5, 5)], group([1, 5, 3]))
        self.assertEqual(
            [(1, 7)], group([1, 2, 3, 4, 5, 6, 7]))
        self.assertEqual(
            [(1, 3), (5, 7), (9, 9)], group([1, 2, 3, 5, 6, 7, 9]))
