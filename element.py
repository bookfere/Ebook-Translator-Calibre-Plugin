import re
import copy

from lxml import etree
from calibre import prepare_string_for_xml as escape
from calibre_plugins.ebook_translator.utils import ns, uid, trim


def get_string(element, remove_ns=False):
    string = trim(etree.tostring(
        element, encoding='utf-8', with_tail=False).decode('utf-8'))
    return string if not remove_ns else re.sub(r'\sxmlns(.*?"){2}', '', string)


def get_name(element):
    return etree.QName(element).localname


class Element:
    def __init__(self, element, placeholder):
        self.element = element
        self.placeholder = placeholder
        self.element_copy = copy.deepcopy(element)
        self.reserves = []

    def get_elements(self, tags):
        xpath = './/*[%s]' % ' or '.join(['self::x:%s' % tag for tag in tags])
        return self.element_copy.xpath(xpath, namespaces=ns)

    def get_content(self):
        for noise in self.get_elements(('rt', 'sup')):
            noise.getparent().remove(noise)

        self.reserves = self.get_elements(('img', 'code'))
        for rid, reserve in enumerate(self.reserves):
            placeholder = self.placeholder[0].format(rid + 10000)
            previous, parent = reserve.getprevious(), reserve.getparent()
            if previous is not None:
                previous.tail = (previous.tail or '') + placeholder
                previous.tail += (reserve.tail or '')
            else:
                parent.text = (parent.text or '') + placeholder
                parent.text += (reserve.tail or '')
            parent.remove(reserve)
        return re.sub(r'\s+', ' ', trim(''.join(self.element_copy.itertext())))

    def add_translation(
            self, translation, position=None, lang=None, color=None):
        translation = escape(translation)
        for rid, reserve in enumerate(self.reserves):
            translation = re.sub(
                # Escape the markups to replace escaped markups.
                escape(self.placeholder[1].format(rid + 10000)),
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
            self.element.getparent().remove(self.element)
        return new_element


class ElementHandler:
    def __init__(self, items, placeholder, merge_length=0, lang=None,
                 position=None, color=None):
        self.elements = [Element(item, placeholder) for item in items]
        self.lang = lang
        self.position = position
        self.color = color
        self.merge_length = merge_length
        self.placeholder = placeholder

        self.original = []
        self.translation = []

    def get_original(self):
        if self.merge_length == 0:
            for element in self.elements:
                content = element.get_content()
                self.original.append((uid(content), content))
            return self.original

        content = ''
        for pid, element in enumerate(self.elements):
            placeholder = ' %s ' % self.placeholder[0].format(pid)
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

    def apply_translation(self):
        if self.merge_length == 0:
            for element in self.elements:
                element.add_translation(
                    self.translation[self.elements.index(element)],
                    self.position, self.lang, self.color)
            return

        content = ''.join(self.translation)
        for pid, element in enumerate(self.elements):
            matches = re.search(self.placeholder[1].format(pid), content)
            if not matches:
                continue
            placeholder = matches.group(0)
            end = content.find(placeholder)
            part = content[:end]
            content = content.replace(part + placeholder, '', 1)
            element.add_translation(
                part.strip(), self.position, self.lang, self.color)
