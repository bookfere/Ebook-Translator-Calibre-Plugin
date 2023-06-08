import re
import json
import copy

from lxml import etree
from calibre import prepare_string_for_xml as xml_escape

from .utils import ns, css, uid, trim, sorted_mixed_keys
from .config import get_config


def get_string(element, remove_ns=False):
    element.text = element.text or ''  # prevent auto-closing empty elements
    string = trim(etree.tostring(
        element, encoding='utf-8', with_tail=False).decode('utf-8'))
    return string if not remove_ns else re.sub(r'\sxmlns(.*?"){2}', '', string)


def get_name(element):
    return etree.QName(element).localname


class Element:
    def __init__(self, element, page_id, placeholder):
        self.element = element
        self.page_id = page_id
        self.placeholder = placeholder
        self.ignored = False

        self.reserves = []
        self.original = []

    def set_ignored(self, ignored):
        self.ignored = ignored

    def get_name(self):
        return get_name(self.element)

    def get_descendents(self, tags):
        xpath = './/*[%s]' % ' or '.join(['self::x:%s' % tag for tag in tags])
        return self.element.xpath(xpath, namespaces=ns)

    def get_raw(self):
        return get_string(self.element, True)

    def get_text(self):
        return trim(''.join(self.element.itertext()))

    def get_content(self):
        for noise in self.get_descendents(('rt', 'rp', 'sup')):
            parent = noise.getparent()
            parent.text = (parent.text or '') + (noise.tail or '')
            parent.remove(noise)

        self.reserves = self.get_descendents(('img', 'code'))
        for rid, reserve in enumerate(self.reserves):
            placeholder = self.placeholder[0].format(format(rid, '05'))
            previous, parent = reserve.getprevious(), reserve.getparent()
            if previous is not None:
                previous.tail = (previous.tail or '') + placeholder
                previous.tail += (reserve.tail or '')
            else:
                parent.text = (parent.text or '') + placeholder
                parent.text += (reserve.tail or '')
            parent.remove(reserve)
        return trim(''.join(self.element.itertext()))

    def get_attributes(self):
        attributes = dict(self.element.attrib.items())
        return json.dumps(attributes) if attributes else None

    def delete(self):
        self.element.getparent().remove(self.element)

    def add_translation(self, translation, position=None, lang=None,
                        color=None):
        translation = xml_escape(translation)
        for rid, reserve in enumerate(self.reserves):
            # Escape the potential regex metacharacters in text.
            for item in reserve.getiterator():
                if item.text is not None:
                    item.text = re.escape(item.text)
                if item.tail is not None:
                    item.tail = re.escape(item.tail)
            translation = re.sub(
                # Escape the markups to replace escaped markups.
                xml_escape(self.placeholder[1].format(format(rid, '05'))),
                get_string(reserve), translation)

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
            self.delete()
        return new_element


class Extraction:
    __version__ = '20230608'

    def __init__(self, pages, placeholder):
        self.pages = pages
        self.placeholder = placeholder
        # TODO: Refactor these attributes.
        self.config = get_config()
        self.element_rules = self.config.get('element_rules', [])
        self.rule_mode = self.config.get('rule_mode')
        self.filter_scope = self.config.get('filter_scope')
        self.filter_rules = self.config.get('filter_rules')[:]

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

    def get_element_rules(self):
        rules = [css('pre'), css('code')]
        for selector in self.element_rules:
            rule = css(selector)
            rule and rules.append(rule)
        return rules

    def need_ignore(self, element):
        for rule in self.get_element_rules():
            if element.xpath(rule, namespaces=ns):
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
                elements.append(Element(element, page_id, self.placeholder))
            else:
                self.extract_elements(page_id, element, elements)
        # Return root if all children have no content
        root = Element(root, page_id, self.placeholder)
        return elements if elements else [root]

    def filter_content(self, element):
        self.filter_rules.append(
            r'^[-\d\s\.\'\\"‘’“”,=~!@#$%^&º*|<>?/`—…+:_(){}[\]]+$')

        patterns = []
        for rule in self.filter_rules:
            if self.rule_mode == 'normal':
                rule = re.compile(r'^.*?%s' % rule, re.I)
            elif self.rule_mode == 'case':
                rule = re.compile(r'^.*?%s' % rule)
            else:
                rule = re.compile(rule)
            patterns.append(rule)
        # Ignore the element contains empty content
        content = element.get_text()
        if content == '':
            element.set_ignored(True)
        for entity in ('&lt;', '&gt;'):
            content = content.replace(entity, '')
        for pattern in patterns:
            if pattern.match(content):
                element.set_ignored(True)
        # Filter HTML according to the rules
        if self.filter_scope == 'html':
            markup = element.get_raw()
            for pattern in patterns:
                if pattern.match(markup):
                    element.set_ignored(True)
        return True


class ElementHandler:
    def __init__(self):
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

    def prepare_original(self, elements):
        if self.merge_length == 0:
            for eid, element in enumerate(elements):
                self.elements[eid] = element
                content = element.get_content()
                raw = element.get_raw()
                attrs = element.get_attributes()
                self.original.append(
                    (eid, uid(content), raw, content, element.ignored, attrs,
                     element.page_id))
            return self.original

        raw = ''
        content = ''
        count = 0
        for eid, element in enumerate(elements):
            self.elements[eid] = element
            placeholder = ' %s ' % element.placeholder[0].format(eid)
            code = element.get_raw()
            text = element.get_content() + placeholder
            attrs = element.get_attributes()
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
        if content:
            self.original.append(
                (count, uid(content), raw, content, False))

        return self.original

    def remove_unused_elements(self):
        if self.position == 'only':
            for element in self.elements.values():
                element.delete()

    def add_translations(self, paragraphs):
        if self.merge_length == 0:
            for paragraph in paragraphs:
                element = self.elements.get(paragraph.id)
                if not element:
                    continue
                translation = paragraph.translation
                if translation:
                    element.add_translation(
                        translation, self.position, self.lang, self.color)
                    self.elements.pop(paragraph.id)
            self.remove_unused_elements()
            return

        content = ''.join(
            paragraph.translation for paragraph in paragraphs
            if paragraph.translation)

        for eid, element in self.elements.copy().items():
            matches = re.search(element.placeholder[1].format(eid), content)
            if not matches:
                continue
            placeholder = matches.group(0)
            end = content.find(placeholder)
            part = content[:end]
            content = content.replace(part + placeholder, '', 1)
            if not element.ignored:
                element.add_translation(
                    part.strip(), self.position, self.lang, self.color)
                self.elements.pop(eid)
        self.remove_unused_elements()


def get_ebook_elements(pages, placeholder):
    return Extraction(pages, placeholder).get_elements()


def get_element_handler(lang_code):
    config = get_config()
    handler = ElementHandler()
    if config.get('merge_enabled'):
        handler.set_merge_length(config.get('merge_length'))
    handler.set_translation_position(
        config.get('translation_position'))
    handler.set_translation_color(config.get('translation_color'))
    handler.set_translation_lang(lang_code)

    return handler
