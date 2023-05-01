import unittest

from lxml import etree

from calibre_plugins.ebook_translator.utils import ns
from calibre_plugins.ebook_translator.element import get_string, Element
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

    def test_get_content(self):
        content = ('{{id_r0}} a {{id_r1}} b c {{id_r2}} d e {{id_r3}} f '
                   'g {{id_r4}} h {{id_r5}} i {{id_r6}}')
        self.assertEqual(content, self.element.get_content())

    def test_add_translation(self):
        self.element.get_content()  # remove rt and reserve images
        translation = ('{{id_r0}} A {{id_r1}} B C {{id_r2}} D E {{id_r3}} F '
                       'G {{id_r4}} H {{id_r5}} I {{id_r6}}')
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
