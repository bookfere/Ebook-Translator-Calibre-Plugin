import unittest
from unittest.mock import patch

from lxml import etree
from calibre_plugins.ebook_translator.utils import ns
from calibre_plugins.ebook_translator.element import (
    get_string, get_name, Element, ElementHandler)
from calibre_plugins.ebook_translator.engines.base import Base


class TestElement(unittest.TestCase):
    def setUp(self):
        xhtml = etree.XML("""
<html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Test Document</title></head>
    <body>
        <p class="abc">
            <img src="icon.jpg"/> a <img src="w1.jpg"/>
            <ruby>b<rt>B</rt></ruby> c
            <span><img src="w2.jpg"/> d</span>
            <span>e <img src="w2.jpg"/></span> f
            <span>g <img src="w2.jpg"/> h</span>
            <img src="w3.jpg"/> i
            <img src="w3.jpg"/>
        </p>
    </body>
</html>""")
        self.paragraph = xhtml.find('.//x:p', namespaces=ns)
        self.element = Element(self.paragraph, Base.placeholder)

    def test_get_string(self):
        markup = '<p xmlns="http://www.w3.org/1999/xhtml" class="a">abc</p>'
        element = etree.XML(markup)
        self.assertEqual(markup, get_string(element, False))
        self.assertEqual('<p class="a">abc</p>', get_string(element, True))

        markup = '<p xmlns:epub="http://www.idpf.org/2007/ops">abc</p>'
        element = etree.XML(markup)
        self.assertEqual(markup, get_string(element, False))
        self.assertEqual('<p>abc</p>', get_string(element, True))

    def test_get_name(self):
        xhtml = '<p xmlns="http://www.w3.org/1999/xhtml">a</p>'
        self.assertEqual('p', get_name(etree.XML(xhtml)))

    def test_get_content(self):
        content = ('{{id_10000}} a {{id_10001}} b c {{id_10002}} d e '
                   '{{id_10003}} f g {{id_10004}} h {{id_10005}} i '
                   '{{id_10006}}')
        self.assertEqual(content, self.element.get_content())

    def test_add_translation(self):
        self.element.get_content()  # remove rt and reserve images
        translation = ('{{id_10000}} A {{id_10001}} B C {{id_10002}} D E '
                       '{{id_10003}} F G {{id_10004}} H {{id_10005}} I '
                       '{{id_10006}}')
        new = self.element.add_translation(translation)
        translation = ('<p xmlns="http://www.w3.org/1999/xhtml" class="abc">'
                       '<img src="icon.jpg"/> A <img src="w1.jpg"/> '
                       'B C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
                       'F G <img src="w2.jpg"/> H <img src="w3.jpg"/> I '
                       '<img src="w3.jpg"/></p>')
        self.assertEqual(translation, get_string(new))
        self.assertIsNone(new.get('lang'))
        self.assertIsNone(new.get('style'))
        self.assertEqual('abc', new.get('class'))

    def test_add_translation_next(self):
        new = self.element.add_translation('test', position='next')
        self.assertEqual(self.paragraph, new.getprevious())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_before(self):
        new = self.element.add_translation('test', position='before')
        self.assertEqual(self.paragraph, new.getnext())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_only(self):
        new = self.element.add_translation('test', position='only')
        self.assertIsNone(new.getprevious())
        self.assertIsNone(new.getnext())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_attr(self):
        new = self.element.add_translation('a', lang='zh', color='red')
        self.assertEqual('zh', new.get('lang'))
        self.assertEqual('color:red', new.get('style'))


class TestElementHandler(unittest.TestCase):
    def setUp(self):
        self.xhtml = etree.XML("""
<html xmlns="http://www.w3.org/1999/xhtml">
    <head><title>Test Document</title></head>
    <body>
        <p>a</p>
        <p>b</p>
        <p>c</p>
    </body>
</html>""")
        self.paragraphs = self.xhtml.findall('.//x:p', namespaces=ns)
        self.handler = ElementHandler(self.paragraphs, Base.placeholder)

    @patch('calibre_plugins.ebook_translator.element.uid')
    def test_get_original(self, mock_uid):
        mock_uid.side_effect = ['1', '2', '3']
        self.assertEqual([('1', 'a'), ('2', 'b'), ('3', 'c')],
                         self.handler.get_original())

    @patch('calibre_plugins.ebook_translator.element.uid')
    def test_get_original_merged(self, mock_uid):
        mock_uid.side_effect = ['1']
        self.handler.merge_length = 1000
        self.assertEqual([('1', 'a {{id_0}} b {{id_1}} c {{id_2}} ')],
                         self.handler.get_original())

    def test_add_transation(self):
        self.handler.add_translation('a')
        self.handler.add_translation('b')
        self.handler.add_translation('c')

        self.assertEqual(['a', 'b', 'c'], self.handler.translation)

    def test_apply_translation(self):
        self.handler.translation = ['A', 'B', 'C']
        self.handler.apply_translation()

        self.assertEqual(6, len(self.xhtml.findall('.//x:p', namespaces=ns)))

    def test_apply_translation_merged(self):
        self.handler.merge_length = 1000
        self.handler.translation = ['a {{id_0}} b {{id_1}} c {{id_2}} ']
        self.handler.apply_translation()

        self.assertEqual(6, len(self.xhtml.findall('.//x:p', namespaces=ns)))
