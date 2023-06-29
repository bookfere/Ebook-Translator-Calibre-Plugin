import sys
import time
import json
import traceback
from types import GeneratorType

from .utils import sep, dummy
from .config import get_config
from .engines import builtin_engines
from .engines import GoogleFreeTranslate
from .engines.custom import CustomTranslate
from .exceptions import (
    BadApiKeyFormat, NoAvailableApiKey, TranslationCanceled, TranslationFailed)


load_translations()


class ProgressBar:
    total = 0
    count = 0
    length = 0.0
    step = 0

    def __init__(self, total):
        self.total = total
        self.step = 1.0 / total

    def increase_count(self):
        self.count += 1

    def increase_length(self):
        self.length += self.step


class Translation:
    def __init__(self, translator):
        self.translator = translator
        self.abort_count = 0

        self.fresh = False
        self.progress = dummy
        self.log = dummy
        self.streaming = dummy
        self.callback = dummy
        self.cancel_request = dummy

    def set_fresh(self, fresh):
        self.fresh = fresh

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
            time.sleep(self.translator.request_interval)
            translation = self.translator.translate(text)
            self.abort_count = 0
            return translation
        except BadApiKeyFormat:
            raise TranslationCanceled(_('Translation canceled.'))
        except Exception as e:
            self.abort_count += 1
            if self.cancel_request() or self.abort_count >= 10:
                raise TranslationCanceled(_('Translation canceled.'))
            if self.translator.need_change_api_key(str(e).lower()):
                if not self.translator.change_api_key():
                    raise NoAvailableApiKey(_('No available API key.'))
                self.log(
                    _('API key was Changed due to previous one unavailable.'))
                return self._translate_text(text, retry, interval)
            message = _('Failed to retrieve data from translate engine API.')
            if retry >= self.translator.request_attempt:
                raise TranslationFailed('{}\n{}'.format(
                    message, traceback.format_exc()))
            # TODO: Display how many jobs are retrying.
            retry += 1
            interval *= retry
            time.sleep(interval)
            return self._translate_text(text, retry, interval)

    def translate_paragraph(self, paragraph):
        if paragraph.translation and not self.fresh:
            return
        self.streaming(paragraph)
        self.streaming('')
        self.streaming(_('Translating...'))
        translation = self._translate_text(paragraph.original)
        # Process streaming text
        if isinstance(translation, GeneratorType):
            temp = ''
            clear = True
            for char in translation:
                if clear:
                    self.streaming('')
                    clear = False
                self.streaming(char)
                time.sleep(0.05)
                temp += char
            translation = temp.replace('\n', ' ')
        paragraph.translation = translation
        paragraph.engine_name = self.translator.name
        paragraph.target_lang = self.translator.get_target_lang()

        self.callback(paragraph)

    def handle(self, paragraphs=[]):
        start_time = time.time()
        total = 0
        char_count = 0
        for paragraph in paragraphs:
            total += 1
            char_count += len(paragraph.original)

        self.log(sep())
        self.log(_('Start to translate ebook content'))
        self.log(sep())
        self.log(_('Total items: {}').format(total))
        self.log(_('Character count: {}'.format(char_count)))
        if total < 1:
            raise Exception(_('There is no content need to translate.'))

        progress_bar = ProgressBar(total)

        def process_translation(paragraph):
            progress_bar.increase_count()
            self.progress(progress_bar.length, _('Translating: {}/{}')
                          .format(progress_bar.count, progress_bar.total))
            progress_bar.increase_length()

            if paragraph.error is None:
                self.log(sep('-'))
                self.log(_('Original: {}').format(paragraph.original))
                self.log(_('Translation: {}').format(paragraph.translation))
            else:
                self.log(sep('-'), True)
                self.log(_('Original: {}').format(paragraph.original), True)
                self.log(_('Error: {}').format(paragraph.error), True)
                paragraph.error = None

        if sys.version_info >= (3, 7, 0):
            from .concurrency.async_handler import AsyncHandler
            handler = AsyncHandler(
                self.translator.concurrency_limit, self.translate_paragraph,
                process_translation, paragraphs)
            handler.handle()
        else:
            from .concurrency.thread_handler import ThreadHandler
            handler = ThreadHandler(
                self.translator.concurrency_limit, self.translate_paragraph,
                process_translation, paragraphs)
            handler.handle()

        message = _('Translation completed.')
        if self.cancel_request():
            message = _('Translation canceled.')
        self.log(sep())
        consuming = round((time.time() - start_time) / 60, 2)
        self.log('Time consuming: %s minutes' % consuming)
        # self.log('Failed translation: %s' % failed_count)
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
    if config.get('proxy_enabled'):
        translator.set_proxy(config.get('proxy_setting'))
    translator.set_merge_enabled(config.get('merge_enabled'))
    return translator


def get_translation(translator, log=None):
    translation = Translation(translator)
    if get_config().get('log_translation'):
        translation.set_logging(log)
    return translation
