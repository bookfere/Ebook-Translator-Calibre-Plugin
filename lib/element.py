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
    def __init__(self, element, page_id=None):
        self.element = element
        self.element_copy = copy.deepcopy(element)
        self.page_id = page_id
        self.ignored = False

        self.reserve_elements = []
        self.original = []

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

    def add_translation(self, translation, placeholder, position=None,
                        lang=None, color=None):
        raise NotImplementedError()


class SrtElement(Element):
    def get_raw(self):
        return self.element[2]

    def get_text(self):
        return self.element[2]

    def get_content(self, placeholder):
        return self.element[2]

    def add_translation(self, translation, placeholder, position=None,
                        lang=None, color=None):
        if position == 'only':
            self.element[2] = translation
        elif position == 'after':
            self.element[2] += '\n%s' % translation
        else:
            self.element[2] = '%s\n%s' % (translation, self.element[2])
        return self.element


class TocElement(Element):
    def get_raw(self):
        return self.element.title

    def get_text(self):
        return self.element.title

    def get_content(self, placeholder):
        return self.element.title

    def add_translation(self, translation, placeholder, position=None,
                        lang=None, color=None):
        items = [self.element.title, translation]
        self.element.title = items[-1] if position == 'only' else \
            ' '.join(reversed(items) if position == 'before' else items)
        return self.element


class PageElement(Element):
    def _get_descendents(self, tags):
        xpath = './/*[%s]' % ' or '.join(['self::x:%s' % tag for tag in tags])
        return self.element_copy.xpath(xpath, namespaces=ns)

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
        for noise in self._get_descendents(('rt', 'rp', 'sup', 'sub')):
            parent = noise.getparent()
            parent.text = (parent.text or '') + (noise.tail or '')
            parent.remove(noise)

        self.reserve_elements = self._get_descendents(
            ('img', 'code', 'br', 'hr', 'sub', 'sup', 'kbd'))
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

    def _polish_translation(self, translation):
        # Condense consecutive letters to a maximum of four.
        return re.sub(r'((\w)\2{3})\2*', r'\1', translation)

    def add_translation(self, translation, placeholder, position=None,
                        lang=None, color=None):
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
        # Preserve all attributes from the original element.
        for name, value in self.element.items():
            if name == 'id' and position != 'only':
                continue
            if name == 'dir':
                value = 'auto'
            new_element.set(name, value)
        if color is not None:
            new_element.set('style', 'color:%s' % color)
        if lang is not None:
            new_element.set('lang', lang)

        self.element.tail = None  # Make sure the element has no tail
        if position == 'before':
            self.element.addprevious(new_element)
        else:
            self.element.addnext(new_element)
        if position == 'only':
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
        pages = []
        for page in self.pages:
            if isinstance(page.data, etree._Element) and 'html' in page.href:
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
    def __init__(self, placeholder, separator, merge_length=0):
        self.placeholder = placeholder
        self.separator = separator
        self.merge_length = merge_length

        self.position = None
        self.color = None
        self.lang = None

        self.elements = {}
        self.originals = []

        self.base_originals = []

    def get_merge_length(self):
        return self.merge_length

    def set_translation_position(self, position):
        self.position = position

    def set_translation_color(self, color):
        self.color = color

    def set_translation_lang(self, lang):
        self.lang = lang

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
                    self.lang, self.color)
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
            translations += ['-'] * offset
        elif offset < 0:
            translations = translations[:offset]
        for original in originals:
            if original and original not in self.base_originals:
                translations.pop(originals.index(original))
        return translations

    def add_translations(self, paragraphs):
        translations = []
        for paragraph in paragraphs:
            translations.extend(self.align_paragraph(paragraph))
        total = len(translations)
        count = 0
        for eid, element in self.elements.copy().items():
            # TODO: Maybe the translation count does not match the elements
            # count due to the criteria of the old version has been changed.
            if element.ignored or eid >= total:
                continue
            element.add_translation(
                translations[count], self.placeholder, self.position,
                self.lang, self.color)
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
    handler = ElementHandler(placeholder, separator)
    if config.get('merge_enabled'):
        handler = ElementHandlerMerge(
            placeholder, separator, config.get('merge_length'))
    handler.set_translation_position(
        config.get('translation_position'))
    handler.set_translation_color(config.get('translation_color'))
    return handler
