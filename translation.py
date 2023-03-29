import time
import random

from lxml import etree
from calibre import prepare_string_for_xml as escape

from calibre_plugins.ebook_translator.utils import ns, sep, uid, trim


load_translations()


class Translation:
    def __init__(self, translator):
        self.translator = translator

        self.cache = None
        self.progress = None
        self.log = None

        self.need_sleep = False
        self.request_attempt = 3
        self.request_interval = 5

    def set_request_attempt(self, limit):
        self.request_attempt = limit

    def set_request_interval(self, max):
        self.request_interval = max

    def set_cache(self, cache):
        self.cache = cache

    def set_progress(self, progress):
        self.progress = progress

    def set_log(self, log):
        self.log = log

    def _progress(self, *args):
        if self.progress:
            self.progress(*args)

    def _log(self, *args, **kwargs):
        if self.log:
            self.log.info(*args, **kwargs)

    def _translate(self, text, count=0, interval=5):
        try:
            return escape(trim(self.translator.translate(text)))
        except Exception as e:
            message = _('Failed to retreive data from translate engine API.')
            if count >= self.request_attempt:
                raise Exception('{} {}'.format(message, str(e)))
            count += 1
            interval *= count
            self._log(message)
            self._log(_('Will retry in {} seconds.').format(interval))
            time.sleep(interval)
            self._log(_('Retrying ... (timeout is {} seconds).')
                      .format(round(self.translator.timeout)))
            return self._translate(text, count, interval)

    def _handle(self, element):
        translation = None
        element_copy = self._get_element_copy(element)
        reserves = element_copy.findall('.//x:img', namespaces=ns)
        for reserve in reserves:
            # TODO: handle nested img element
            if reserve.getparent() != element_copy:
                reserves.remove(reserve)
                continue
            placeholder = '{id_%s}' % id(reserve)
            element_copy.text = ((element_copy.text or '') + placeholder
                                 + (reserve.tail or ''))
            reserve.tail = None
            reserve.getparent().remove(reserve)

        original = trim(''.join(element_copy.itertext()))
        self._log(_('Original: {}').format(original))

        paragraph_uid = uid(original)
        if self.cache and self.cache.exists():
            translation = self.cache.get(paragraph_uid)

        if translation is not None:
            self._log(_('Translation (Cached): {}').format(translation))
            self.need_sleep = False
        else:
            translation = self._translate(original)
            if self.cache:
                self.cache.add(paragraph_uid, translation)
            self._log(_('Translation: {}').format(translation))
            self.need_sleep = True

        if reserves:
            translation = translation.format(**dict([
                ('id_%s' % id(reserve), self._get_element_string(reserve))
                for reserve in reserves]))

        translation = '<{0} xmlns="{1}">{2}</{0}>'.format(
                      etree.QName(element).localname, ns['x'], translation,)
        new_element = etree.fromstring(translation)
        new_element.set('class', element.get('class'))
        element.tail = None  # Make sure it has no tail
        element.addnext(new_element)

    def _get_element_copy(self, element):
        return etree.fromstring(self._get_element_string(element))

    def _get_element_string(self, element):
        return trim(etree.tostring(element, encoding='utf-8').decode())

    def handle(self, elements):
        total = len(elements)
        if total < 1:
            raise Exception(_('There is no content need to translate.'))
        self._log(sep, _('Start to translate ebook content:'), sep, sep='\n')
        self._log(_('Total items: {}').format(total))
        process, step = 0.0, 1.0 / total
        count = 0
        for element in elements:
            self._log('-' * 30)
            self._progress(process, _('Translating: {}/{}')
                           .format(count, total))
            self._handle(element)
            if self.translator.need_sleep() and self.need_sleep:
                time.sleep(random.randint(0, self.request_interval))
            count += 1
            process += step
        self._progress(1, _('Translation completed.'))
        self._log(sep, _('Start to convert ebook format:'), sep, sep='\n')
        # self.cache.destroy()
