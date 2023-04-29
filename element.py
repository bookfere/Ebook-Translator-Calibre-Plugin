import re
import copy

from lxml import etree
from calibre import prepare_string_for_xml as escape
from calibre_plugins.ebook_translator.utils import ns, uid, trim


def get_string(element):
    return trim(etree.tostring(element, encoding='utf-8').decode('utf-8'))


class Element:
    def __init__(self, element):
        self.element = element
        self.element_copy = copy.deepcopy(element)
        self.reserves = []

    def get_content(self):
        noises = self.element_copy.xpath('.//*[self::x:rt]', namespaces=ns)
        for noise in noises:
            noise.getparent().remove(noise)

        self.reserves = self.element_copy.xpath(
            './/*[self::x:img]', namespaces=ns)
        for reserve in self.reserves:
            placeholder = 'el_%s' % id(reserve)
            previous = reserve.getprevious()
            previous.tail = (previous.tail or '') + placeholder
            previous.tail += (reserve.tail or '')
            reserve.getparent().remove(reserve)
            reserve.tail = None

        return trim(''.join(self.element_copy.itertext())).replace('\n', ' ')

    def add_translation(
            self, translation, lang=None, position=None, color=None):
        translation = escape(translation)

        for reserve in self.reserves:
            translation = translation.replace(
                'el_%s' % id(reserve), get_string(reserve))

        translation = '<{0} xmlns="{1}">{2}</{0}>'.format(
            etree.QName(self.element).localname, ns['x'], translation)
        new_element = etree.fromstring(translation)
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
            self.element.getparent().remove(self.element)


class ElementHandler:
    def __init__(self, items, lang=None, position=None, color=None,
                 merge_length=0, merge_divider=None):
        self.elements = [Element(item) for item in items]
        self.merge_length = merge_length
        self.merge_divider = merge_divider
        self.lang = lang
        self.position = position
        self.color = color

        self.original = []
        self.translation = []

    def get_original(self):
        if self.merge_length == 0:
            for element in self.elements:
                content = element.get_content()
                self.original.append((uid(content), content))
            return self.original

        content = ''
        for sid, element in enumerate(self.elements):
            placeholder = ' %s ' % self.merge_divider[0].format('id_%s' % sid)
            text = element.get_content() + placeholder
            if len(content + text) < self.merge_length:
                content += text
                continue
            elif content:
                self.original.append((uid(content), content))
            content = text
        if content:
            self.original.append((uid(content), content))

        return self.original

    def add_translation(self, text):
        self.translation.append(text)

    def varify_translation(self):
        pass

    def apply_translation(self):
        if self.merge_length == 0:
            for element in self.elements:
                element.add_translation(
                    self.translation[self.elements.index(element)],
                    self.lang, self.position, self.color)
            return

        content = ''.join(self.translation)
        pattern = self.merge_divider[1]
        for sid, element in enumerate(self.elements):
            matches = re.search(pattern.format('id_%s' % sid), content)
            if not matches:
                continue
            placeholder = matches.group(0)
            end = content.find(placeholder)
            part = content[:end]
            content = content.replace(part + placeholder, '', 1)
            element.add_translation(
                part.strip(), self.lang, self.position, self.color)
