import unittest
from unittest.mock import patch, Mock

from lxml import etree
from ..lib.utils import ns
from ..lib.cache import Paragraph
from ..lib.element import (
    get_string, get_name, Element, Extraction, ElementHandler)
from ..engines import DeeplFreeTranslate
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
            <img alt="{\D}" src="w3.jpg"/> i
            <img src="w3.jpg"/>
            <code>App\Http</code> k
        </p>
    </body>
</html>""")
        self.paragraph = self.xhtml.find('.//x:p', namespaces=ns)
        self.element = Element(self.paragraph, 'p1')

    def test_get_name(self):
        self.assertEqual('p', self.element.get_name())

    def test_get_descendents(self):
        elements = self.element.get_descendents(('ruby', 'img'))
        self.assertEqual(8, len(elements))
        self.assertEqual(
            '<ruby>b<rt>B</rt></ruby>', get_string(elements[2], True))

    def test_get_raw(self):
        text = (
            '<p class="abc"> <img src="icon.jpg"/> a <img src="w1.jpg"/> '
            '<ruby>b<rt>B</rt></ruby> c <span><img src="w2.jpg"/> d</span> '
            '<span>e <img src="w2.jpg"/></span> f <span>g <img src="w2.jpg"/> '
            r'h</span> <img alt="{\D}" src="w3.jpg"/> i <img src="w3.jpg"/> '
            r'<code>App\Http</code> k </p>')
        self.assertEqual(text, self.element.get_raw())

    def test_get_text(self):
        self.assertEqual(
            r'a bB c d e f g h i App\Http k', self.element.get_text())

    def test_get_content(self):
        content = ('{{id_00000}} a {{id_00001}} b c {{id_00002}} d e '
                   '{{id_00003}} f g {{id_00004}} h {{id_00005}} i '
                   '{{id_00006}} {{id_00007}} k')
        self.assertEqual(content, self.element.get_content(Base.placeholder))
        self.assertEqual(8, len(self.element.reserve_elements))

        for element in self.element.reserve_elements:
            with self.subTest(element=element):
                self.assertIsNone(element.tail)

    def test_get_attributes(self):
        self.assertEqual('{"class": "abc"}', self.element.get_attributes())

    def test_add_translation(self):
        self.element.get_content(Base.placeholder)
        translation = ('{{id_00000}} A {{id_00001}} B C {{id_00002}} D E '
                       '{{id_00003}} F G {{id_00004}} H {{id_00005}} I '
                       '{{id_00006}} {{id_00007}} K')
        new = self.element.add_translation(translation, Base.placeholder)
        translation = ('<p xmlns="http://www.w3.org/1999/xhtml" class="abc">'
                       '<img src="icon.jpg"/> A <img src="w1.jpg"/> '
                       r'B C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
                       'F G <img src="w2.jpg"/> H '
                       r'<img alt="{\D}" src="w3.jpg"/> I '
                       r'<img src="w3.jpg"/> <code>App\Http</code> K</p>')
        self.assertEqual(translation, get_string(new))
        self.assertIsNone(new.get('lang'))
        self.assertIsNone(new.get('style'))
        self.assertEqual('abc', new.get('class'))

    def test_add_translation_with_markup(self):
        self.element.get_content(DeeplFreeTranslate.placeholder)
        translation = ('<m id=00000 /> A <m id=00001 /> B C <m id=00002 /> D '
                       'E <m id=00003 /> F G <m id=00004 /> H <m id=00005 /> '
                       'I <m id=00006 /> <m id=00007 /> K')
        new = self.element.add_translation(
            translation, DeeplFreeTranslate.placeholder)
        translation = ('<p xmlns="http://www.w3.org/1999/xhtml" class="abc">'
                       '<img src="icon.jpg"/> A <img src="w1.jpg"/> '
                       'B C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
                       'F G <img src="w2.jpg"/> H '
                       r'<img alt="{\D}" src="w3.jpg"/> I '
                       r'<img src="w3.jpg"/> <code>App\Http</code> K</p>')
        self.assertEqual(translation, get_string(new))

    def test_add_translation_next(self):
        new = self.element.add_translation(
            'test', Base.placeholder, position='next')
        self.assertEqual(self.paragraph, new.getprevious())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_before(self):
        new = self.element.add_translation(
            'test', Base.placeholder, position='before')
        self.assertEqual(self.paragraph, new.getnext())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_only(self):
        new = self.element.add_translation(
            'test', Base.placeholder, position='only')
        self.assertIsNone(new.getprevious())
        self.assertIsNone(new.getnext())
        self.assertIn('>test<', get_string(new))

        # Test for the anchor element that is a sibling of the paragraph.
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <a></a>
        <a href="abc">a</a>
    </body>
</html>""")

        element = Element(xhtml.find('.//x:a[1]', namespaces=ns), 'p1')
        new = element.add_translation('A', Base.placeholder, position='only')
        self.assertIsNone(new.get('href'))

        element = Element(xhtml.find('.//x:a[2]', namespaces=ns), 'p1')
        new = element.add_translation('A', Base.placeholder, position='only')
        self.assertEqual('abc', new.get('href'))

    def test_add_translation_attr(self):
        new = self.element.add_translation(
            'test', Base.placeholder, lang='zh', color='red')
        self.assertEqual('zh', new.get('lang'))
        self.assertEqual('color:red', new.get('style'))


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.page_1 = Mock(
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
        self.page_2 = Mock(
            id='b', media_type='text/html', href='test2.xhtml', data=etree.XML(
                b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <div class="def">def</div>
        <div></div>
    </body>
</html>"""))
        self.page_3 = Mock(media_type='text/css')

        self.extraction = Extraction(
            [self.page_3, self.page_2, self.page_1], 'normal', 'text', [], [])

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
        self.assertEqual('p', get_name(elements[0].get_name()))
        self.assertEqual('abc', elements[0].get_content(Base.placeholder))
        self.assertIsInstance(elements[1], Element)
        self.assertEqual('div', get_name(elements[1].get_name()))
        self.assertEqual('def', elements[1].get_content(Base.placeholder))

    def test_load_filter_patterns(self):
        self.extraction.load_filter_patterns()
        self.assertEqual(1, len(self.extraction.filter_patterns))

        self.extraction.filter_rules = ['^a', 'b$']
        self.extraction.load_filter_patterns()
        self.assertEqual(3, len(self.extraction.filter_patterns))

    def test_load_element_patterns(self):
        self.extraction.load_element_patterns()
        self.assertEqual(2, len(self.extraction.element_patterns))

        self.extraction.element_rules = [
            'table', 'table.list', 'invalid:class']
        self.extraction.load_element_patterns()
        self.assertEqual(4, len(self.extraction.element_patterns))

    def test_need_ignore(self):
        self.extraction.element_rules = ['table', 'p.a']
        self.extraction.load_element_patterns()

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
            7, len(self.extraction.extract_elements('p1', root, [])))

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
        def elements(markups):
            return [Element(etree.XML(markup), 'test') for markup in markups]

        # normal - text
        markups = ['<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>',
                   '<p></p>', '<p> </p>', '<p><img src="/abc.jpg" /></p>',
                   '<p><span>  </span><span>  </span></p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.assertFalse(self.extraction.filter_content(element))

        self.extraction.filter_rules = ['a', 'b', 'c']
        self.extraction.load_filter_patterns()
        markups = ['<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>',
                   '<p>2 &lt;= 2</p>', '<p>”.—…‘’</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.assertTrue(self.extraction.filter_content(element))
                self.assertTrue(element.ignored)

        self.extraction.filter_rules = ['A', 'B', 'C']
        markups = ['<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.extraction.filter_content(element)
                self.assertTrue(element.ignored)

        # case - text
        self.extraction.rule_mode = 'case'
        markups = ['<p>xxxAxxx</p>', '<p>xxxBxxx</p>', '<p>xxxCxxx</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.extraction.filter_content(element)
                self.assertTrue(element.ignored)

        self.extraction.filter_rules = ['a', 'b', 'c']
        self.extraction.load_filter_patterns()
        markups = ['<p>xxxAxxx</p>', '<p>xxxBxxx</p>', '<p>xxxCxxx</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.extraction.filter_content(element)
                self.assertFalse(element.ignored)

        # regex - text
        self.extraction.rule_mode = 'regex'
        self.extraction.filter_rules = ['a', 'f', 'h']
        self.extraction.load_filter_patterns()
        markups = ['<p>5.</p>', '<p>5-5.</p>', '<p>5-5_5.</p>',
                   '<p>abc</p>', '<p>def</p>', '<p>ghi</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.extraction.filter_content(element)
                self.assertTrue(element.ignored)

        # regex - html
        self.extraction.rule_mode = 'regex'
        self.extraction.filter_scope = 'html'
        self.extraction.filter_rules = ['^<pre>', '</code>$', 'class="c"']
        self.extraction.load_filter_patterns()
        markups = ['<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>',
                   '<p></p>', '<p> </p>', '<p><img src="/abc.jpg" /></p>',
                   '<p><span>  </span><span>  </span></p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.assertFalse(self.extraction.filter_content(element))

        markups = ['<pre>a</pre>', '<code>b</code>', '<p class="c">c</p>',
                   '<p>2 &lt;= 2</p>', '<p><span>123</span></p>',
                   '<p>”.—…‘’</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.assertTrue(self.extraction.filter_content(element))
                self.assertTrue(element.ignored)


class TestElementHandler(unittest.TestCase):
    def setUp(self):
        self.xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p id="a">a</p>
        <p id="b">b</p>
        <p><img src="abc.jpg" /></p>
        <p id="c" class="c">c</p>
        <p></p>
    </body>
</html>""")

        self.elements = [
            Element(element, 'p1') for element
            in self.xhtml.findall('./x:body/*', namespaces=ns)]
        self.elements[-1].set_ignored(True)
        self.elements[-3].set_ignored(True)
        self.handler = ElementHandler(Base.placeholder)

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_original(self, mock_uid):
        mock_uid.side_effect = ['m1', 'm2', 'm3', 'm4', 'm5']
        self.assertEqual([
            (0, 'm1', '<p id="a">a</p>', 'a', False, '{"id": "a"}', 'p1'),
            (1, 'm2', '<p id="b">b</p>', 'b', False, '{"id": "b"}', 'p1'),
            (2, 'm3', '<p><img src="abc.jpg"/></p>', '{{id_00000}}', True,
             None, 'p1'),
            (3, 'm4', '<p id="c" class="c">c</p>', 'c', False,
             '{"id": "c", "class": "c"}', 'p1'),
            (4, 'm5', '<p></p>', '', True, None, 'p1')],
            self.handler.prepare_original(self.elements))

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_original_merged(self, mock_uid):
        mock_uid.return_value = 'm1'
        self.handler.merge_length = 1000
        self.assertEqual([(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c" class="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}} ', False)],
            self.handler.prepare_original(self.elements))

    def test_add_translations(self):
        self.handler.prepare_original(self.elements)
        translations = [
            Paragraph(0, 'm1', '<p id="a">a</p>', 'a', False, '{"id": "a"}',
                      'p1', 'A', 'ENGINE', 'LANG'),
            Paragraph(1, 'm2', '<p id="b">b</p>', 'b', False, '{"id": "b"}',
                      'p1', 'B', 'ENGINE', 'LANG'),
            Paragraph(3, 'm3', '<p id="c">c</p>', 'c', False,
                      '{"id": "c", "class": "c"}', 'p1', 'C', 'ENGINE',
                      'LANG')]

        self.handler.add_translations(translations)

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(8, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('A', elements[1].text)
        self.assertEqual('b', elements[2].text)
        self.assertEqual('B', elements[3].text)

        self.assertEqual('c', elements[5].text)
        self.assertEqual('C', elements[6].text)
        self.assertIsNone(elements[6].get('id'))
        self.assertEqual('c', elements[6].get('class'))

    def test_add_translations_translation_only(self):
        self.handler.position = 'only'

        self.handler.prepare_original(self.elements)
        self.handler.add_translations([
            Paragraph(0, 'm1', '<p id="a">a</p>', 'a', False, '{"id": "a"}',
                      'p1', 'A', 'ENGINE', 'LANG'),
            Paragraph(1, 'm2', '<p id="b">b</p>', 'b', False, '{"id": "b"}',
                      'p1', 'B', 'ENGINE', 'LANG'),
            Paragraph(3, 'm3', '<p id="c">c</p>', 'c', False,
                      '{"id": "c", "class": "c"}', 'p1', 'C', 'ENGINE',
                      'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(5, len(elements))
        self.assertEqual('A', elements[0].text)
        self.assertEqual('a', elements[0].get('id'))
        self.assertEqual('B', elements[1].text)
        self.assertEqual('b', elements[1].get('id'))
        self.assertEqual('C', elements[3].text)
        self.assertEqual('c', elements[3].get('id'))
        self.assertEqual('c', elements[3].get('class'))

    def test_add_translations_merged(self):
        self.handler.merge_length = 1000
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A {{id_0}} B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(8, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('A', elements[1].text)
        self.assertEqual('b', elements[2].text)
        self.assertEqual('B', elements[3].text)

        self.assertEqual('c', elements[5].text)
        self.assertEqual('C', elements[6].text)

    def test_add_translations_merged_missing_id(self):
        self.handler.merge_length = 1000
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(7, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('b', elements[1].text)
        self.assertEqual('A B', elements[2].text)

        self.assertEqual('c', elements[4].text)
        self.assertEqual('C', elements[5].text)

    def test_add_translations_merged_translation_only(self):
        self.handler.position = 'only'

        self.handler.merge_length = 1000
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>'
            '<a href="/a">a</a>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A {{id_0} B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(5, len(elements))
        self.assertEqual('A', elements[0].text)
        self.assertEqual('B', elements[1].text)

        self.assertEqual('C', elements[3].text)

    def test_add_translations_merged_translation_only_missing_id(self):
        self.handler.position = 'only'

        self.handler.merge_length = 1000
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>'
            '<a href="/a">a</a>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(4, len(elements))
        self.assertEqual('A B', elements[0].text)

        self.assertEqual('C', elements[2].text)
