import re
import json
import copy

from lxml import etree
from lxml.builder import ElementMaker
from calibre import prepare_string_for_xml as xml_escape

from .utils import ns, css, uid, trim, sorted_mixed_keys
from .config import get_config


def get_string(element, remove_ns=False):
    element.text = element.text or ''  # prevent auto-closing empty elements
    markup = trim(etree.tostring(
        element, encoding='utf-8', with_tail=False).decode('utf-8'))
    return re.sub(r'\sxmlns([^"]+"){2}', '', markup) if remove_ns else markup


def get_name(element):
    return etree.QName(element).localname


class Element:
    def __init__(self, element, page_id=None):
        self.element = element
        self.page_id = page_id

        self.ignored = False
        self.reserve_elements = []
        self.original = []

    def _element_copy(self):
        return copy.deepcopy(self.element)

    def set_ignored(self, ignored):
        self.ignored = ignored

    def get_name(self):
        return None

    def get_raw(self):
        raise NotImplementedError()

    def get_text(self):
        raise NotImplementedError()

    def get_attributes(self):
        return None

    def delete(self):
        pass

    def get_content(self, placeholder):
        raise NotImplementedError()

    def add_translation(
            self, translation, placeholder, position, translation_lang=None,
            original_color=None, translation_color=None):
        raise NotImplementedError()


class SrtElement(Element):
    def get_raw(self):
        return self.element[2]

    def get_text(self):
        return self.element[2]

    def get_content(self, placeholder):
        return self.element[2]

    def add_translation(
            self, translation, placeholder, position, translation_lang=None,
            original_color=None, translation_color=None):
        if translation is not None:
            if position == 'only':
                self.element[2] = translation
            elif position in ('below', 'right'):
                self.element[2] += '\n%s' % translation
            else:
                self.element[2] = '%s\n%s' % (translation, self.element[2])
        return self.element


class MetadataElement(Element):
    def get_raw(self):
        return self.element.content

    def get_text(self):
        return self.element.content

    def get_content(self, placeholder):
        return self.element.content

    def add_translation(
            self, translation, placeholder, position, translation_lang=None,
            original_color=None, translation_color=None):
        if translation is not None:
            if position == 'only':
                self.element.content = translation
            elif position in ['above', 'left']:
                self.element.content = '%s %s' % (
                    translation, self.element.content)
            else:
                self.element.content = '%s %s' %(
                    self.element.content, translation)
        return self.element


class TocElement(Element):
    def get_raw(self):
        return self.element.title

    def get_text(self):
        return self.element.title

    def get_content(self, placeholder):
        return self.element.title

    def add_translation(
            self, translation, placeholder, position, translation_lang=None,
            original_color=None, translation_color=None):
        if translation is not None:
            items = [self.element.title, translation]
            self.element.title = items[-1] if position == 'only' else ' '.join(
                reversed(items) if position in ('above', 'left') else items)
        return self.element


class PageElement(Element):
    def _get_descendents(self, element, tags):
        xpath = './/*[%s]' % ' or '.join(['self::x:%s' % tag for tag in tags])
        return element.xpath(xpath, namespaces=ns)

    def get_name(self):
        return get_name(self.element)

    def get_raw(self):
        return get_string(self.element, True)

    def get_text(self):
        return trim(''.join(self.element.itertext()))

    def get_attributes(self):
        attributes = dict(self.element.attrib.items())
        return json.dumps(attributes) if attributes else None

    def delete(self):
        self.element.getparent().remove(self.element)

    def get_content(self, placeholder):
        element_copy = self._element_copy()
        for noise in self._get_descendents(
                element_copy, ('rt', 'rp', 'sup', 'sub')):
            parent = noise.getparent()
            parent.text = (parent.text or '') + (noise.tail or '')
            parent.remove(noise)

        self.reserve_elements = self._get_descendents(
            element_copy, ('img', 'code', 'br', 'hr', 'sub', 'sup', 'kbd'))
        count = 0
        for reserve in self.reserve_elements:
            replacement = placeholder[0].format(format(count, '05'))
            previous, parent = reserve.getprevious(), reserve.getparent()
            if previous is not None:
                previous.tail = (previous.tail or '') + replacement
                previous.tail += (reserve.tail or '')
            else:
                parent.text = (parent.text or '') + replacement
                parent.text += (reserve.tail or '')
            reserve.tail = None
            parent.remove(reserve)
            count += 1

        return trim(''.join(element_copy.itertext()))

    def _polish_translation(self, translation):
        translation = translation.replace('\n', '<br />')
        # Condense consecutive letters to a maximum of four.
        return re.sub(r'((\w)\2{3})\2*', r'\1', translation)

    def add_translation(
            self, translation, placeholder, position, translation_lang=None,
            original_color=None, translation_color=None):
        if translation is None:
            if position in ('left', 'right'):
                if original_color is not None:
                    self.element_color.set(
                        'style', 'color:%s' % original_color)
                self.element.addnext(
                    self._create_table(position, self._element_copy()))
            if position in ('only', 'left', 'right'):
                self.delete()
            return self.element
        # Escape the markups (<m id=1 />) to replace escaped markups.
        translation = xml_escape(translation)
        for rid, reserve in enumerate(self.reserve_elements):
            pattern = placeholder[1].format(r'\s*'.join(format(rid, '05')))
            # Prevent processe any backslash escapes in the replacement.
            translation = re.sub(
                xml_escape(pattern), lambda _: get_string(reserve),
                translation)
        translation = self._polish_translation(translation)

        new_element = etree.XML('<{0} xmlns="{1}">{2}</{0}>'.format(
            get_name(self.element), ns['x'], trim(translation)))
        # new_element = self.element.makeelement(
        #     get_name(self.element), nsmap={'xhtml': ns['x']})
        # new_element.text = trim(translation)

        # Preserve all attributes from the original element.
        for name, value in self.element.items():
            if name == 'id' and position != 'only':
                continue
            if name == 'dir':
                value = 'auto'
            new_element.set(name, value)
        if translation_lang is not None:
            new_element.set('lang', translation_lang)
        if original_color is not None:
            self.element.set('style', 'color:%s' % original_color)
        if translation_color is not None:
            new_element.set('style', 'color:%s' % translation_color)

        self.element.tail = None  # Make sure the element has no tail

        if position in ('left', 'right'):
            element_copy = self._element_copy()
            if original_color is not None:
                element_copy.set('style', 'color:%s' % original_color)
            self.element.addnext(
                self._create_table(position, element_copy, new_element))
        elif position == 'above':
            self.element.addprevious(new_element)
        else:
            self.element.addnext(new_element)
        if position in ['left', 'right', 'only']:
            self.delete()
        return new_element

    def _create_table(self, position, original, translation=None):
        # table = self.element.makeelement('table', attrib={'width': '100%'})
        table = etree.XML(
            '<table xmlns="{}" width="100%"></table>'.format(ns['x']))
        tr = etree.SubElement(table, 'tr')
        td_left = etree.SubElement(
            tr, 'td', attrib={'width': '45%', 'valign': 'top'})
        etree.SubElement(tr, 'td', attrib={'width': '10%'})
        td_right = etree.SubElement(
            tr, 'td', attrib={'width': '45%', 'valign': 'top'})
        if position == 'left':
            if translation is not None:
                td_left.append(translation)
            td_right.append(original)
        if position == 'right':
            td_left.append(original)
            if translation is not None:
                td_right.append(translation)
        return table


class Extraction:
    __version__ = '20230608'

    def __init__(self, pages, rule_mode, filter_scope, filter_rules,
                 element_rules):
        self.pages = pages

        self.rule_mode = rule_mode
        self.filter_scope = filter_scope
        self.filter_rules = filter_rules
        self.element_rules = element_rules

        self.filter_patterns = []
        self.element_patterns = []

        self.load_filter_patterns()
        self.load_element_patterns()

    def load_filter_patterns(self):
        default_rules = [
            r'^[-\d\s\.\'\\"‘’“”,=~!@#$%^&º*|<>?/`—…+:_(){}[\]]+$']
        patterns = [re.compile(rule) for rule in default_rules]
        for rule in self.filter_rules:
            if self.rule_mode == 'normal':
                rule = re.compile(re.escape(rule), re.I)
            elif self.rule_mode == 'case':
                rule = re.compile(re.escape(rule))
            else:
                rule = re.compile(rule)
            patterns.append(rule)
        self.filter_patterns = patterns

    def load_element_patterns(self):
        rules = ['pre', 'code']
        rules.extend(self.element_rules)
        patterns = []
        for selector in rules:
            rule = css(selector)
            rule and patterns.append(rule)
        self.element_patterns = patterns

    def get_sorted_pages(self):
        pages = []
        pattern = re.compile(r'\.(xhtml|html|htm|xml|xht)$')
        for page in self.pages:
            if isinstance(page.data, etree._Element) \
                    and pattern.search(page.href):
                pages.append(page)
        return sorted(pages, key=lambda page: sorted_mixed_keys(page.href))

    def get_elements(self):
        elements = []
        for page in self.get_sorted_pages():
            body = page.data.find('./x:body', namespaces=ns)
            elements.extend(self.extract_elements(page.id, body, []))
        return filter(self.filter_content, elements)

    def need_ignore(self, element):
        for pattern in self.element_patterns:
            if element.xpath(pattern, namespaces=ns):
                return True
        return False

    def extract_elements(self, page_id, root, elements=[]):
        priority_elements = ['p', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
        for element in root.findall('./*'):
            if self.need_ignore(element):
                continue
            element_has_content = False
            if element.text is not None and trim(element.text) != '':
                element_has_content = True
            else:
                children = element.findall('./*')
                if children and get_name(element) in priority_elements:
                    element_has_content = True
                else:
                    for child in children:
                        if child.tail is not None and trim(child.tail) != '':
                            element_has_content = True
                            break
            if element_has_content:
                elements.append(PageElement(element, page_id))
            else:
                self.extract_elements(page_id, element, elements)
        # Return root if all children have no content
        root = PageElement(root, page_id)
        return elements if elements else [root]

    def filter_content(self, element):
        # Ignore the element contains empty content
        content = element.get_text()
        if content == '':
            return False
        for entity in ('&lt;', '&gt;'):
            content = content.replace(entity, '')
        for pattern in self.filter_patterns:
            if pattern.search(content):
                element.set_ignored(True)
        # Filter HTML according to the rules
        if self.filter_scope == 'html':
            markup = element.get_raw()
            for pattern in self.filter_patterns:
                if pattern.search(markup):
                    element.set_ignored(True)
        return True


class ElementHandler:
    def __init__(self, placeholder, separator, position, merge_length=0):
        self.placeholder = placeholder
        self.separator = separator
        self.position = position
        self.merge_length = merge_length

        self.translation_lang = None
        self.original_color = None
        self.translation_color = None

        self.elements = {}
        self.originals = []

        self.base_originals = []

    def get_merge_length(self):
        return self.merge_length

    def set_translation_lang(self, lang):
        self.translation_lang = lang

    def set_original_color(self, color):
        self.original_color = color

    def set_translation_color(self, color):
        self.translation_color = color

    def remove_unused_elements(self):
        if self.position == 'only':
            for element in self.elements.values():
                element.delete()

    def prepare_original(self, elements):
        count = 0
        for oid, element in enumerate(elements):
            raw = element.get_raw()
            content = element.get_content(self.placeholder)
            md5 = uid('%s%s' % (oid, content))
            attrs = element.get_attributes()
            if not element.ignored:
                self.elements[count] = element
                self.base_originals.append(content)
                count += 1
            self.originals.append(
                (oid, md5, raw, content, element.ignored, attrs,
                 element.page_id))
        return self.originals

    def add_translations(self, paragraphs):
        count = 0
        for paragraph in paragraphs:
            if paragraph.original not in self.base_originals:
                continue
            element = self.elements.get(count)
            if not element:
                continue
            translation = paragraph.translation
            if translation:
                element.add_translation(
                    translation, self.placeholder, self.position,
                    self.translation_lang, self.original_color,
                    self.translation_color)
                self.elements.pop(count)
            count += 1
        for eid, element in self.elements.copy().items():
            if element.ignored:
                self.elements.pop(eid)
        self.remove_unused_elements()


class ElementHandlerMerge(ElementHandler):
    def prepare_original(self, elements):
        raw = ''
        txt = ''
        oid = 0
        count = 0
        for element in elements:
            if element.ignored:
                continue
            self.elements[count] = element
            code = element.get_raw()
            content = element.get_content(self.placeholder)
            self.base_originals.append(content)
            count += 1
            content += self.separator
            if len(txt + content) < self.merge_length:
                raw += code + self.separator
                txt += content
                continue
            elif txt:
                md5 = uid('%s%s' % (oid, txt))
                self.originals.append((oid, md5, raw, txt, False))
                oid += 1
            raw = code
            txt = content
        md5 = uid('%s%s' % (oid, txt))
        txt and self.originals.append((oid, md5, raw, txt, False))
        return self.originals

    def align_paragraph(self, paragraph):
        # Compatible with using the placeholder as the separator.
        if paragraph.original[-2:] != self.separator:
            pattern = re.compile(
                r'\s*%s\s*' % self.placeholder[1].format(r'(0|[^0]\d*)'))
            paragraph.original = pattern.sub(
                self.separator, paragraph.original)
            paragraph.translation = pattern.sub(
                self.separator, paragraph.translation)
        # Ensure the translation count matches the actual elements count.
        originals = paragraph.original.strip().split(self.separator)
        pattern = re.compile('%s+' % self.separator)
        translation = pattern.sub(self.separator, paragraph.translation)
        translations = translation.strip().split(self.separator)
        offset = len(originals) - len(translations)
        if offset > 0:
            # TODO: Merge the original and translation for the left and right.
            if self.position in ['left', 'right']:
                addition = [None] * offset
                translations += addition
            else:
                merged_translations = '\n\n'.join(translations)
                translations = [None] * (len(originals) - 1)
                if self.position in ['above']:
                    translations.insert(0, merged_translations)
                else:
                    translations.append(merged_translations)
        elif offset < 0:
            offset = len(originals) - 1
            translations = translations[:offset] + [
                '\n\n'.join(translations[offset:])]
        # for original in originals:
        #     if original and original not in self.base_originals:
        #         translations.pop(originals.index(original))
        return translations

    def add_translations(self, paragraphs):
        translations = []
        for paragraph in paragraphs:
            translations.extend(self.align_paragraph(paragraph))
        total = len(translations)
        count = 0
        for eid, element in self.elements.copy().items():
            if element.ignored or eid >= total:
                continue
            element.add_translation(
                translations[count], self.placeholder, self.position,
                self.translation_lang, self.original_color,
                self.translation_color)
            count += 1
            self.elements.pop(eid)
        self.remove_unused_elements()


def get_srt_elements(path):
    sections = []

    try:
        with open(path, 'r', newline=None) as f:
            content = f.read().strip()
    except Exception:
        with open(path, 'rU') as f:
            content = f.read().strip()
    for section in content.split('\n\n'):
        lines = section.split('\n')
        number = lines.pop(0)
        time = lines.pop(0)
        content = '\n'.join(lines)
        sections.append([number, time, content])

    return [SrtElement(section) for section in sections]


def get_metadata_elements(metadata):
    elements = []
    names = (
        'title', 'creator', 'publisher', 'rights', 'subject', 'contributor')
    pattern = re.compile(r'[a-z]+')
    for key in metadata.iterkeys():
        if key not in names:
            continue
        items = getattr(metadata, key)
        for item in items:
            if pattern.search(item.content) is None:
                continue
            elements.append(MetadataElement(item, 'content.opf'))
    return elements


def get_toc_elements(nodes, elements=[]):
    """Be aware that elements should not overlap with existing data."""
    for node in nodes:
        elements.append(TocElement(node, 'toc.ncx'))
        if len(node.nodes) > 0:
            get_toc_elements(node.nodes, elements)
    return elements


def get_page_elements(pages):
    config = get_config()
    rule_mode = config.get('rule_mode')
    filter_scope = config.get('filter_scope')
    filter_rules = config.get('filter_rules')
    element_rules = config.get('element_rules', [])
    extraction = Extraction(
        pages, rule_mode, filter_scope, filter_rules, element_rules)
    return extraction.get_elements()


def get_element_handler(placeholder, separator):
    config = get_config()
    position_alias = {'before': 'above', 'after': 'below'}
    position = config.get('translation_position', 'below')
    position = position_alias.get(position) or position
    handler = ElementHandler(placeholder, separator, position)
    if config.get('merge_enabled'):
        handler = ElementHandlerMerge(
            placeholder, separator, position, config.get('merge_length'))
    handler.set_original_color(config.get('original_color'))
    handler.set_translation_color(config.get('translation_color'))
    return handler
