import re
import sys
import time
import json
from types import GeneratorType

from ..engines import builtin_engines
from ..engines import GoogleFreeTranslate
from ..engines.custom import CustomTranslate

from .utils import sep, trim, dummy
from .config import get_config
from .exception import (
    TranslationFailed, TranslationCanceled, NoAvailableApiKey)


load_translations()


class Glossary:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.glossary = []

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
        except Exception:
            try:
                with open(path, 'rU') as f:
                    content = f.read().strip()
            except Exception:
                pass
        if not content:
            return
        groups = re.split(r'\n{2,}', content.strip(u'\ufeff'))
        for group in filter(trim, groups):
            group = group.split('\n')
            self.glossary.append(
                (group[0], group[0] if len(group) < 2 else group[1]))

    def replace(self, content):
        for wid, words in enumerate(self.glossary):
            replacement = self.placeholder[0].format(format(wid, '06'))
            content = content.replace(words[0], replacement)
        return content

    def restore(self, content):
        for wid, words in enumerate(self.glossary):
            pattern = self.placeholder[1].format(format(wid, '06'))
            # Eliminate the impact of backslashes on substitution.
            content = re.sub(pattern, lambda _: words[1], content)
        return content


class ProgressBar:
    total = 0
    length = 0.0
    step = 0

    _count = 0

    def load(self, total):
        self.total = total
        self.step = 1.0 / total

    @property
    def count(self):
        self._count += 1
        self.length += self.step
        return self._count


class Translation:
    def __init__(self, translator, glossary):
        self.translator = translator
        self.glossary = glossary

        self.fresh = False
        self.batch = False
        self.progress = dummy
        self.log = dummy
        self.streaming = dummy
        self.callback = dummy
        self.cancel_request = dummy

        self.total = 0
        self.progress_bar = ProgressBar()
        self.abort_count = 0

    def set_fresh(self, fresh):
        self.fresh = fresh

    def set_batch(self, batch):
        self.batch = batch

    def set_progress(self, progress):
        self.progress = progress

    def set_logging(self, log):
        self.log = log

    def set_streaming(self, streaming):
        self.streaming = streaming

    def set_callback(self, callback):
        self.callback = callback

    def set_cancel_request(self, cancel_request):
        self.cancel_request = cancel_request

    def need_stop(self):
        # Cancel the request if there are more than max continuous errors.
        return self.translator.max_error_count > 0 and \
            self.abort_count >= self.translator.max_error_count

    def _translate_text(self, text, retry=0, interval=5):
        """Translation engine service error code documentation:
        * https://cloud.google.com/apis/design/errors
        * https://www.deepl.com/docs-api/api-access/error-handling/
        * https://platform.openai.com/docs/guides/error-codes/api-errors
        * https://ai.youdao.com/DOCSIRMA/html/trans/api/wbfy/index.html
        * https://api.fanyi.baidu.com/doc/21
        """
        if self.cancel_request():
            raise TranslationCanceled(_('Translation canceled.'))
        try:
            text = self.glossary.replace(text)
            translation = self.translator.translate(text)
            self.abort_count = 0
            return translation
        except Exception as e:
            if self.cancel_request() or self.need_stop():
                raise TranslationCanceled(_('Translation canceled.'))
            # Try to retrieve an available API key.
            if self.translator.need_change_api_key(str(e).lower()):
                if not self.translator.change_api_key():
                    raise NoAvailableApiKey(_('No available API key.'))
                self.log(
                    _('API key was Changed due to previous one unavailable.'))
            else:
                self.abort_count += 1
                message = _(
                    'Failed to retrieve data from translate engine API.')
                if retry >= self.translator.request_attempt:
                    raise TranslationFailed('{}\n{}'.format(message, str(e)))
                retry += 1
                interval *= retry
                # Logging any errors that occur during translation.
                text = text[:200] + '...' if len(text) > 200 else text
                error_message = '{0}\n{2}\n{1}\n{3}\n{1}\n{4}'.format(
                    sep(), sep('┈'), _('Original: {}').format(text),
                    _('Status: Failed {} times / Sleeping for {} seconds')
                    .format(retry, interval), _('Error: {}').format(str(e)))
                self.log(error_message, True)
                time.sleep(interval)
            return self._translate_text(text, retry, interval)

    def translate_paragraph(self, paragraph):
        if self.cancel_request():
            raise TranslationCanceled(_('Translation canceled.'))
        if paragraph.translation and not self.fresh:
            paragraph.is_cache = True
            return
        self.streaming('')
        self.streaming(_('Translating...'))
        translation = self._translate_text(paragraph.original)
        # Process streaming text
        if isinstance(translation, GeneratorType):
            if self.total == 1:
                # Only for a single translation.
                temp = ''
                clear = True
                for char in translation:
                    if clear:
                        self.streaming('')
                        clear = False
                    self.streaming(char)
                    time.sleep(0.05)
                    temp += char
            else:
                temp = ''.join([char for char in translation])
            translation = temp
        translation = self.glossary.restore(translation)
        paragraph.translation = translation.strip()
        paragraph.engine_name = self.translator.name
        paragraph.target_lang = self.translator.get_target_lang()
        paragraph.seperator = self.translator.separator
        paragraph.is_cache = False

    def process_translation(self, paragraph):
        self.progress(
            self.progress_bar.length, _('Translating: {}/{}').format(
                self.progress_bar.count, self.progress_bar.total))

        self.streaming(paragraph)
        self.callback(paragraph)

        original = paragraph.original.strip()
        translation = paragraph.translation.strip()
        if paragraph.error is None:
            self.log(sep())
            self.log(_('Original: {}').format(original))
            self.log(sep('┈'))
            message = _('Translation: {}')
            if paragraph.is_cache:
                message = _('Translation (Cached): {}')
            self.log(message.format(translation))
        else:
            self.log(sep(), True)
            self.log(_('Original: {}').format(original), True)
            self.log(sep('┈'), True)
            self.log(_('Error: {}').format(paragraph.error), True)
            paragraph.error = None

    def handle(self, paragraphs=[]):
        start_time = time.time()
        char_count = 0
        for paragraph in paragraphs:
            self.total += 1
            char_count += len(paragraph.original)

        self.log(sep())
        self.log(_('Start to translate ebook content'))
        self.log(sep('┈'))
        self.log(_('Total items: {}').format(self.total))
        self.log(_('Character count: {}').format(char_count))
        if self.total < 1:
            raise Exception(_('There is no content need to translate.'))
        self.progress_bar.load(self.total)

        if sys.version_info >= (3, 7, 0):
            from .async_handler import AsyncHandler
            handler = AsyncHandler(
                paragraphs, self.translator.concurrency_limit,
                self.translate_paragraph, self.process_translation,
                self.translator.request_interval)
            handler.handle()
        else:
            from .thread_handler import ThreadHandler
            handler = ThreadHandler(
                paragraphs, self.translator.concurrency_limit,
                self.translate_paragraph, self.process_translation,
                self.translator.request_interval)
            handler.handle()

        self.log(sep())
        if self.batch and self.need_stop():
            raise Exception(_('Translation failed.'))
        consuming = round((time.time() - start_time) / 60, 2)
        self.log('Time consuming: %s minutes' % consuming)
        message = _('Translation completed.')
        self.log(message)
        self.progress(1, message)


def get_engine_class(engine_name=None):
    config = get_config()
    engine_name = engine_name or config.get('translate_engine')
    engines = {engine.name: engine for engine in builtin_engines}
    custom_engines = config.get('custom_engines')
    if engine_name in engines:
        engine_class = engines.get(engine_name)
    elif engine_name in custom_engines:
        engine_class = CustomTranslate
        engine_data = json.loads(custom_engines.get(engine_name))
        engine_class.set_engine_data(engine_data)
    else:
        engine_class = GoogleFreeTranslate
    engine_config = config.get('engine_preferences.%s' % engine_class.name)
    engine_class.set_config(engine_config or {})
    return engine_class


def get_translator(engine_class=None):
    config = get_config()
    engine_class = engine_class or get_engine_class()
    translator = engine_class()
    translator.set_search_paths(config.get('search_paths'))
    if config.get('proxy_enabled'):
        translator.set_proxy(config.get('proxy_setting'))
    translator.set_merge_enabled(config.get('merge_enabled'))
    return translator


def get_translation(translator, log=None):
    config = get_config()
    glossary = Glossary(translator.placeholder)
    if config.get('glossary_enabled'):
        glossary.load_from_file(config.get('glossary_path'))
    translation = Translation(translator, glossary)
    if get_config().get('log_translation'):
        translation.set_logging(log)
    return translation
