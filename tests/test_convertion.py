import unittest
from unittest.mock import patch, MagicMock

from lxml import etree
from calibre_plugins.ebook_translator.utils import ns
from calibre_plugins.ebook_translator.convertion import (
    get_sorted_pages, extract_elements, get_elements, filter_content)


class TestConvertion(unittest.TestCase):
    def setUp(self):
        self.page_1 = MagicMock(
            media_type='text/html', href='test1.xhtml', data=etree.XML("""
<html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Test Document</title></head>
    <body>
        <p class="abc">abc</p>
        <p></p>
    </body>
</html>"""))
        self.page_2 = MagicMock(
            media_type='text/html', href='test2.xhtml', data=etree.XML("""
<html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Test Document</title></head>
    <body>
        <div class="abc">abc</div>
        <div></div>
    </body>
</html>"""))
        self.page_3 = MagicMock(media_type='text/css')
        self.pages = [self.page_3, self.page_2, self.page_1]

    def test_get_sorted_pages(self):
        self.assertEqual(
            [self.page_1, self.page_2], get_sorted_pages(self.pages))

    @patch('calibre_plugins.ebook_translator.convertion.get_config')
    def test_extract_elements(self, mock_get_config):
        mock_get_config.side_effect = lambda key: {
            'rule_mode': 'normal', 'filter_rules': []}.get(key)

        elements = extract_elements(self.pages)
        self.assertIsInstance(elements, list)
        self.assertEqual(2, len(elements))

    def test_get_elements(self):
        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>
    <div>
        <div>
            <div>123456789</div>
            <div><div>123</div>456789</div>
            <div>123456<div>789</div></div>
            <div>123<div>456</div>789</div>
            <div><div>123</div>456<div>789</div></div>
            <div><section>123<div>456</div></section>789</div>
            <pre>123 <code>456</code> 789</pre>
        </div>
    </div>
</body>
</html>""")
        root = xhtml.find('x:body', namespaces=ns)
        self.assertEqual(6, len(get_elements(root, [])))

        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>123456789</body>
</html>""")
        root = xhtml.find('x:body', namespaces=ns)
        self.assertEqual(1, len(get_elements(root, [])))

    @patch('calibre_plugins.ebook_translator.convertion.get_config')
    def test_filter_content(self, mock_get_config):
        values = {
            'rule_mode': 'normal',
            'filter_scope': 'text',
            'filter_rules': []
        }
        mock_get_config.side_effect = lambda key: values[key]

        markups = ['<p></p>', '<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(filter_content(etree.XML(markup)))

        values.update(filter_rules=['a', 'b', 'c'])
        markups = ['<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(filter_content(etree.XML(markup)))

        values.update(filter_rules=['A', 'B', 'C'])
        markups = ['<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(filter_content(etree.XML(markup)))

        values.update(rule_mode='case')
        markups = ['<p>xxxAxxx</p>', '<p>xxxBxxx</p>', '<p>xxxCxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(filter_content(etree.XML(markup)))

        values.update(filter_rules=['a', 'b', 'c'])
        mock_get_config.side_effect = lambda key: values[key]
        markups = ['<p>xxxAxxx</p>', '<p>xxxBxxx</p>', '<p>xxxCxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertTrue(filter_content(etree.XML(markup)))

        values.update(rule_mode='regex', filter_rules=['^a', 'f$', '[^z]'])
        markups = ['<p>5.</p>', '<p>5-5.</p>', '<p>5-5_5.</p>',
                   '<p>abc</p>', '<p>def</p>', '<p>ghi</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(filter_content(etree.XML(markup)))

        values.update(
            rule_mode='regex', filter_scope='html',
            filter_rules=['^<pre>', '</code>$', 'class="c"'])
        markups = ['<pre>a</pre>', '<code>b</code>', '<p class="c">c</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(filter_content(etree.XML(markup)))

        markups = ['<p><b>a</b>.</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertTrue(filter_content(etree.XML(markup)))
