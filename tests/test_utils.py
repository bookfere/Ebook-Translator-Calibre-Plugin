import html
import unittest
from calibre_plugins.ebook_translator.utils import uid, trim


class TestUtils(unittest.TestCase):
    def test_uid(self):
        self.assertEqual('202cb962ac59075b964b07152d234b70', uid('123'))
        self.assertEqual('202cb962ac59075b964b07152d234b70', uid(b'123'))
        self.assertEqual('e10adc3949ba59abbe56e057f20f883e', uid('123', '456'))

    def test_trim(self):
        self.assertEqual('abc', trim('   abc   '))
        self.assertEqual('a b c', trim(' a b c '))

        content = '{0}abc{0}'.format(html.unescape('&#160;') * 3)
        self.assertEqual('abc', trim(content))
