import unittest
from unittest.mock import patch, Mock

from lxml import etree

from calibre.ebooks.oeb.base import TOC, Metadata

from ..lib.utils import ns
from ..lib.cache import Paragraph
from ..lib.element import (
    get_string, get_name, Extraction, ElementHandler, ElementHandlerMerge,
    Element, SrtElement, TocElement, PageElement, MetadataElement,
    get_toc_elements, get_metadata_elements)
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

    def test_get_toc_elements(self):
        toc = TOC()
        toc.add('a', 'a.html')
        toc.nodes[0].add('b', 'b.html')
        toc.nodes[0][0].add('c', 'c.html')

        elements = get_toc_elements(toc, [])
        self.assertEqual(3, len(elements))

        elements = get_toc_elements(toc, [])
        self.assertEqual(3, len(elements))

    def test_get_metadata_elements(self):
        metadata = Mock(Metadata)
        item_1 = Mock(Metadata.Item, content='a')
        item_2 = Mock(Metadata.Item, content='b')
        item_3 = Mock(Metadata.Item, content='0')
        metadata.title = [item_1]
        metadata.subject = [item_2, item_3]
        metadata.language = []
        metadata.iterkeys.return_value = ['title', 'subject', 'language']

        elements = get_metadata_elements(metadata)

        self.assertEqual(2, len(elements))
        self.assertIs(item_1, elements[0].element)
        self.assertIs(item_2, elements[1].element)


class MockedElement(Element):
    def get_raw(self):
        pass

    def get_text(self):
        pass

    def get_content(self):
        pass

    def add_translation(
            self, translation, placeholder, position, translation_lang=None,
            original_color=None, translation_color=None):
        pass


class TestElement(unittest.TestCase):
    def setUp(self):
        self._element = Mock()
        self.element = MockedElement(self._element, 'toc.ncx')

    def test_create_element(self):
        self.assertIs(self._element, self.element.element)
        self.assertEqual('toc.ncx', self.element.page_id)
        self.assertFalse(self.element.ignored)
        self.assertIsNone(self.element.placeholder)
        self.assertEqual([], self.element.reserve_elements)
        self.assertEqual([], self.element.original)

    def test_set_ignored(self):
        self.element.set_ignored(True)
        self.assertTrue(self.element.ignored)

    def test_set_placeholder(self):
        self.element.set_placeholder(['{{id_{}}}', r'{id_\d+}'])
        self.assertEqual(['{{id_{}}}', r'{id_\d+}'], self.element.placeholder)

    def test_get_name(self):
        self.assertIsNone(self.element.get_name())

    def test_get_attributes(self):
        self.assertIsNone(self.element.get_name())

    def test_delete(self):
        self.assertIsNone(self.element.delete())

    def test_get_translation(self):
        self.assertIsNone(self.element.get_translation())


class TestSrtElement(unittest.TestCase):
    def setUp(self):
        self.element = SrtElement(['1', '00:01 --> 00:02', 'a'])

    def test_get_raw(self):
        self.assertEqual('a', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_none(self):
        element = self.element.add_translation(None, 'below')
        self.assertEqual('a', element[2])

    def test_add_translation_below(self):
        element = self.element.add_translation('A', 'below')
        self.assertEqual('a\nA', element[2])

    def test_add_translation_right(self):
        element = self.element.add_translation('A', 'right')
        self.assertEqual('a\nA', element[2])

    def test_add_translation_above(self):
        element = self.element.add_translation('A', 'above')
        self.assertEqual('A\na', element[2])

    def test_add_translation_left(self):
        element = self.element.add_translation('A', 'left')
        self.assertEqual('A\na', element[2])

    def test_add_translation_only(self):
        element = self.element.add_translation('A', 'only')
        self.assertEqual('A', element[2])


class TestMetadataElement(unittest.TestCase):
    def setUp(self):
        self.medata_item = Mock(Metadata.Item, content='a')
        self.element = MetadataElement(self.medata_item)

    def test_get_raw(self):
        self.assertEqual('a', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_none(self):
        self.assertIs(
            self.element.element,
            self.element.add_translation(None, 'below'))

    def test_add_translation_below(self):
        element = self.element.add_translation('A', 'below')
        self.assertEqual('a A', element.content)

    def test_add_translation_right(self):
        element = self.element.add_translation('A', 'right')
        self.assertEqual('a A', element.content)

    def test_add_translation_above(self):
        element = self.element.add_translation('A', 'above')
        self.assertEqual('A a', element.content)

    def test_add_translation_left(self):
        element = self.element.add_translation('A', 'left')
        self.assertEqual('A a', element.content)

    def test_add_translation_only(self):
        element = self.element.add_translation('A', 'only')
        self.assertEqual('A', element.content)


class TestTocElement(unittest.TestCase):
    def setUp(self):
        self.element = TocElement(TOC('a', 'a.html'), 'toc.ncx')

    def test_get_raw(self):
        self.assertEqual('a', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_none(self):
        element = self.element.add_translation(None, 'below')
        self.assertEqual('a', element.title)

    def test_add_translation_below(self):
        element = self.element.add_translation('A', 'below')
        self.assertEqual('a A', element.title)

    def test_add_translation_right(self):
        element = self.element.add_translation('A', 'right')
        self.assertEqual('a A', element.title)

    def test_add_translation_above(self):
        element = self.element.add_translation('A', 'above')
        self.assertEqual('A a', element.title)

    def test_add_translation_left(self):
        element = self.element.add_translation('A', 'left')
        self.assertEqual('A a', element.title)

    def test_add_translation_only(self):
        element = self.element.add_translation('A', 'only')
        self.assertEqual('A', element.title)


class TestPageElement(unittest.TestCase):
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
            <code>App\Http</code> k<br/>l
        </p>
    </body>
</html>""")
        self.paragraph = self.xhtml.find('.//x:p', namespaces=ns)
        self.element = PageElement(self.paragraph, 'p1')
        self.element.set_placeholder(Base.placeholder)

    def test_get_name(self):
        self.assertEqual('p', self.element.get_name())

    # def test_get_descendents(self):
    #     elements = self.element.get_descendents(('ruby', 'img'))
    #     self.assertEqual(8, len(elements))
    #     self.assertEqual(
    #         '<ruby>b<rt>B</rt></ruby>', get_string(elements[2], True))

    def test_get_raw(self):
        text = (
            '<p class="abc"> <img src="icon.jpg"/> a <img src="w1.jpg"/> '
            '<ruby>b<rt>B</rt></ruby> c <span><img src="w2.jpg"/> d</span> '
            '<span>e <img src="w2.jpg"/></span> f <span>g <img src="w2.jpg"/> '
            r'h</span> <img alt="{\D}" src="w3.jpg"/> i <img src="w3.jpg"/> '
            r'<code>App\Http</code> k<br/>l </p>')
        self.assertEqual(text, self.element.get_raw())

    def test_get_text(self):
        self.assertEqual(
            r'a bB c d e f g h i App\Http kl', self.element.get_text())

    def test_get_content(self):
        raw_content = self.element.get_raw()
        content = ('{{id_00000}} a {{id_00001}} b c {{id_00002}} d e '
                   '{{id_00003}} f g {{id_00004}} h {{id_00005}} i '
                   '{{id_00006}} {{id_00007}} k{{id_00008}}l')
        self.assertEqual(content, self.element.get_content())
        self.assertEqual(9, len(self.element.reserve_elements))
        self.assertEqual(raw_content, self.element.get_raw())

        for element in self.element.reserve_elements:
            with self.subTest(element=element):
                self.assertIsNone(element.tail)

    def test_get_attributes(self):
        self.assertEqual('{"class": "abc"}', self.element.get_attributes())

    def test_add_translation_none(self):
        element = self.element.add_translation(None, 'below')
        self.assertIs(element, self.element.element)

    def test_add_translation_none_with_left_position(self):
        element = self.element.add_translation(None, 'left')
        self.assertIs(element, self.element.element)
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)

    def test_add_translation_with_placeholder(self):
        self.element.set_placeholder(Base.placeholder)
        self.element.get_content()
        translation = ('{{id_00000}} Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa '
                       '{{id_00001}} Bbbbbbbbbbbbbbb C {{id_00002}} D E '
                       '{{id_00003}} F G {{id_00004}} H \n\n{{id_00005}} I '
                       '{{id_00006}} {{id_00007}} K{ { id _ 0 00 08 } }L')
        new = self.element.add_translation(translation, position='below')
        translation = ('<p xmlns="http://www.w3.org/1999/xhtml" class="abc">'
                       '<img src="icon.jpg"/> Aaaaa <img src="w1.jpg"/> '
                       'Bbbbb C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
                       'F G <img src="w2.jpg"/> H <br/><br/>'
                       r'<img alt="{\D}" src="w3.jpg"/> I '
                       r'<img src="w3.jpg"/> <code>App\Http</code> '
                       'K<br/>L</p>')
        self.assertEqual(translation, get_string(new))
        self.assertIsNone(new.get('lang'))
        self.assertIsNone(new.get('style'))
        self.assertEqual('abc', new.get('class'))

    def test_add_translation_with_markup(self):
        self.element.set_placeholder(DeeplFreeTranslate.placeholder)
        self.element.get_content()
        translation = ('<m id=00000 /> A <m id=00001 /> B C <m id=00002 /> D '
                       'E <m id=00003 /> F G <m id=00004 /> H <m id=00005 /> '
                       'I <m id=00006 /> <m id=00007 /> K<m id=00008 />L')
        new = self.element.add_translation(translation, position='below')
        translation = ('<p xmlns="http://www.w3.org/1999/xhtml" class="abc">'
                       '<img src="icon.jpg"/> A <img src="w1.jpg"/> '
                       'B C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
                       'F G <img src="w2.jpg"/> H '
                       r'<img alt="{\D}" src="w3.jpg"/> I '
                       r'<img src="w3.jpg"/> <code>App\Http</code> '
                       'K<br/>L</p>')
        self.assertEqual(translation, get_string(new))

    def test_add_translation_below(self):
        new = self.element.add_translation('test', position='next')
        self.assertEqual(self.paragraph, new.getprevious())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_right(self):
        new = self.element.add_translation('test', position='right')
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)
        self.assertIn('>test<', get_string(new))

    def test_add_translation_above(self):
        new = self.element.add_translation('test',  position='above')
        self.assertEqual(self.paragraph, new.getnext())
        self.assertIn('>test<', get_string(new))

    def test_add_translation_left(self):
        new = self.element.add_translation('test', position='left')
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)
        self.assertIn('>test<', get_string(new))

    def test_add_translation_only(self):
        new = self.element.add_translation('test', position='only')
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

        element = PageElement(xhtml.find('.//x:a[1]', namespaces=ns), 'p1')
        new = element.add_translation('A', position='only')
        self.assertIsNone(new.get('href'))

        element = PageElement(xhtml.find('.//x:a[2]', namespaces=ns), 'p1')
        new = element.add_translation('A', position='only')
        self.assertEqual('abc', new.get('href'))

    def test_add_translation_attr(self):
        new = self.element.add_translation(
            'test', position='below', translation_lang='zh',
            original_color='green', translation_color='red')
        self.assertEqual('zh', new.get('lang'))
        self.assertEqual('color:green', self.element.element.get('style'))
        self.assertEqual('color:red', new.get('style'))


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.page_1 = Mock(
            id='a', media_type='text/html', href='test1.htm', data=etree.XML(
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
        self.page_3 = Mock(
            id="c", media_type='image/svg+xml', href='test.svg',
            data=etree.XML(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'))

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
        self.assertIsInstance(elements[0], PageElement)
        self.assertEqual('p', get_name(elements[0].get_name()))
        self.assertEqual('abc', elements[0].get_content())
        self.assertIsInstance(elements[1], PageElement)
        self.assertEqual('div', get_name(elements[1].get_name()))
        self.assertEqual('def', elements[1].get_content())

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

        for item in items:
            with self.subTest(item=item):
                self.assertTrue(self.extraction.need_ignore(etree.XML(item)))

        items = ['<p xmlns="http://www.w3.org/1999/xhtml">abc</p>',
                 '<p xmlns="http://www.w3.org/1999/xhtml" id="a">abc</p>']

        for item in items:
            with self.subTest(item=item):
                self.assertFalse(self.extraction.need_ignore(etree.XML(item)))

    def test_extract_elements(self):
        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>
    <div>
        <div>
            <h2><a>title</a></h2>
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
        elements = self.extraction.extract_elements('p1', root, [])
        self.assertEqual(8, len(elements))
        self.assertEqual('h2', elements[0].get_name())
        self.assertEqual('p', elements[-1].get_name())

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
            return [
                PageElement(etree.XML(markup), 'test') for markup in markups]

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
            PageElement(element, 'p1') for element
            in self.xhtml.findall('./x:body/*', namespaces=ns)]
        self.elements[-1].set_ignored(True)
        self.elements[-3].set_ignored(True)
        self.handler = ElementHandler(
            Base.placeholder, Base.separator, 'below')

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

    def test_add_translations(self):
        self.handler.prepare_original(self.elements)
        translations = [
            Paragraph(0, 'm1', '<p id="x">x</p>', 'x', False, '{"id": "x"}',
                      'p1', None, 'ENGINE', 'LANG'),
            Paragraph(1, 'm1', '<p id="a">a</p>', 'a', False, '{"id": "a"}',
                      'p1', 'A', 'ENGINE', 'LANG'),
            Paragraph(2, 'm2', '<p id="b">b</p>', 'b', False, '{"id": "b"}',
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


class TestElementHandlerMerge(unittest.TestCase):
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
            PageElement(element, 'p1') for element
            in self.xhtml.findall('./x:body/*', namespaces=ns)]
        self.elements[-1].set_ignored(True)
        self.elements[-3].set_ignored(True)
        self.handler = ElementHandlerMerge(
            Base.placeholder, Base.separator, 'below', 1000)

    def test_align_paragraph(self):
        self.handler.prepare_original(self.elements)

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A {{id_0}} B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')
        self.assertEqual(
            [('a', 'A'), ('b', 'B'), ('c', 'C')],
            self.handler.align_paragraph(paragraph))

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A {{id_0}} B {{id_1}} C {{id_4}} D {{id_5}}', 'ENGINE', 'LANG')
        self.handler.align_paragraph(paragraph)
        self.assertEqual(
            [('a', 'A'), ('b', 'B'), ('c', 'C\n\nD')],
            self.handler.align_paragraph(paragraph))

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A {{id_0}} B {{id_1}}', 'ENGINE', 'LANG')
        self.assertEqual(
            [('a', None), ('b', None), ('c', 'A\n\nB')],
            self.handler.align_paragraph(paragraph))

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None, 'A\n\nB\n\nC\n\n',
            'ENGINE', 'LANG')
        self.assertEqual(
            [('a', 'A'), ('b', 'B'), ('c', 'C')],
            self.handler.align_paragraph(paragraph))

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None, 'A\n\nB\n\nC\n\nD\n\nE\n\n',
            'ENGINE', 'LANG')
        self.assertEqual(
            [('a', 'A'), ('b', 'B'), ('c', 'C\n\nD\n\nE')],
            self.handler.align_paragraph(paragraph))

        # paragraph = Paragraph(
        #     0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
        #     'a\n\nb\n\nx\n\n', False, None, None, 'A\n\nB\n\n',
        #     'ENGINE', 'LANG')
        # self.assertEqual(
        #     ['A', 'B'], self.handler.align_paragraph(paragraph))

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None, 'A\n\nB\n\n',
            'ENGINE', 'LANG')
        self.assertEqual(
            [('a', None), ('b', None), ('c', 'A\n\nB')],
            self.handler.align_paragraph(paragraph))

        self.handler.position = 'above'
        self.assertEqual(
            [('a', 'A\n\nB'),('b', None), ('c', None)],
            self.handler.align_paragraph(paragraph))

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_original_merge_separator(self, mock_uid):
        mock_uid.return_value = 'm1'
        self.handler.separator = Base.separator
        self.assertEqual([(
            0, 'm1', '<p id="a">a</p>\n\n<p id="b">b</p>\n\n<p id="c" '
            'class="c">c</p>\n\n', 'a\n\nb\n\nc\n\n', False)],
            self.handler.prepare_original(self.elements))
        self.assertEqual(['a', 'b', 'c'], self.handler.base_originals)

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_original_merge_separator_multiple(self, mock_uid):
        mock_uid.side_effect = ['m1', 'm2', 'm3']
        self.handler.merge_length = 2
        self.handler.separator = Base.separator
        items = [
            (0, 'm1', '<p id="a">a</p>', 'a\n\n', False),
            (1, 'm2', '<p id="b">b</p>', 'b\n\n', False),
            (2, 'm3', '<p id="c" class="c">c</p>', 'c\n\n', False)]
        self.assertEqual(items, self.handler.prepare_original(self.elements))
        self.assertEqual(['a', 'b', 'c'], self.handler.base_originals)

    def test_add_translations_merge_placeholder(self):
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

    def test_add_translations_merge_cached_placeholder(self):
        self.handler.separator = Base.separator
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

    def test_add_translations_merge_separator(self):
        self.handler.separator = Base.separator
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None,
            'A B\n\n\nC', 'ENGINE', 'LANG')])  # missing or repeated \n

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(6, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('b', elements[1].text)
        self.assertEqual('c', elements[3].text)
        self.assertEqual(
            '<p class="c">A B<br/><br/>C</p>', get_string(elements[4], True))

    def test_add_translations_merge_separator_multiple(self):
        self.handler.merge_length = 2
        self.handler.separator = Base.separator
        self.handler.prepare_original(self.elements)
        paragraphs = [
            Paragraph(0, 'm1', '<p id="a">a</p>', 'a\n\n', False, None, None,
                      'A\n\n', 'ENGINE', 'LANG'),
            Paragraph(1, 'm2', '<p id="b">b</p>', 'b\n\n', False, None, None,
                      'B', 'ENGINE', 'LANG'),
            Paragraph(2, 'm3', '<p id="c" class="c">c</p>', 'c\n\n', False,
                      None, None, 'C\n\n', 'ENGINE', 'LANG')]
        self.handler.add_translations(paragraphs)

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(8, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('A', elements[1].text)
        self.assertEqual('b', elements[2].text)
        self.assertEqual('B', elements[3].text)

        self.assertEqual('c', elements[5].text)
        self.assertEqual('C', elements[6].text)

    def test_add_translations_merge_placeholder_missing_id(self):
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(6, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('b', elements[1].text)

        self.assertEqual('c', elements[3].text)
        self.assertEqual(
            '<p class="c">A B<br/><br/>C</p>', get_string(elements[4], True))

    def test_add_translations_merge_placeholder_missing_newline(self):
        self.handler.separator = Base.separator
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None,
            'A B\n\nC\n\n', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(6, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('b', elements[1].text)

        self.assertEqual('c', elements[3].text)
        self.assertEqual(
            '<p class="c">A B<br/><br/>C</p>', get_string(elements[4], True))

    def test_add_translations_merge_palceholder_only(self):
        self.handler.position = 'only'
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

    def test_add_translations_merge_separator_only(self):
        self.handler.position = 'only'
        self.handler.separator = Base.separator
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>'
            '<a href="/a">a</a>',
            'a\n\nb\n\nc\n\n', False, None, None,
            'A\n\n B\n\nC\n\n', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)
        self.assertEqual(5, len(elements))
        self.assertEqual('A', elements[0].text)
        self.assertEqual('B', elements[1].text)

        self.assertEqual('C', elements[3].text)

    def test_add_translations_merge_placeholder_only_missing_id(self):
        self.handler.position = 'only'

        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>'
            '<a href="/a">a</a>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(3, len(elements))
        self.assertEqual(
            '<p id="c" class="c">A B<br/><br/>C</p>',
            get_string(elements[1], True))

    def test_add_translations_merge_separator_only_missing_id(self):
        self.handler.position = 'only'
        self.handler.separator = Base.separator
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>'
            '<a href="/a">a</a>',
            'a\n\nb\n\nc\n\n', False, None, None,
            'A B\n\nC\n\n', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(3, len(elements))
        self.assertEqual(
            '<p id="c" class="c">A B<br/><br/>C</p>',
            get_string(elements[1], True))
