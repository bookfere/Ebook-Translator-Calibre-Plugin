import copy

from lxml import etree
from calibre_plugins.ebook_translator.utils import ns, trim


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
            # TODO: handle nested img element
            if reserve.getparent() != self.element_copy:
                self.reserves.remove(reserve)
                continue
            placeholder = 'id_%s' % id(reserve)
            self.element_copy.text = ((self.element_copy.text or '')
                                      + placeholder + (reserve.tail or ''))
            reserve.tail = None
            reserve.getparent().remove(reserve)

        return trim(''.join(self.element_copy.itertext())).replace('\n', ' ')

    def add_translation(
            self, translation, lang=None, position=None, color=None):
        if self.reserves:
            for reserve in self.reserves:
                translation = translation.replace(
                    'id_%s' % id(reserve), self._get_string(reserve))

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

    @staticmethod
    def _get_string(element):
        return trim(etree.tostring(element, encoding='utf-8').decode('utf-8'))


class ElementHandler:
    def __init__(self, items, merge_length=0, lang=None, position=None,
                 color=None):
        self.elements = [Element(item) for item in items]
        self.merge_length = merge_length
        self.lang = lang
        self.position = position
        self.color = color

        self.original = []
        self.translation = []

    def get_original(self):
        if self.merge_length == 0:
            for element in self.elements:
                self.original.append(element.get_content())
            return self.original

        content = ''
        for element in self.elements:
            uid = ' <id_%s> ' % id(element)
            text = element.get_content() + uid
            print(text)
            if len((content + text).encode()) < self.merge_length:
                content += text
                continue
            elif content:
                self.original.append(content)
            content = text
        if content:
            self.original.append(content)
        return self.original

    def add_translation(self, text):
        self.translation.append(text)

    def apply_translation(self):
        if self.merge_length == 0:
            for element in self.elements:
                element.add_translation(
                    self.translation[self.elements.index(element)],
                    self.lang, self.position, self.color)
            return

        content = ''.join(self.translation)
        for element in self.elements:
            uid = 'id_%s' % id(element)
            end = content.find(uid)
            part = content[:end]
            content = content.replace(part + uid, '')

            element.add_translation(
                part.strip(' \n\t<>'), self.lang, self.position, self.color)
