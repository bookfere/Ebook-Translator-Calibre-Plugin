import os
import time
import random
from types import GeneratorType

from calibre_plugins.ebook_translator.utils import sep, trim
from calibre_plugins.ebook_translator.config import get_config
from calibre_plugins.ebook_translator.element import ElementHandler


load_translations()


class Translation:
    def __init__(self, translator):
        self.translator = translator

        self.glossary = Glossary()
        self.merge_length = 0
        self.translation_position = None
        self.translation_color = None
        self.request_attempt = 3
        self.request_interval = 5
        self.cache = None
        self.progress = None
        self.log = None

        self.need_sleep = False

    def set_merge_length(self, length):
        self.merge_length = length

    def set_translation_position(self, position):
        self.translation_position = position

    def set_translation_color(self, color):
        self.translation_color = color

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

    def _translate_text(self, text, count=0, interval=5):
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
            self._log(_('[{}] Retrying {} ... (timeout is {} seconds).')
                      .format(time.strftime('%Y-%m-%d %H:%I:%S'), count,
                              int(self.translator.timeout)))
            return self._translate_text(text, count, interval)

    def _get_translation(self, identity, original):
        self._log(_('Original: {}').format(original))
        translation = None

        if self.cache and self.cache.exists():
            translation = self.cache.get(identity)
        if translation is not None:
            self._log(_('Translation (Cached): {}').format(translation))
            self.need_sleep = False
        else:
            original = self.glossary.replace(original)
            translation = self._translate_text(original)
            # TODO: translation monitor display streaming text
            if isinstance(translation, GeneratorType):
                translation = ''.join(text for text in translation)
                translation = translation.replace('\n', ' ')
            translation = self.glossary.restore(trim(translation))
            self.cache and self.cache.add(identity, translation)
            self._log(_('Translation: {}').format(translation))
            self.need_sleep = True

        return translation

    def handle(self, elements):
        element_handler = ElementHandler(
            elements, self.translator.placeholder, self.merge_length,
            self.translator.get_target_code(), self.translation_position,
            self.translation_color)

        original_group = element_handler.get_original()
        total = len(original_group)
        if total < 1:
            raise Exception(_('There is no content need to translate.'))
        self._log(sep, _('Start to translate ebook content:'), sep, sep='\n')
        self._log(_('Total items: {}').format(total))
        process, step = 0.0, 1.0 / total

        count = 0
        for identity, original in original_group:
            self._log('-' * 30)
            count += 1
            self._progress(process, _('Translating: {}/{}')
                           .format(count, total))
            element_handler.add_translation(
                self._get_translation(identity, original))
            process += step
            if self.need_sleep and count < total:
                time.sleep(random.randint(1, self.request_interval))

        element_handler.apply_translation()

        self._progress(1, _('Translation completed.'))
        self._log(sep, _('Start to convert ebook format:'), sep, sep='\n')


class Glossary:
    def __init__(self):
        self.glossary = []

    def load(self, path):
        try:
            with open(path) as f:
                content = f.read().strip()
        except Exception as e:
            raise Exception(_('Can not open glossary file: {}').format(str(e)))

        if not content:
            return

        for group in content.split(os.linesep*2):
            group = group.strip().split(os.linesep)
            if len(group) > 2:
                continue
            if len(group) == 1:
                group.append(group[0])
            self.glossary.append(group)

    def replace(self, text):
        for word in self.glossary:
            text = text.replace(word[0], 'id_%d' % id(word))
        return text

    def restore(self, text):
        for word in self.glossary:
            text = text.replace('id_%d' % id(word), word[1])
        return text


def get_translation(translator):
    translation = Translation(translator)
    if get_config('glossary_enabled'):
        translation.glossary.load(get_config('glossary_path'))
    if get_config('merge_enabled'):
        translation.set_merge_length(get_config('merge_length'))
    translation.set_translation_position(get_config('translation_position'))
    translation.set_translation_color(get_config('translation_color'))
    translation.set_request_attempt(get_config('request_attempt'))
    translation.set_request_interval(get_config('request_interval'))
    return translation
