import re
import json
import copy

from lxml import etree
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
    def __init__(self, element, page_id):
        self.element = element
        self.element_copy = copy.deepcopy(element)
        self.page_id = page_id
        self.ignored = False

        self.reserve_elements = []
        self.reserve_words = []
        self.original = []

    def set_ignored(self, ignored):
        self.ignored = ignored

    def get_name(self):
        return get_name(self.element)

    def get_descendents(self, tags):
        xpath = './/*[%s]' % ' or '.join(['self::x:%s' % tag for tag in tags])
        return self.element_copy.xpath(xpath, namespaces=ns)

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
        for noise in self.get_descendents(('rt', 'rp', 'sup', 'sub')):
            parent = noise.getparent()
            parent.text = (parent.text or '') + (noise.tail or '')
            parent.remove(noise)

        self.reserve_elements = self.get_descendents(('img', 'code'))
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

        return trim(''.join(self.element_copy.itertext()))

    def add_translation(self, translation, placeholder, position=None,
                        lang=None, color=None):
        translation = xml_escape(translation)
        count = 0
        for reserve in self.reserve_elements:
            # Escape the markups (<m id=1 />) to replace escaped markups.
            pattern = placeholder[1].format(format(count, '05'))
            # Prevent potential invalid escapes from affecting the replacement.
            translation = re.sub(
                xml_escape(pattern), lambda _: get_string(reserve),
                translation)
            count += 1

        new_element = etree.XML('<{0} xmlns="{1}">{2}</{0}>'.format(
            get_name(self.element), ns['x'], translation))
        if color is not None:
            new_element.set('style', 'color:%s' % color)
        if lang is not None:
            new_element.set('lang', lang)
        klass = self.element.get('class')
        if klass is not None:
            new_element.set('class', self.element.get('class'))
        self.element.tail = None  # Make sure it has no tail
        if position == 'before':
            self.element.addprevious(new_element)
        else:
            self.element.addnext(new_element)
        if position == 'only':
            if get_name(new_element) =='a':
                new_element.set('href', self.element.get('href'))           
            self.delete()
        return new_element


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
        return sorted(
            [page for page in self.pages if 'html' in page.media_type],
            key=lambda page: sorted_mixed_keys(page.href))

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
        priority_elements = ['p', 'pre']
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
                elements.append(Element(element, page_id))
            else:
                self.extract_elements(page_id, element, elements)
        # Return root if all children have no content
        root = Element(root, page_id)
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
    def __init__(self, placeholder):
        self.placeholder = placeholder

        self.merge_length = 0
        self.position = None
        self.color = None
        self.lang = None

        self.elements = {}
        self.original = []

    def set_merge_length(self, length):
        self.merge_length = length

    def get_merge_length(self):
        return self.merge_length

    def set_translation_position(self, position):
        self.position = position

    def set_translation_color(self, color):
        self.color = color

    def set_translation_lang(self, lang):
        self.lang = lang

    def get_elements(self):
        return self.elements

    def remove_unused_elements(self):
        if self.position == 'only':
            for element in self.elements.values():
                element.delete()

    def prepare_original(self, elements):
        if self.merge_length == 0:
            for eid, element in enumerate(elements):
                self.elements[eid] = element
                raw = element.get_raw()
                content = element.get_content(self.placeholder)
                md5 = uid('%s%s' % (eid, content))
                attrs = element.get_attributes()
                self.original.append(
                    (eid, md5, raw, content, element.ignored, attrs,
                     element.page_id))
            return self.original

        raw = ''
        content = ''
        count = 0
        for eid, element in enumerate(elements):
            if element.ignored:
                continue
            self.elements[eid] = element
            placeholder = ' %s ' % self.placeholder[0].format(eid)
            code = element.get_raw()
            text = element.get_content(self.placeholder) + placeholder
            attrs = element.get_attributes()
            if len(content + text) < self.merge_length:
                raw += code
                content += text
                continue
            elif content:
                md5 = uid('%s%s' % (count, content))
                self.original.append((count, md5, raw, content, False))
                count += 1
            raw = code
            content = text
        md5 = uid('%s%s' % (count, content))
        content and self.original.append((count, md5, raw, content, False))
        return self.original

    def add_translations(self, paragraphs):
        if self.merge_length == 0:
            for paragraph in paragraphs:
                element = self.elements.get(paragraph.id)
                if not element:
                    continue
                translation = paragraph.translation
                if translation:
                    element.add_translation(
                        translation, self.placeholder, self.position,
                        self.lang, self.color)
                    self.elements.pop(paragraph.id)
            for eid, element in self.elements.copy().items():
                if element.ignored:
                    self.elements.pop(eid)
            self.remove_unused_elements()
            return

        content = ''.join(
            paragraph.translation for paragraph in paragraphs
            if paragraph.translation)

        for eid, element in self.elements.copy().items():
            matches = re.search(self.placeholder[1].format(eid), content)
            if not matches:
                continue
            pattern = matches.group(0)
            end = content.find(pattern)
            part = content[:end]
            content = content.replace(part + pattern, '', 1)
            if not element.ignored:
                element.add_translation(
                    part.strip(), self.placeholder, self.position, self.lang,
                    self.color)
                self.elements.pop(eid)
        self.remove_unused_elements()


def get_ebook_elements(pages):
    config = get_config()
    rule_mode = config.get('rule_mode')
    filter_scope = config.get('filter_scope')
    filter_rules = config.get('filter_rules')
    element_rules = config.get('element_rules', [])
    extraction = Extraction(
        pages, rule_mode, filter_scope, filter_rules, element_rules)
    return extraction.get_elements()


def get_element_handler(placeholder):
    config = get_config()
    handler = ElementHandler(placeholder)
    if config.get('merge_enabled'):
        handler.set_merge_length(config.get('merge_length'))
    handler.set_translation_position(
        config.get('translation_position'))
    handler.set_translation_color(config.get('translation_color'))

    return handler

class TOCHandler(ElementHandler):
    placeholder = []
    offset = 50000
    def prepare_original(self, elements):
        if self.merge_length == 0:
            for eid, element in enumerate(elements):
                self.elements[eid] = element
                content = element.title
                raw = element.href
                attrs = element.klass
                self.original.append(
                    (eid + self.offset, uid(content), raw, content, False, attrs,
                     element.id))
            return self.original

        raw = ''
        content = ''
        count = 0 + self.offset
        for eid, element in enumerate(elements):
            self.elements[eid] = element
            # placeholder = ' %s ' % '{{id_{}}}'.format(eid)
            placeholder = ' %s ' % self.placeholder[0].format(eid)
            code = str(element.href) + ' '
            text = element.title + placeholder
            attrs = element.klass
            if len(content + text) < self.merge_length:
                raw += code
                content += text
                continue
            elif content:
                self.original.append(
                    (count, uid(content), raw, content, False))
                count += 1
            raw = code
            content = text
        content and self.original.append(
                (count, uid(content), raw, content, False))
        return self.original

    def add_translation(self,Toc,translation):
        position = self.position
        if position == 'before':
            Toc.title = translation + Toc.title
        else:
            Toc.title = Toc.title + translation
        if position == 'only':
            Toc.title = translation

    def add_translations(self, paragraphs):
        if self.merge_length == 0:
            for paragraph in paragraphs:
                element = self.elements.get(paragraph.id - self.offset)
                if not element:
                    continue
                translation = paragraph.translation
                if translation:
                    self.add_translation(element,translation)
                    self.elements.pop(paragraph.id - self.offset)
            return

        content = ''.join(
            paragraph.translation for paragraph in paragraphs
            if paragraph.translation)

        for eid, element in self.elements.copy().items():
            matches = re.search(self.placeholder[1].format(eid), content)
            if not matches:
                continue
            placeholder = matches.group(0)
            end = content.find(placeholder)
            part = content[:end]
            content = content.replace(part + placeholder, '', 1)
            if not False: #element.ignored:
                self.add_translation(element,part.strip())
                self.elements.pop(eid)

    def all_paragraphs(self):
        from .cache import Paragraph
        paragraphs = []
        for item in self.original:
            paragraph = Paragraph(*item)
            paragraphs.append(paragraph)
        return paragraphs
    

def get_TOCHandler(lang_code,placeholder):
    config = get_config()
    handler = TOCHandler(placeholder)
    if config.get('merge_enabled'):
        handler.set_merge_length(config.get('merge_length'))
    handler.set_translation_position(
        config.get('translation_position'))
    handler.set_translation_color(config.get('translation_color'))
    handler.set_translation_lang(lang_code)

    return handler
