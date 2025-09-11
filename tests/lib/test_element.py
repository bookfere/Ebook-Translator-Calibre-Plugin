import re
import unittest
from unittest.mock import patch, Mock

from lxml import etree

from calibre.ebooks.oeb.base import TOC, Metadata  # type: ignore

from ...lib.utils import ns, create_xpath
from ...lib.cache import Paragraph
from ...lib.element import (
    get_string, get_name, Extraction, ElementHandler, ElementHandlerMerge,
    Element, SrtElement, PgnElement, TocElement, PageElement, MetadataElement,
    get_srt_elements, get_pgn_elements, get_toc_elements,
    get_metadata_elements)
from ...engines import DeeplFreeTranslate
from ...engines.base import Base


module_name = 'calibre_plugins.ebook_translator.lib.element'


class TestFunction(unittest.TestCase):
    def test_get_string(self):
        markup = '<div xmlns="http://www.w3.org/1999/xhtml">' \
                 '<p class="a">abc</p> def</div>'
        element = etree.XML(markup).find('.//x:p', namespaces=ns)
        self.assertEqual(
            '<p xmlns="http://www.w3.org/1999/xhtml" class="a">abc</p>',
            get_string(element, False))
        self.assertEqual('<p class="a">abc</p>', get_string(element, True))

        markup = '<p xmlns:epub="http://www.idpf.org/2007/ops">abc</p>'
        element = etree.XML(markup)
        self.assertEqual(markup, get_string(element, False))
        self.assertEqual(
            '<p xmlns:epub="http://www.idpf.org/2007/ops">abc</p>',
            get_string(element, True))

    def test_get_name(self):
        xhtml = '<p xmlns="http://www.w3.org/1999/xhtml">a</p>'
        self.assertEqual('p', get_name(etree.XML(xhtml)))

    @patch('calibre_plugins.ebook_translator.lib.element.open_file')
    def test_get_srt_elements(self, mock_open_file):
        mock_open_file.return_value = '01:00\n0\na\nb\n\n02:00\n1\nc\n\n'
        elements = get_srt_elements('/path/to/srt', 'utf-8')
        mock_open_file.assert_called_once_with('/path/to/srt', 'utf-8')
        self.assertEqual(2, len(elements))
        self.assertEqual(['01:00', '0', 'a\nb'], elements[0].element)
        self.assertEqual(['02:00', '1', 'c'], elements[1].element)

    @patch('calibre_plugins.ebook_translator.lib.element.open_file')
    def test_get_pgn_elements(self, mock_open_file):
        mock_open_file.return_value = '1\n2\n3\n\nabc{abc}abc\n\ndef{def}def'
        elements = get_pgn_elements('/path/to/pgn', 'utf-8')
        mock_open_file.assert_called_once_with('/path/to/pgn', 'utf-8')
        self.assertEqual(2, len(elements))
        self.assertEqual(['{abc}', None], elements[0].element)
        self.assertEqual(['{def}', None], elements[1].element)

    def test_get_toc_elements(self):
        toc = TOC()
        toc.add('a', 'a.html')
        toc.nodes[0].add('b', 'b.html')
        toc.nodes[0][0].add('c', 'c.html')

        elements = get_toc_elements(toc, [])
        self.assertEqual(3, len(elements))

        elements = get_toc_elements(toc, [])
        self.assertEqual(3, len(elements))

    @patch(module_name + '.get_config')
    def test_get_metadata_elements(self, mock_get_config):
        mock_get_config.return_value.get.return_value = False
        metadata = Mock(Metadata)
        item_1 = Mock(Metadata.Item, content='a')
        item_2 = Mock(Metadata.Item, content='b')
        item_3 = Mock(Metadata.Item, content='0')
        metadata.title = [item_1]
        metadata.subject = [item_2, item_3]
        metadata.language = []
        metadata.iterkeys.return_value = ['title', 'subject', 'language']

        elements = get_metadata_elements(metadata)

        mock_get_config().get.assert_called_once_with(
            'ebook_metadata.metadata_translation', False)
        self.assertEqual(2, len(elements))
        self.assertIs(item_1, elements[0].element)
        self.assertTrue(elements[0].ignored)
        self.assertIs(item_2, elements[1].element)
        self.assertTrue(elements[1].ignored)


class MockedElement(Element):
    def get_raw(self):
        pass

    def get_text(self):
        pass

    def get_content(self):
        pass

    def add_translation(self, translation=None):
        pass


class TestElement(unittest.TestCase):
    def setUp(self):
        self._element = Mock()
        self.element = MockedElement(self._element)

    def test_create_element(self):
        self.assertIs(self._element, self.element.element)
        self.assertIsNone(self.element.page_id)
        self.assertFalse(self.element.ignored)
        self.assertEqual((), self.element.placeholder)
        self.assertEqual([], self.element.reserve_elements)
        self.assertEqual([], self.element.original)
        self.assertIsNone(self.element.column_gap)
        self.assertIsNone(self.element.position)
        self.assertIsNone(self.element.translation_lang)
        self.assertIsNone(self.element.original_color)
        self.assertIsNone(self.element.translation_color)
        self.assertIsNone(self.element.remove_pattern)
        self.assertIsNone(self.element.reserve_pattern)

    def test_create_element_with_ignored(self):
        element = MockedElement(self._element, 'toc.ncx', True)
        self.assertEqual('toc.ncx', element.page_id)
        self.assertTrue(element.ignored)

    def test_set_ignored(self):
        self.element.set_ignored(True)
        self.assertTrue(self.element.ignored)

    def test_set_placeholder(self):
        self.element.set_placeholder(['{{id_{}}}', r'{id_\d+}'])
        self.assertEqual(['{{id_{}}}', r'{id_\d+}'], self.element.placeholder)

    def test_set_column_gap(self):
        self.element.set_column_gap(('percentage', 10))
        self.assertEqual(('percentage', 10), self.element.column_gap)

    def test_set_position(self):
        self.element.set_position('left')
        self.assertEqual('left', self.element.position)

    def test_set_target_direction(self):
        self.element.set_target_direction('ltr')
        self.assertEqual('ltr', self.element.target_direction)

    def test_set_translation_lang(self):
        self.element.set_translation_lang('zh')
        self.assertEqual('zh', self.element.translation_lang)

    def test_set_original_color(self):
        self.element.set_original_color('red')
        self.assertEqual('red', self.element.original_color)

    def test_set_translation_color(self):
        self.element.set_translation_color('green')
        self.assertEqual('green', self.element.translation_color)

    def test_set_remove_pattern(self):
        self.element.set_remove_pattern('.//*[self::x:sup]')
        self.assertEqual('.//*[self::x:sup]', self.element.remove_pattern)

    def test_set_reserve_pattern(self):
        self.element.set_reserve_pattern('.//*[self::x:sup]')
        self.assertEqual('.//*[self::x:sup]', self.element.reserve_pattern)

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
        self.element.position = 'below'

    def test_get_raw(self):
        self.assertEqual('a', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_none(self):
        self.element.add_translation()
        self.assertEqual('a', self.element.element[2])

    def test_add_translation_below(self):
        self.element.add_translation('A')
        self.assertEqual('a\nA', self.element.element[2])

    def test_add_translation_right(self):
        self.element.position = 'right'
        self.element.add_translation('A')
        self.assertEqual('a\nA', self.element.element[2])

    def test_add_translation_above(self):
        self.element.position = 'above'
        self.element.add_translation('A')
        self.assertEqual('A\na', self.element.element[2])

    def test_add_translation_left(self):
        self.element.position = 'left'
        self.element.add_translation('A')
        self.assertEqual('A\na', self.element.element[2])

    def test_add_translation_only(self):
        self.element.position = 'only'
        self.element.add_translation('A')
        self.assertEqual('A', self.element.element[2])


class TestPgnElement(unittest.TestCase):
    def setUp(self):
        self.item = ['{a}', None]
        self.element = PgnElement(self.item)
        self.element.position = 'below'

    def test_create_element(self):
        self.assertIsInstance(self.element, Element)
        self.assertIsInstance(self.element, PgnElement)

    def test_get_raw(self):
        self.assertEqual('{a}', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_only(self):
        self.element.position = 'only'
        self.element.add_translation('A')
        self.assertEqual('A', self.element.element[1])

    def test_add_translation_below(self):
        self.element.add_translation('A')
        self.assertEqual('a | A', self.element.element[1])

    def test_add_translation_right(self):
        self.element.position = 'right'
        self.element.add_translation('A')
        self.assertEqual('a | A', self.element.element[1])

    def test_add_translation_above(self):
        self.element.position = 'above'
        self.element.add_translation('A')
        self.assertEqual('A | a', self.element.element[1])

    def test_add_translation_left(self):
        self.element.position = 'left'
        self.element.add_translation('A')
        self.assertEqual('A | a', self.element.element[1])

    def test_get_translation(self):
        self.element.add_translation('A')
        self.assertEqual('{a | A}', self.element.get_translation())

    def test_get_translation_none(self):
        self.assertEqual('{a}', self.element.get_translation())


class TestMetadataElement(unittest.TestCase):
    def setUp(self):
        self.medata_item = Mock(Metadata.Item, content='a')
        self.element = MetadataElement(self.medata_item)
        self.element.position = 'below'

    def test_get_raw(self):
        self.assertEqual('a', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_none(self):
        self.element.add_translation()
        self.assertEqual('a', self.element.element.content)

    def test_add_translation_below(self):
        self.element.add_translation('A')
        self.assertEqual('a A', self.element.element.content)

    def test_add_translation_right(self):
        self.element.position = 'right'
        self.element.add_translation('A')
        self.assertEqual('a A', self.element.element.content)

    def test_add_translation_above(self):
        self.element.position = 'above'
        self.element.add_translation('A')
        self.assertEqual('A a', self.element.element.content)

    def test_add_translation_left(self):
        self.element.position = 'left'
        self.element.add_translation('A')
        self.assertEqual('A a', self.element.element.content)

    def test_add_translation_only(self):
        self.element.position = 'only'
        self.element.add_translation('A')
        self.assertEqual('A', self.element.element.content)

    def test_add_translation_same_content(self):
        self.element.add_translation('a')
        self.assertEqual('a', self.element.element.content)

    def test_add_translation_with_ignored(self):
        self.element.ignored = True
        self.element.add_translation('A')
        self.assertEqual('a', self.element.element.content)


class TestTocElement(unittest.TestCase):
    def setUp(self):
        self.element = TocElement(TOC('a', 'a.html'), 'toc.ncx')
        self.element.position = 'below'

    def test_get_raw(self):
        self.assertEqual('a', self.element.get_raw())

    def test_get_text(self):
        self.assertEqual('a', self.element.get_text())

    def test_get_content(self):
        self.assertEqual('a', self.element.get_content())

    def test_add_translation_none(self):
        self.element.add_translation()
        self.assertEqual('a', self.element.element.title)

    def test_add_translation_below(self):
        self.element.add_translation('A')
        self.assertEqual('a A', self.element.element.title)

    def test_add_translation_right(self):
        self.element.position = 'right'
        self.element.add_translation('A')
        self.assertEqual('a A', self.element.element.title)

    def test_add_translation_above(self):
        self.element.position = 'above'
        self.element.add_translation('A')
        self.assertEqual('A a', self.element.element.title)

    def test_add_translation_left(self):
        self.element.position = 'left'
        self.element.add_translation('A')
        self.assertEqual('A a', self.element.element.title)

    def test_add_translation_only(self):
        self.element.position = 'only'
        self.element.add_translation('A')
        self.assertEqual('A', self.element.element.title)


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
            <code>App\Http</code> k<sup>[1]</sup> l
        </p>
    </body>
</html>""")
        self.paragraph = self.xhtml.find('.//x:p', namespaces=ns)
        self.element = PageElement(self.paragraph, 'p1')
        self.element.remove_pattern = create_xpath(('rt',))
        self.element.reserve_pattern = create_xpath(
            ('img', 'sup', 'br', 'code'))
        self.element.placeholder = Base.placeholder
        self.element.position = 'below'

    def test_get_name(self):
        self.assertEqual('p', self.element.get_name())

    def test_get_raw(self):
        text = (
            '<p class="abc"> <img src="icon.jpg"/> a <img src="w1.jpg"/> '
            '<ruby>b<rt>B</rt></ruby> c <span><img src="w2.jpg"/> d</span> '
            '<span>e <img src="w2.jpg"/></span> f <span>g <img src="w2.jpg"/> '
            r'h</span> <img alt="{\D}" src="w3.jpg"/> i <img src="w3.jpg"/> '
            r'<code>App\Http</code> k<sup>[1]</sup> l </p>')
        self.assertEqual(text, self.element.get_raw())

    def test_get_text(self):
        self.assertEqual(
            r'a bB c d e f g h i App\Http k[1] l', self.element.get_text())

    def test_get_content(self):
        content = (
            '{{id_00000}} a {{id_00001}} b c {{id_00002}} d e '
            '{{id_00003}} f g {{id_00004}} h {{id_00005}} i '
            '{{id_00006}} {{id_00007}} k{{id_00008}} l')
        self.assertEqual(content, self.element.get_content())
        self.assertEqual(9, len(self.element.reserve_elements))
        self.assertEqual(
            '<img src="icon.jpg"></img>', self.element.reserve_elements[0])
        self.assertEqual(
            '<img src="w1.jpg"></img>', self.element.reserve_elements[1])
        self.assertEqual(
            '<img src="w2.jpg"></img>', self.element.reserve_elements[2])
        self.assertEqual(
            '<img src="w2.jpg"></img>', self.element.reserve_elements[3])
        self.assertEqual(
            '<img src="w2.jpg"></img>', self.element.reserve_elements[4])
        self.assertEqual(
            '<img alt="{\D}" src="w3.jpg"></img>',
            self.element.reserve_elements[5])
        self.assertEqual(
            '<img src="w3.jpg"></img>', self.element.reserve_elements[6])
        self.assertEqual(
            '<code>App\\Http</code>', self.element.reserve_elements[7])
        self.assertEqual('<sup>[1]</sup>', self.element.reserve_elements[8])

    def test_get_content_with_sub_sup(self):
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p class="abc">
            a<a><sup>[1]</sup></a>
            b<a><sup>[1]</sup> <span>x</span></a>
            c<a>x <sup>[2]</sup></a>
            d<a><sup>[3]</sup> x</a>
        </p>
    </body>
</html>""")
        element = PageElement(xhtml.find('.//x:p', namespaces=ns), 'p1')
        element.reserve_pattern = create_xpath(('sup',))
        element.placeholder = Base.placeholder
        content = (
            'a{{id_00000}} b{{id_00001}} x cx {{id_00002}} d{{id_00003}} x')
        self.assertEqual(content, element.get_content())
        self.assertEqual('<a><sup>[1]</sup></a>', element.reserve_elements[0])
        self.assertEqual('<sup>[1]</sup>', element.reserve_elements[1])
        self.assertEqual('<sup>[2]</sup>', element.reserve_elements[2])
        self.assertEqual('<sup>[3]</sup>', element.reserve_elements[3])

    def test_get_attributes(self):
        self.assertEqual('{"class": "abc"}', self.element.get_attributes())

    def test_add_translation_none_below(self):
        self.element.original_color = '#ffff00'
        self.element.add_translation()

        elements = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(1, len(elements))
        self.assertIn('style="color:#ffff00"', get_string(elements[0]))

    def test_add_translation_none_above(self):
        self.element.position = 'above'
        self.element.original_color = '#ffff00'
        self.element.add_translation()

        elements = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(1, len(elements))
        self.assertIn('style="color:#ffff00"', get_string(elements[0]))

    def test_add_translation_none_left(self):
        self.element.column_gap = ('space_count', 5)
        self.element.position = 'left'
        self.element.original_color = '#ffff00'
        self.element.add_translation()

        self.assertEqual(1, len(self.xhtml.findall('.//x:p', namespaces=ns)))
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)
        left_td, middle_td, right_td = table.findall('.//td')
        self.assertEqual(0, len(list(left_td)))
        self.assertIsNone(left_td.text)
        self.assertEqual(0, len(list(middle_td)))
        self.assertEqual('\xa0\xa0\xa0\xa0\xa0', middle_td.text)
        self.assertEqual(1, len(list(right_td)))
        self.assertIn('style="color:#ffff00"', get_string(list(right_td)[0]))

    def test_add_translation_none_right(self):
        self.element.column_gap = ('percentage', 20)
        self.element.position = 'right'
        self.element.original_color = '#ff00ff'
        self.element.add_translation()

        self.assertEqual(1, len(self.xhtml.findall('.//x:p', namespaces=ns)))
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)
        left_td, middle_td, right_td = table.findall('.//td')
        self.assertEqual(1, len(list(left_td)))
        self.assertEqual('40%', left_td.get('width'))
        self.assertIn('style="color:#ff00ff"', get_string(list(left_td)[0]))
        self.assertEqual(0, len(list(middle_td)))
        self.assertEqual('20%', middle_td.get('width'))
        self.assertEqual(0, len(list(right_td)))
        self.assertEqual('40%', right_td.get('width'))
        self.assertIsNone(right_td.text)

    def test_add_translation_with_placeholder(self):
        self.element.set_placeholder(Base.placeholder)
        self.element.get_content()
        translation = (
            '{{id_00000}} Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa '
            '{{id_00001}} Bbbbbbbbbbbbbbb C {{id_00002}} D E '
            '{{id_00003}} F G {{id_00004}} H {{id_00005}} I '
            '{{id_00006}} {{id_00007}} K{ { id _ 0 00 08 } } L')
        self.element.add_translation(translation)

        translation = (
            '<p xmlns="http://www.w3.org/1999/xhtml" class="abc" dir="auto">'
            '<img src="icon.jpg"/> Aaaaa <img src="w1.jpg"/> '
            'Bbbbb C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
            'F G <img src="w2.jpg"/> H '
            r'<img alt="{\D}" src="w3.jpg"/> I '
            r'<img src="w3.jpg"/> <code>App\Http</code> '
            'K<sup>[1]</sup> L</p>')
        elements = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(2, len(elements))
        self.assertEqual(translation, get_string(elements[1]))
        self.assertIsNone(elements[1].get('lang'))
        self.assertIsNone(elements[1].get('style'))
        self.assertEqual('abc', elements[1].get('class'))

    def test_add_translation_with_markup(self):
        self.element.placeholder = DeeplFreeTranslate.placeholder
        self.element.get_content()
        translation = (
            '<m id=00000 /> Aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa '
            '<m id=00001 /> Bbbbbbbbbbbbbbb C <m id=00002 /> D '
            'E <m id=00003 /> F G <m id=00004 /> H <m id=00005 /> '
            'I <m id=00006 /> <m id=00007 /> K<m id=00008 /> L')
        self.element.add_translation(translation)

        translation = (
            '<p xmlns="http://www.w3.org/1999/xhtml" class="abc" dir="auto">'
            '<img src="icon.jpg"/> Aaaaa <img src="w1.jpg"/> '
            'Bbbbb C <img src="w2.jpg"/> D E <img src="w2.jpg"/> '
            'F G <img src="w2.jpg"/> H '
            r'<img alt="{\D}" src="w3.jpg"/> I '
            r'<img src="w3.jpg"/> <code>App\Http</code> '
            'K<sup>[1]</sup> L</p>')
        elements = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(2, len(elements))
        self.assertEqual(translation, get_string(elements[1]))
        self.assertIsNone(elements[1].get('lang'))
        self.assertIsNone(elements[1].get('style'))
        self.assertEqual('abc', elements[1].get('class'))

    def test_add_translation_with_linefeeds(self):
        """Convert linefeeds to line breaks if those linefeeds were added to
        the translation intentionally."""
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body><p>a b c</p></body>
</html>""")
        element = PageElement(xhtml.find('.//x:p', namespaces=ns), 'p1')
        element.set_placeholder(Base.placeholder)
        element.get_content()
        element.add_translation('A\n\nB\nC')

        elements = xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(2, len(elements))
        self.assertEqual(
            '<p xmlns="http://www.w3.org/1999/xhtml" dir="auto">'
            'A<br/><br/>B<br/>C</p>',
            get_string(elements[1]))

    def test_add_translation_with_extra_namespace(self):
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
xmlns:epub="http://www.idpf.org/2007/ops" lang="en">
    <head><title>Test Document</title></head>
    <body><p>a<code><span epub:type="pagebreak"/>b</code></p></body>
</html>""")
        element = PageElement(xhtml.find('.//x:p', namespaces=ns), 'p1')
        element.reserve_pattern = create_xpath(('code',))
        element.set_placeholder(Base.placeholder)
        element.get_content()
        element.add_translation('A{{id_00000}}')

        elements = xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(2, len(elements))
        self.assertEqual(
            '<p xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops" '
            'dir="auto">A<code><span epub:type="pagebreak"/>b</code></p>',
            get_string(elements[1]))

    def test_add_translation_with_missing_namespace(self):
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body><p>a<code><span xmlns:epub="http://www.idpf.org/2007/ops"
epub:type="pagebreak"/>b</code></p></body>
</html>""")
        element = PageElement(xhtml.find('.//x:p', namespaces=ns), 'p1')
        element.reserve_pattern = create_xpath(('code',))
        element.set_placeholder(Base.placeholder)
        element.get_content()
        element.add_translation('A{{id_00000}}')

        elements = xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(2, len(elements))
        self.assertEqual(
            '<p xmlns="http://www.w3.org/1999/xhtml" dir="auto">'
            'A<code><span xmlns:epub="http://www.idpf.org/2007/ops" '
            'epub:type="pagebreak"/>b</code></p>',
            get_string(elements[1]))

    def test_add_translation_below(self):
        self.element.position = 'next'
        self.element.original_color = 'red'
        self.element.translation_color = 'blue'
        self.element.add_translation('test')

        original, translation = self.xhtml.findall('.//x:p', namespaces=ns)
        for element in original:
            with self.subTest(element=element):
                if get_name(element) != 'img':
                    self.assertEqual('color:red', element.get('style'))
        self.assertEqual('color:blue', translation.get('style'))
        self.assertIn('>test<', get_string(translation))

    def test_add_translation_above(self):
        self.element.position = 'above'
        self.element.original_color = 'red'
        self.element.translation_color = 'blue'
        self.element.add_translation('test')

        translation, original = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual('color:blue', translation.get('style'))
        self.assertEqual('color:red', original.get('style'))
        self.assertIn('>test<', get_string(translation))

    def test_add_translation_right(self):
        self.element.position = 'right'
        self.element.add_translation('test')

        self.assertEqual(2, len(self.xhtml.findall('.//x:p', namespaces=ns)))
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)
        left_td, middle_td, right_td = table.findall('.//td')
        self.assertEqual(1, len(list(left_td)))
        self.assertEqual('45%', left_td.get('width'))
        self.assertEqual(0, len(list(middle_td)))
        self.assertEqual('10%', middle_td.get('width'))
        self.assertIsNone(middle_td.text)
        self.assertEqual(1, len(list(right_td)))
        self.assertEqual('45%', right_td.get('width'))
        self.assertIn('>test<', get_string(right_td))

    def test_add_translation_left(self):
        self.element.position = 'left'
        self.element.original_color = 'red'
        self.element.translation_color = 'blue'
        self.element.add_translation('test')

        self.assertEqual(2, len(self.xhtml.findall('.//x:p', namespaces=ns)))
        table = self.xhtml.find('.//x:table', namespaces=ns)
        self.assertIsNotNone(table)
        left_td, middle_td, right_td = table.findall('.//td')
        self.assertEqual(1, len(list(left_td)))
        self.assertEqual('45%', left_td.get('width'))
        self.assertIn('>test<', get_string(left_td))
        self.assertEqual(0, len(list(middle_td)))
        self.assertEqual('10%', middle_td.get('width'))
        self.assertIsNone(middle_td.text)
        self.assertEqual(1, len(list(right_td)))
        self.assertEqual('45%', right_td.get('width'))

    def test_add_translation_only(self):
        self.element.position = 'only'
        self.element.translation_color = 'blue'
        self.element.add_translation('test')

        elements = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(1, len(elements))
        self.assertEqual('color:blue', elements[0].get('style'))
        self.assertIn('>test<', get_string(elements[0]))

    def test_add_translation_only_keep_anchor(self):
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
        element.position = 'only'
        element.add_translation('A')

        a = xhtml.find('.//x:a[1]', namespaces=ns)
        self.assertIsNone(a.get('href'))
        self.assertEqual('A', a.text)

        element = PageElement(xhtml.find('.//x:a[2]', namespaces=ns), 'p1')
        element.position = 'only'
        element.add_translation('A')

        a = xhtml.find('.//x:a[2]', namespaces=ns)
        self.assertEqual('abc', a.get('href'))
        self.assertEqual('A', a.text)

    def test_add_translation_table(slef):
        pass

    def test_add_translation_table_only(slef):
        pass

    def test_add_translation_line_break_below(self):
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p>a<br/></p>
        <p>a<br/>b</p>
        <p>a<br/><br/><br/>b</p>
        <p>a<br/>b<br/></p>
        <p>a<br/>b<br/><br/><br/></p>
        <p><br/>a<br/>b</p>
        <p><br/><br/><br/>a<br/>b</p>
        <p>a<br/><span>b<br/>c<br/><img src="test.jpg"/>d</span>e</p>
    </body>
</html>""")
        translations = [
            'A{{id_00000}}',
            'A{{id_00000}}B',
            'A{{id_00000}}{{id_00001}}{{id_00002}}B',
            'A{{id_00000}}B{{id_00001}}',
            'A{{id_00000}}B{{id_00001}}{{id_00002}}{{id_00003}}',
            '{{id_00000}}A{{id_00001}}B',
            '{{id_00000}}{{id_00001}}{{id_00002}}A{{id_00003}}B',
            'A{{id_00000}}B{{id_00001}}C{{id_00002}}{{id_00003}}D E']
        for element in xhtml.findall('.//x:p', namespaces=ns):
            element = PageElement(element, 'p1')
            element.reserve_pattern = create_xpath(('sup', 'img', 'br'))
            element.placeholder = Base.placeholder
            element.position = 'below'
            element.get_content()
            element.add_translation(translations.pop(0))

        translation = (
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="en"> '
            '<head><title>Test Document</title></head> <body> '
            '<p>a<br/><span dir="auto">A</span><br/></p> '
            '<p>a<br/><span dir="auto">A</span><br/>'
            'b<br/><span dir="auto">B</span></p> '
            '<p>a<br/><span dir="auto">A</span><br/><br/><br/>'
            'b<br/><span dir="auto">B</span></p> '
            '<p>a<br/><span dir="auto">A</span><br/>b<br/>'
            '<span dir="auto">B</span><br/></p> '
            '<p>a<br/><span dir="auto">A</span><br/>b<br/>'
            '<span dir="auto">B</span><br/><br/><br/></p> '
            '<p><br/>a<br/><span dir="auto">A</span><br/>b<br/>'
            '<span dir="auto">B</span></p> '
            '<p><br/><br/><br/>a<br/><span dir="auto">A</span><br/>b<br/>'
            '<span dir="auto">B</span></p> '
            '<p>a<br/><span dir="auto">A</span><br/><span>b<br/>'
            '<span dir="auto">B</span><br/>c<br/>'
            '<span dir="auto">C</span><br/><img src="test.jpg"/>d</span>e<br/>'
            '<span dir="auto"><img src="test.jpg"/>D E</span></p> '
            '</body> </html>')
        self.assertEqual(translation, get_string(xhtml))

    def test_add_translation_line_break_above(self):
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p>a<br/></p>
        <p>a<br/>b</p>
        <p>a<br/><br/><br/>b</p>
        <p>a<br/>b<br/></p>
        <p>a<br/>b<br/><br/><br/></p>
        <p><br/>a<br/>b</p>
        <p><br/><br/><br/>a<br/>b</p>
        <p>a<img src="test.jpg"/><br/><span>b<br/>c<br/>d</span>e</p>
    </body>
</html>""")
        translations = [
            'A{{id_00000}}',
            'A{{id_00000}}B',
            'A{{id_00000}}{{id_00001}}{{id_00002}}B',
            'A{{id_00000}}B{{id_00001}}',
            'A{{id_00000}}B{{id_00001}}{{id_00002}}{{id_00003}}',
            '{{id_00000}}A{{id_00001}}B',
            '{{id_00000}}{{id_00001}}{{id_00002}}A{{id_00003}}B',
            'A{{id_00000}}{{id_00001}}B{{id_00002}}C{{id_00003}}D E'
        ]
        for element in xhtml.findall('.//x:p', namespaces=ns):
            element = PageElement(element, 'p1')
            element.reserve_pattern = create_xpath(('sup', 'img', 'br'))
            element.placeholder = Base.placeholder
            element.position = 'above'
            element.get_content()
            element.add_translation(translations.pop(0))

        translation = (
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="en"> '
            '<head><title>Test Document</title></head> <body> '
            '<p><span dir="auto">A</span><br/>a<br/></p> '
            '<p><span dir="auto">A</span><br/>a<br/>'
            '<span dir="auto">B</span><br/>b</p> '
            '<p><span dir="auto">A</span><br/>a<br/><br/><br/>'
            '<span dir="auto">B</span><br/>b</p> '
            '<p><span dir="auto">A</span><br/>a<br/>'
            '<span dir="auto">B</span><br/>b<br/></p> '
            '<p><span dir="auto">A</span><br/>a<br/>'
            '<span dir="auto">B</span><br/>b<br/><br/><br/></p> '
            '<p><br/><span dir="auto">A</span><br/>a<br/>'
            '<span dir="auto">B</span><br/>b</p> '
            '<p><br/><br/><br/><span dir="auto">A</span><br/>a<br/>'
            '<span dir="auto">B</span><br/>b</p> '
            '<p><span dir="auto">A<img src="test.jpg"/></span><br/>'
            'a<img src="test.jpg"/><br/><span dir="auto">B</span><br/>'
            '<span>b<br/><span dir="auto">C</span><br/>c<br/>'
            '<span dir="auto">D E</span><br/>d</span>e</p> '
            '</body> </html>')
        self.assertEqual(translation, get_string(xhtml))

    def test_add_translation_attr(self):
        self.element.translation_lang = 'zh'
        self.element.original_color = 'green'
        self.element.translation_color = 'red'
        self.element.target_direction = 'rtl'
        self.element.add_translation('test')

        elements = self.xhtml.findall('.//x:p', namespaces=ns)
        self.assertEqual(2, len(elements))
        self.assertEqual('zh', elements[1].get('lang'))
        self.assertEqual('color:green', self.element.element.get('style'))
        self.assertEqual('color:red', elements[1].get('style'))
        self.assertEqual('rtl', elements[1].get('dir'))

    def test_add_translation_set_style_with_non_element_nodes(self):
        xhtml = etree.XML(rb"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p>a<!--test--></p>
    </body>
</html>""")

        element = PageElement(xhtml.find('.//x:p[1]', namespaces=ns), 'p1')
        element.original_color = 'green'
        element.add_translation('A')

        p = xhtml.find('.//x:p[2]', namespaces=ns)
        self.assertEqual('A', p.text)


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

        pages = [self.page_3, self.page_2, self.page_1]
        self.extraction = Extraction(pages, [], 'normal', 'text', [], [])

    def test_create_extraction(self):
        self.assertIsInstance(self.extraction, Extraction)
        self.assertEqual(
            [self.page_3, self.page_2, self.page_1], self.extraction.pages)
        self.assertEqual('normal', self.extraction.rule_mode)
        self.assertEqual('text', self.extraction.filter_scope)
        self.assertEqual([], self.extraction.filter_rules)
        self.assertEqual([], self.extraction.ignore_rules)
        default_rule = r'^[-\d\s\.\'\\"‘’“”,=~!@#$%^&º*|≈<>?/`—…+:–_(){}[\]]+$'
        self.assertEqual(
            [re.compile(default_rule)],
            self.extraction.filter_patterns)
        self.assertEqual(
            ['self::x:pre', 'self::x:code'], self.extraction.ignore_patterns)

    def test_get_sorted_pages(self):
        self.assertEqual(
            [self.page_1, self.page_2], self.extraction.get_sorted_pages())

    def test_get_elements(self):
        self.extraction.rule_mode = 'normal'
        self.extraction.filter_rules = []
        self.extraction.ignore_rules = []

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

    def test_load_priority_patterns(self):
        self.extraction.load_priority_patterns()
        self.assertEqual(9, len(self.extraction.priority_patterns))

        self.extraction.priority_rules = [
            'table', 'table.list', 'invalid:class']
        self.extraction.load_priority_patterns()
        self.assertEqual(11, len(self.extraction.priority_patterns))

    def test_load_filter_patterns(self):
        self.extraction.load_filter_patterns()
        self.assertEqual(1, len(self.extraction.filter_patterns))

        self.extraction.filter_rules = ['^a', 'b$']
        self.extraction.load_filter_patterns()
        self.assertEqual(3, len(self.extraction.filter_patterns))

    def test_load_ignore_patterns(self):
        self.extraction.load_ignore_patterns()
        self.assertEqual(2, len(self.extraction.ignore_patterns))

        self.extraction.ignore_rules = [
            'table', 'table.list', 'invalid:class']
        self.extraction.load_ignore_patterns()
        self.assertEqual(4, len(self.extraction.ignore_patterns))

    def test_is_priority(self):
        self.extraction.priority_rules = ['.test']
        self.extraction.load_priority_patterns()

        items = [
            '<p xmlns="http://www.w3.org/1999/xhtml">abc</p>',
            '<pre xmlns="http://www.w3.org/1999/xhtml">abc</pre>',
            '<div xmlns="http://www.w3.org/1999/xhtml" class="test">abc</div>']
        for item in items:
            with self.subTest(item=item):
                self.assertTrue(self.extraction.is_priority(etree.XML(item)))

        items = [
            '<sub xmlns="http://www.w3.org/1999/xhtml">abc</sub>',
            '<div xmlns="http://www.w3.org/1999/xhtml" id="a">abc</div>']
        for item in items:
            with self.subTest(item=item):
                self.assertFalse(self.extraction.is_priority(etree.XML(item)))

    def test_is_inline_only(self):
        div = '<div xmlns="http://www.w3.org/1999/xhtml"><span>a</span></div>'
        self.assertTrue(self.extraction.is_inline_only(etree.XML(div)))

        div = '<div xmlns="http://www.w3.org/1999/xhtml"><div>a</div></div>'
        self.assertFalse(self.extraction.is_inline_only(etree.XML(div)))

    def test_need_ignore(self):
        self.extraction.ignore_rules = ['table', 'p.a']
        self.extraction.load_ignore_patterns()

        items = [
            '<pre xmlns="http://www.w3.org/1999/xhtml">abc</pre>',
            '<code xmlns="http://www.w3.org/1999/xhtml">abc</code>',
            '<table xmlns="http://www.w3.org/1999/xhtml">abc</table>',
            '<p xmlns="http://www.w3.org/1999/xhtml" class="a">abc</p>']

        for item in items:
            with self.subTest(item=item):
                self.assertTrue(self.extraction.need_ignore(etree.XML(item)))

        items = [
            '<p xmlns="http://www.w3.org/1999/xhtml">abc</p>',
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
        root = xhtml.find('.//x:body', namespaces=ns)
        elements = self.extraction.extract_elements('p1', root, [])
        self.assertEqual(9, len(elements))
        self.assertEqual('h2', elements[0].get_name())
        self.assertFalse(elements[0].ignored)
        self.assertEqual('pre', elements[-2].get_name())
        self.assertTrue(elements[-2].ignored)
        self.assertEqual('p', elements[-1].get_name())
        self.assertFalse(elements[-1].ignored)

    def test_extract_elements_root_without_elements(self):
        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>123456789</body>
</html>""")
        root = xhtml.find('.//x:body', namespaces=ns)

        elements = self.extraction.extract_elements('test', root, [])
        self.assertEqual(1, len(elements))
        self.assertEqual('123456789', elements[0].element.text)

    def test_extract_elements_ignore_root(self):
        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body class="test"><p>a</p></body>
</html>""")
        root = xhtml.find('.//x:body', namespaces=ns)
        self.extraction.ignore_rules = ['.test']
        self.extraction.load_ignore_patterns()

        self.assertEqual(
            [], self.extraction.extract_elements('test', root, []))

    def test_extract_elements_ignore_certain_elements(self):
        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body>
    <div><p>a</p></div>
    <div class="test"><p>b</p><p class="test">c</p></div>
    <div><p>d</p></div>
    <div id="test"><p>e</p></div>
</body>
</html>""")
        root = xhtml.find('.//x:body', namespaces=ns)
        self.extraction.ignore_rules = ['.test', '#test']
        self.extraction.load_ignore_patterns()

        elements = self.extraction.extract_elements('test', root, [])
        self.assertEqual(4, len(elements))
        self.assertEqual(
            xhtml.find('.//x:div[1]/x:p', namespaces=ns), elements[0].element)
        self.assertTrue(elements[1].ignored)
        self.assertEqual(
            xhtml.find('.//x:div[3]/x:p', namespaces=ns), elements[2].element)
        self.assertTrue(elements[3].ignored)

    def test_extract_elements_with_sole_block_level_element(self):
        xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head><title>Document</title></head>
<body class="test"><div><span>a </span><span>, b</span></div></body>
</html>""")
        root = xhtml.find('.//x:body', namespaces=ns)
        self.extraction.load_ignore_patterns()
        elements = self.extraction.extract_elements('test', root, [])
        self.assertEqual(1, len(elements))
        self.assertEqual('div', elements[0].get_name())

    def test_filter_content(self):
        def elements(markups):
            return [
                PageElement(etree.XML(markup), 'test') for markup in markups]

        # normal - text
        markups = [
            '<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>',
            '<p></p>', '<p> </p>', '<p><img src="/abc.jpg" /></p>',
            '<p><span>  </span><span>  </span></p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.assertFalse(self.extraction.filter_content(element))

        self.extraction.filter_rules = ['a', 'b', 'c']
        self.extraction.load_filter_patterns()
        markups = [
            '<p>xxxaxxx</p>', '<p>xxxbxxx</p>', '<p>xxxcxxx</p>',
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
        markups = [
            '<p>5.</p>', '<p>5-5.</p>', '<p>5-5_5.</p>', '<p>abc</p>',
            '<p>def</p>', '<p>ghi</p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.extraction.filter_content(element)
                self.assertTrue(element.ignored)

        # regex - html
        self.extraction.rule_mode = 'regex'
        self.extraction.filter_scope = 'html'
        self.extraction.filter_rules = ['^<pre>', '</code>$', 'class="c"']
        self.extraction.load_filter_patterns()
        markups = [
            '<p>\xa0</p>', '<p>\u3000</p>', '<p>\u200b</p>',
            '<p></p>', '<p> </p>', '<p><img src="/abc.jpg" /></p>',
            '<p><span>  </span><span>  </span></p>']
        for element in elements(markups):
            with self.subTest(element=element):
                self.assertFalse(self.extraction.filter_content(element))

        markups = [
            '<pre>a</pre>', '<code>b</code>', '<p class="c">c</p>',
            '<p>2 &lt;= 2</p>', '<p><span>123</span></p>', '<p>”.—…‘’</p>']
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

    def test_create_element_handler_merge(self):
        self.assertIsInstance(self.handler, ElementHandler)
        self.assertEqual(Base.placeholder, self.handler.placeholder)
        self.assertEqual(Base.separator, self.handler.separator)
        self.assertEqual('below', self.handler.position)
        self.assertEqual(0, self.handler.merge_length)
        self.assertIsNone(self.handler.target_direction)
        self.assertIsNone(self.handler.translation_lang)
        self.assertIsNone(self.handler.original_color)
        self.assertIsNone(self.handler.translation_color)
        self.assertIsNone(self.handler.column_gap)
        self.assertIsNone(self.handler.remove_pattern)
        self.assertIsNone(self.handler.reserve_pattern)
        self.assertEqual({}, self.handler.elements)
        self.assertEqual([], self.handler.originals)

    def test_get_merge_length(self):
        self.assertEqual(0, self.handler.merge_length)

    def test_set_target_direction(self):
        self.handler.set_target_direction('ltr')
        self.assertEqual('ltr', self.handler.target_direction)

    def test_set_translation_lang(self):
        self.handler.set_translation_lang('zh')
        self.assertEqual('zh', self.handler.translation_lang)

    def test_set_original_color(self):
        self.handler.set_original_color('#ff00ff')
        self.assertEqual('#ff00ff', self.handler.original_color)

    def test_set_translation_color(self):
        self.handler.set_translation_color('#ff00ff')
        self.assertEqual('#ff00ff', self.handler.translation_color)

    def test_set_column_gap(self):
        self.handler.set_column_gap('test')
        self.assertIsNone(self.handler.column_gap)

        self.handler.set_column_gap(('percentage',))
        self.assertIsNone(self.handler.column_gap)

        self.handler.set_column_gap(('percentage', 2))
        self.assertEqual(('percentage', 2), self.handler.column_gap)

    def test_load_remove_rules(self):
        self.handler.load_remove_rules()
        self.assertEqual(
            './/*[self::x:rt or self::x:rp]', self.handler.remove_pattern)

    def test_load_reserve_rules(self):
        self.handler.load_reserve_rules()
        self.assertRegex(
            self.handler.reserve_pattern, r'^\.//\*\[self::x:img.*style\]$')

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_original(self, mock_uid):
        self.handler.translation_lang = 'en'
        self.handler.original_color = 'red'
        self.handler.translation_color = 'green'
        self.handler.column_gap = ('percentage', 20)
        self.handler.load_remove_rules()
        self.handler.load_reserve_rules()
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
        for element in self.elements:
            with self.subTest(element=element):
                self.assertEqual(Base.placeholder, element.placeholder)
                self.assertEqual('below', element.position)
                self.assertEqual('en', element.translation_lang)
                self.assertEqual('red', element.original_color)
                self.assertEqual('green', element.translation_color)
                self.assertEqual(('percentage', 20), element.column_gap)
                self.assertEqual(
                    './/*[self::x:rt or self::x:rp]',
                    self.handler.remove_pattern)
                self.assertRegex(
                    element.reserve_pattern or '',
                    r'^\.//\*\[self::x:img.*style\]$')

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_translation_contains_ignored_element(self, mock_uid):
        self.xhtml = etree.XML(b"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
    <head><title>Test Document</title></head>
    <body>
        <p><b class="test">a</b></p>
    </body>
</html>""")
        self.handler.load_remove_rules(['.test'])
        mock_uid.return_value = 'm1'
        elements = [
            PageElement(element, 'p1') for element
            in self.xhtml.findall('./x:body/*', namespaces=ns)]
        self.assertEqual([
            (0, 'm1', '<p><b class="test">a</b></p>', '', True, None, 'p1')],
            self.handler.prepare_original(elements))
        self.assertTrue(elements[0].ignored)

    def test_prepare_translation(self):
        pass

    def test_add_translations(self):
        self.handler.prepare_original(self.elements)
        translations = [
            Paragraph(
                0, 'm1', '<p id="x">x</p>', 'x', False, '{"id": "x"}', 'p1',
                None, 'ENGINE', 'LANG'),
            Paragraph(
                1, 'm1', '<p id="a">a</p>', 'a', False, '{"id": "a"}', 'p1',
                'A', 'ENGINE', 'LANG'),
            Paragraph(
                2, 'm2', '<p id="b">b</p>', 'b', False, '{"id": "b"}', 'p1',
                'B', 'ENGINE', 'LANG'),
            Paragraph(
                3, 'm3', '<p id="c">c</p>', 'c', False,
                '{"id": "c", "class": "c"}', 'p1', 'C', 'ENGINE', 'LANG')]

        self.handler.add_translations(translations)

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(8, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('A', elements[1].text)
        self.assertEqual('auto', elements[1].get('dir'))
        self.assertEqual('b', elements[2].text)
        self.assertEqual('B', elements[3].text)
        self.assertEqual('auto', elements[3].get('dir'))

        self.assertEqual('c', elements[5].text)
        self.assertEqual('C', elements[6].text)
        self.assertEqual('auto', elements[6].get('dir'))

        self.assertIsNone(elements[6].get('id'))
        self.assertEqual('c', elements[6].get('class'))

    def test_add_translations_with_partial_translation(self):
        self.handler.target_direction = 'rtl'
        self.handler.prepare_original(self.elements)
        translations = [
            Paragraph(1, 'm1', '<p id="a">a</p>', 'a', False, '{"id": "a"}',
                      'p1', 'A', 'ENGINE', 'LANG'),
            Paragraph(3, 'm3', '<p id="c">c</p>', 'c', False,
                      '{"id": "c", "class": "c"}', 'p1', 'C', 'ENGINE',
                      'LANG')]

        self.handler.add_translations(translations)

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(7, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('A', elements[1].text)
        self.assertEqual('rtl', elements[1].get('dir'))
        self.assertEqual('b', elements[2].text)

        self.assertEqual('c', elements[4].text)
        self.assertEqual('C', elements[5].text)
        self.assertEqual('rtl', elements[5].get('dir'))

        self.assertIsNone(elements[5].get('id'))
        self.assertEqual('c', elements[5].get('class'))

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
            Base.placeholder, Base.separator, 'below')
        self.handler.set_merge_length(1000)

    def test_create_element_handler_merge(self):
        self.assertIsInstance(self.handler, ElementHandler)
        self.assertIsInstance(self.handler, ElementHandlerMerge)
        self.assertEqual(1000, self.handler.merge_length)

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

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None, None,
            'ENGINE', 'LANG')
        self.assertEqual(
            [('a', None), ('b', None), ('c', None)],
            self.handler.align_paragraph(paragraph))

        paragraph = Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a\n\nb\n\nc\n\n', False, None, None, 'A\n\nB\n\n',
            'ENGINE', 'LANG')
        self.assertEqual(
            [('a', None), ('b', None), ('c', 'A\n\nB')],
            self.handler.align_paragraph(paragraph))

        self.handler.position = 'above'
        self.assertEqual(
            [('a', 'A\n\nB'), ('b', None), ('c', None)],
            self.handler.align_paragraph(paragraph))

    @patch('calibre_plugins.ebook_translator.lib.element.uid')
    def test_prepare_original_merge_separator(self, mock_uid):
        mock_uid.return_value = 'm1'
        self.handler.separator = Base.separator
        self.handler.translation_lang = 'en'
        self.handler.original_color = 'red'
        self.handler.translation_color = 'green'
        self.handler.column_gap = ('percentage', 20)
        self.handler.load_remove_rules()
        self.handler.load_reserve_rules()
        self.assertEqual([(
            0, 'm1', '<p id="a">a</p>\n\n<p id="b">b</p>\n\n<p id="c" '
            'class="c">c</p>\n\n', 'a\n\nb\n\nc\n\n', False)],
            self.handler.prepare_original(self.elements))
        for element in [e for e in self.elements if not e.ignored]:
            with self.subTest(element=element):
                self.assertEqual(Base.placeholder, element.placeholder)
                self.assertEqual('below', element.position)
                self.assertEqual('en', element.translation_lang)
                self.assertEqual('red', element.original_color)
                self.assertEqual('green', element.translation_color)
                self.assertEqual(('percentage', 20), element.column_gap)
                self.assertEqual(
                    './/*[self::x:rt or self::x:rp]',
                    self.handler.remove_pattern)
                self.assertRegex(
                    element.reserve_pattern, r'^\.//\*\[self::x:img.*style\]$')

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

    def test_prepare_translation(self):
        pass

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
        self.assertEqual('auto', elements[1].get('dir'))
        self.assertEqual('b', elements[2].text)
        self.assertEqual('B', elements[3].text)
        self.assertEqual('auto', elements[3].get('dir'))

        self.assertEqual('c', elements[5].text)
        self.assertEqual('C', elements[6].text)
        self.assertEqual('auto', elements[6].get('dir'))

    def test_add_translations_merge_cached_placeholder(self):
        self.handler.separator = Base.separator
        self.handler.target_direction = 'rtl'
        self.handler.prepare_original(self.elements)
        self.handler.add_translations([Paragraph(
            0, 'm1', '<p id="a">a</p><p id="b">b</p><p id="c">c</p>',
            'a {{id_0}} b {{id_1}} c {{id_3}}', False, None, None,
            'A {{id_0}} B {{id_1}} C {{id_3}}', 'ENGINE', 'LANG')])

        elements = self.xhtml.findall('./x:body/*', namespaces=ns)

        self.assertEqual(8, len(elements))
        self.assertEqual('a', elements[0].text)
        self.assertEqual('A', elements[1].text)
        self.assertEqual('rtl', elements[1].get('dir'))
        self.assertEqual('b', elements[2].text)
        self.assertEqual('B', elements[3].text)
        self.assertEqual('rtl', elements[3].get('dir'))

        self.assertEqual('c', elements[5].text)
        self.assertEqual('C', elements[6].text)
        self.assertEqual('rtl', elements[6].get('dir'))

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
            '<p class="c" dir="auto">A B<br/><br/>C</p>',
            get_string(elements[4], True))

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
            '<p class="c" dir="auto">A B<br/><br/>C</p>',
            get_string(elements[4], True))

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
            '<p class="c" dir="auto">A B<br/><br/>C</p>',
            get_string(elements[4], True))

    def test_add_translations_merge_placeholder_only(self):
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
        self.assertEqual(5, len(elements))
        self.assertEqual(
            '<p id="c" class="c" dir="auto">A B<br/><br/>C</p>',
            get_string(elements[-2], True))

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

        self.assertEqual(5, len(elements))
        self.assertEqual(
            '<p id="c" class="c" dir="auto">A B<br/><br/>C</p>',
            get_string(elements[-2], True))
