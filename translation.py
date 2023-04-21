import time
import random
from types import GeneratorType

from calibre import prepare_string_for_xml as escape

from calibre_plugins.ebook_translator.utils import sep, uid, trim
from calibre_plugins.ebook_translator.config import get_config
from calibre_plugins.ebook_translator.element import ElementHandler


load_translations()


class Translation:
    def __init__(self, translator):
        self.translator = translator

        self.position = None
        self.color = None
        self.request_attempt = 3
        self.request_interval = 5
        self.cache = None
        self.progress = None
        self.log = None

        self.need_sleep = False

    def set_position(self, position):
        self.position = position

    def set_color(self, color):
        self.color = color

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
            return self.translator.translate(text)
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
                      .format(int(self.translator.timeout)))
            return self._translate(text, count, interval)

    def _handle(self, element):
        element_handler = ElementHandler(element)

        original = element_handler.get_content()
        self._log(_('Original: {}').format(original))

        translation = None
        paragraph_uid = uid(original)
        if self.cache and self.cache.exists():
            translation = self.cache.get(paragraph_uid)
        if translation is not None:
            self._log(_('Translation (Cached): {}').format(translation))
            self.need_sleep = False
        else:
            translation = self._translate(original)
            # TODO: translation monitor display streaming text
            if isinstance(translation, GeneratorType):
                translation = ''.join(text for text in translation)
            translation = escape(trim(translation))
            if self.cache:
                self.cache.add(paragraph_uid, translation)
            self._log(_('Translation: {}').format(translation))
            self.need_sleep = True

        element_handler.add_translation(
            translation, self.translator.get_target_code(),
            self.position, self.color)

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
            if self.need_sleep and count < total:
                time.sleep(random.randint(1, self.request_interval))
            count += 1
            process += step
        self._progress(1, _('Translation completed.'))
        self._log(sep, _('Start to convert ebook format:'), sep, sep='\n')


def get_translation(translator):
    translation = Translation(translator)
    translation.set_position(get_config('translation_position'))
    translation.set_color(get_config('translation_color'))
    translation.set_request_attempt(get_config('request_attempt'))
    translation.set_request_interval(get_config('request_interval'))
    return translation
