import unittest
from unittest.mock import patch, MagicMock

from lxml import etree
from ..utils import ns
from ..cache import Paragraph
from ..element import get_string, get_name, Element, Extraction, ElementHandler
from ..engines.base import Base


class TestFunction(unittest.TestCase):
    def test_get_string(self):
        markup = '<div xmlns="http://www.w3.org/1999/xhtml">' \
                 '<p class="a">abc</p> def</div>'
        element = etree.XML(markup).find('x:p', namespaces=ns)
        self.assertEqual(
            '<p xmlns="http://www.w3.org/1999/xhtml" class="a">abc</p>',
            get_string(element, False))
        self.assertEqual('<p class="a">abc</p>', get_string(element, True))

        markup = '<p xmlns:epub="http://www.idpf.org/2007/ops">abc</p>'
        element = etree.XML(markup)
        self.assertEqual(markup, get_string(element, False))
        self.assertEqual('<p>abc</p>', get_string(element, True))

    def test_get_name(self):
        xhtml = '<p xmlns="http://www.w3.org/1999/xhtml">a</p>'
        self.assertEqual('p', get_name(etree.XML(xhtml)))


class TestElement(unittest.TestCase):
    def setUp(self):
        self.xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
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
            <code>App\Http</code> k
        </p>
    </body>
</html>""")
        self.paragraph = self.xhtml.find('.//x:p', namespaces=ns)
        self.element = Element(self.paragraph, 'test', Base.placeholder)

    def test_get_descendents(self):
        elements = self.element.get_descendents(('ruby', 'img'))
        self.assertEqual(8, len(elements))
        self.assertEqual(
            '<ruby>b<rt>B</rt></ruby>', get_string(elements[2], True))

    def test_get_raw(self):
        div = etree.XML('<div xmlns="http://www.w3.org/1999/xhtml">123</div>')
        self.assertEqual('<div>123</div>',
                         Element(div, 'test', Base.placeholder).get_raw())

    def test_get_content(self):
        content = ('{{id_00000}} a {{id_00001}} b c {{id_00002}} d e '
                   '{{id_00003}} f g {{id_00004}} h {{id_00005}} i '
                   '{{id_00006}} {{id_00007}} k')
        self.assertEqual(content, self.element.get_content())

    def test_get_attributes(self):
        self.assertEqual('{"class": "abc"}', self.element.get_attributes())

    def test_add_translation(self):
        self.element.get_content()  # remove rt and reserve images
        translation = ('{{id_00000}} A {{id_00001}} B C {{id_00002}} D E '
                       '{{id_00003}} F G {{id_00004}} H {{id_00005}} I '
                       '{{id_00006}} {{id_00007}} K')
        new = self.element.add_translation(translation)
        translation = ('<p xmlns="http://www.w3.org/1999/xhtml" class="abc">'
                       '<img src="icon.jpg"/> A <img src="w1.jpg"/> '
                       'B C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
                       'F G <img src="w2.jpg"/> H <img src="w3.jpg"/> I '
                       r'<img src="w3.jpg"/> <code>App\Http</code> K</p>')
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


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.page_1 = MagicMock(
            id='a', media_type='text/html', href='test1.xhtml', data=etree.XML(
                b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p class="abc">abc</p>
        <p></p>
    </body>
</html>"""))
        self.page_2 = MagicMock(
            id='b', media_type='text/html', href='test2.xhtml', data=etree.XML(
                b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <div class="abc">abc</div>
        <div></div>
    </body>
</html>"""))
        self.page_3 = MagicMock(media_type='text/css')

        self.extraction = Extraction(
            [self.page_3, self.page_2, self.page_1], Base.placeholder)

    def test_get_sorted_pages(self):
        self.assertEqual(
            [self.page_1, self.page_2], self.extraction.get_sorted_pages())

    def test_get_elements(self):
        self.extraction.rule_mode = 'normal'
        self.extraction.filter_rules = []
        self.extraction.element_rules = []

        elements = self.extraction.get_elements()
        self.assertIsInstance(elements, filter)
        elements = list(elements)
        self.assertEqual(2, len(elements))
        self.assertIsInstance(elements[0], Element)
        self.assertIsInstance(elements[1], Element)

    def test_get_element_rules(self):
        self.extraction.element_rules = [
            'table', 'table.list', 'invalid:class']
        self.assertEqual(4, len(self.extraction.get_element_rules()))

    def test_need_ignore(self):
        self.extraction.element_rules = ['table', 'p.a']

        self.extraction.rules = []
        items = ['<pre xmlns="http://www.w3.org/1999/xhtml">abc</pre>',
                 '<code xmlns="http://www.w3.org/1999/xhtml">abc</code>',
                 '<table xmlns="http://www.w3.org/1999/xhtml">abc</table>',
                 '<p xmlns="http://www.w3.org/1999/xhtml" class="a">abc</p>']
        with self.subTest():
            for item in items:
                self.assertTrue(self.extraction.need_ignore(etree.XML(item)))

        items = ['<p xmlns="http://www.w3.org/1999/xhtml">abc</p>',
                 '<p xmlns="http://www.w3.org/1999/xhtml" id="a">abc</p>']
        with self.subTest():
            for item in items:
                self.assertFalse(self.extraction.need_ignore(etree.XML(item)))

    def test_extract_elements(self):
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
            <p><span>123</span><strong>789</strong></p>
        </div>
    </div>
</body>
</html>""")
        root = xhtml.find('x:body', namespaces=ns)
        self.assertEqual(
            7, len(self.extraction.extract_elements('test', root, [])))

        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>123456789</body>
</html>""")
        root = xhtml.find('x:body', namespaces=ns)
        self.assertEqual(
            1, len(self.extraction.extract_elements('test', root, [])))

    def test_filter_content(self):
        self.extraction.element_rules = []
        self.extraction.rule_mode = 'normal'
        self.extraction.filter_scope = 'text'
        self.extraction.filter_rules = []

        def element(markup):
            return Element(etree.XML(markup), 'test', Base.placeholder)

        # normal:text
        markups = ['<p></p>', '<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>',
                   '<p> </p>', '<p>”.</p>', '<p>‘’</p>', '<p>2 &lt;= 2</p>',
                   '<p><span>  </span><span>  </span></p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(
                    self.extraction.filter_content(element(markup)))

        self.extraction.filter_rules = ['a', 'b', 'c']
        markups = ['<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(
                    self.extraction.filter_content(element(markup)))

        self.extraction.filter_rules = ['A', 'B', 'C']
        markups = ['<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(
                    self.extraction.filter_content(element(markup)))

        # case:text
        self.extraction.rule_mode = 'case'
        markups = ['<p>xxxAxxx</p>', '<p>xxxBxxx</p>', '<p>xxxCxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(
                    self.extraction.filter_content(element(markup)))

        self.extraction.filter_rules = ['a', 'b', 'c']
        markups = ['<p>xxxAxxx</p>', '<p>xxxBxxx</p>', '<p>xxxCxxx</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertTrue(
                    self.extraction.filter_content(element(markup)))

        # regex:text
        self.extraction.rule_mode = 'regex'
        self.extraction.filter_rules = ['^.*?a', 'f.*$', '[^z]']
        markups = ['<p>5.</p>', '<p>5-5.</p>', '<p>5-5_5.</p>',
                   '<p>abc</p>', '<p>def</p>', '<p>ghi</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(
                    self.extraction.filter_content(element(markup)))

        # regex:html
        self.extraction.rule_mode = 'regex'
        self.extraction.filter_scope = 'html'
        self.extraction.filter_rules = [
            '^<pre>', '^.*</code>$', '^.*?class="c"']
        markups = ['<pre>a</pre>', '<code>b</code>', '<p class="c">c</p>',
                   '<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>', '<p></p>',
                   '<p> </p>', '<p>”.</p>', '<p>‘’</p>', '<p>2 &lt;= 2</p>',
                   '<p><span>123</span></p>',
                   '<p><span>  </span><span>  </span></p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertFalse(
                    self.extraction.filter_content(element(markup)))

        markups = ['<p><b>a</b>.</p>']
        for markup in markups:
            with self.subTest(markup=markup):
                self.assertTrue(
                    self.extraction.filter_content(element(markup)))


class TestElementHandler(unittest.TestCase):
    def setUp(self):
        self.xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p class="a">a</p>
        <p name="b">b</p>
        <p id="c">c</p>
    </body>
</html>""")
        self.elements = [Element(element, 'test', Base.placeholder) for element
                         in self.xhtml.findall('.//x:p', namespaces=ns)]
        self.handler = ElementHandler()

    @patch('calibre_plugins.ebook_translator.element.uid')
    def test_prepare_original(self, mock_uid):
        mock_uid.side_effect = ['m1', 'm2', 'm3']
        self.assertEqual(
            [(0, 'm1', '<p class="a">a</p>', 'a', '{"class": "a"}', 'test'),
             (1, 'm2', '<p name="b">b</p>', 'b', '{"name": "b"}', 'test'),
             (2, 'm3', '<p id="c">c</p>', 'c', '{"id": "c"}', 'test')],
            self.handler.prepare_original(self.elements))

    @patch('calibre_plugins.ebook_translator.element.uid')
    def test_prepare_original_merged(self, mock_uid):
        mock_uid.return_value = 'm1'
        self.handler.merge_length = 1000
        self.assertEqual([(
            0, 'm1', '<p class="a">a</p><p name="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_2}} ')],
            self.handler.prepare_original(self.elements))

    def test_add_translations(self):
        self.handler.prepare_original(self.elements)
        self.handler.add_translations(
            [Paragraph(0, 'm1', '<p>a</p>', 'a', 'A', 'Google', 'Chinese'),
             Paragraph(1, 'm2', '<p>b</p>', 'b', 'B', 'Google', 'Chinese'),
             Paragraph(2, 'm3', '<p>c</p>', 'c', 'C', 'Google', 'Chinese')])

        self.assertEqual(6, len(self.xhtml.findall('.//x:p', namespaces=ns)))

    def test_add_translations_merged(self):
        self.handler.merge_length = 1000
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p class="a">a</p><p name="b">b</p><p id="c">c</p>',
            None, None, 'a {{id_0}} b {{id_1}} c {{id_2}} ',
            'A {{id_0}} B {{id_1}} C {{id_2}} ')])

        self.assertEqual(6, len(self.xhtml.findall('.//x:p', namespaces=ns)))
