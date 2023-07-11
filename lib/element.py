import os
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


class Glossary(dict):
    def load_from_file(self, path):
        """In the universal newlines mode (by adding 'U' to the mode in
        Python 2.x or keeping newline=None in Python 3.x), there is no need
        to use `os.linesep`. Instead, using '\n' can properly parse newlines
        when reading from or writing to files on multiple platforms.
        """
        content = None
        try:
            with open(path, 'r', newline=None) as f:
                content = f.read().strip()
        except TypeError as e:
            try:
                with open(path, 'rU') as f:
                    content = f.read().strip()
            except Exception:
                pass
        if not content:
            return
        for group in content.split('\n' * 2):
            group = group.strip().split(os.linesep)
            if len(group) > 2:
                continue
            self[group[0]] = group[0] if len(group) == 1 else group[1]


class Element:
    def __init__(self, element, page_id, placeholder, glossary):
        self.element = element
        self.element_copy = copy.deepcopy(element)
        self.page_id = page_id
        self.placeholder = placeholder
        self.glossary = glossary
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

    def get_content(self):
        for noise in self.get_descendents(('rt', 'rp', 'sup', 'sub')):
            parent = noise.getparent()
            parent.text = (parent.text or '') + (noise.tail or '')
            parent.remove(noise)

        self.reserve_elements = self.get_descendents(('img', 'code'))
        count = 0
        for reserve in self.reserve_elements:
            placeholder = self.placeholder[0].format(format(count, '05'))
            previous, parent = reserve.getprevious(), reserve.getparent()
            if previous is not None:
                previous.tail = (previous.tail or '') + placeholder
                previous.tail += (reserve.tail or '')
            else:
                parent.text = (parent.text or '') + placeholder
                parent.text += (reserve.tail or '')
            reserve.tail = None
            parent.remove(reserve)
            count += 1

        content = trim(''.join(self.element_copy.itertext()))

        for word in self.glossary.keys():
            placeholder = self.placeholder[0].format(format(count, '05'))
            content = content.replace(word, placeholder)
            count += 1

        return content

    def get_attributes(self):
        attributes = dict(self.element.attrib.items())
        return json.dumps(attributes) if attributes else None

    def delete(self):
        self.element.getparent().remove(self.element)

    def add_translation(self, translation, position=None, lang=None,
                        color=None):
        translation = xml_escape(translation)
        count = 0
        for reserve in self.reserve_elements:
            # Escape the markups (<m id=1 />) to replace escaped markups.
            pattern = self.placeholder[1].format(format(count, '05'))
            # Prevent potential invalid escapes from affecting the replacement.
            translation = re.sub(
                xml_escape(pattern), lambda _: get_string(reserve),
                translation)
            count += 1

        for word in self.glossary.values():
            pattern = self.placeholder[1].format(format(count, '05'))
            translation = re.sub(
                xml_escape(pattern), lambda _: word, translation)
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
            self.delete()
        return new_element


class Extraction:
    __version__ = '20230608'

    def __init__(self, pages, placeholder, glossary, rule_mode, filter_scope,
                 filter_rules, element_rules):
        self.pages = pages
        self.placeholder = placeholder
        self.glossary = glossary

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
                elements.append(
                    Element(element, page_id, self.placeholder, self.glossary))
            else:
                self.extract_elements(page_id, element, elements)
        # Return root if all children have no content
        root = Element(root, page_id, self.placeholder, self.glossary)
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
            if element.ignored:
                continue
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
        content and self.original.append(
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
    config = get_config()
    glossary = Glossary()
    if config.get('glossary_enabled'):
        glossary.load_from_file(config.get('glossary_path'))
    rule_mode = config.get('rule_mode')
    filter_scope = config.get('filter_scope')
    filter_rules = config.get('filter_rules')[:]
    element_rules = config.get('element_rules', [])
    extraction = Extraction(pages, placeholder, glossary, rule_mode,
                            filter_scope, filter_rules, element_rules)
    return extraction.get_elements()


def get_element_handler():
    config = get_config()
    handler = ElementHandler()
    if config.get('merge_enabled'):
        handler.set_merge_length(config.get('merge_length'))
    handler.set_translation_position(
        config.get('translation_position'))
    handler.set_translation_color(config.get('translation_color'))

    return handler
