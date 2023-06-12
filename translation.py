import sys
import time
import json
import random
from types import GeneratorType

from .utils import sep, dummy
from .config import get_config
from .engines import builtin_engines
from .engines import GoogleFreeTranslate
from .engines.custom import CustomTranslate
from .exceptions.engine import IncorrectApiKeyFormat


load_translations()


class Translation:
    def __init__(self, translator):
        self.translator = translator

        self.concurrency_limit = 1
        self.request_attempt = 3
        self.request_interval = 5
        self.need_sleep = False
        self.cancelled = False

        self.fresh = False
        self.progress = dummy
        self.log = dummy
        self.streaming = dummy
        self.callback = dummy
        self.cancel_request = dummy

    def set_concurrency_limit(self, limit):
        self.concurrency_limit = limit

    def set_request_attempt(self, limit):
        self.request_attempt = limit

    def set_request_interval(self, max):
        self.request_interval = max

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

    def is_cancelled(self):
        self.cancelled = self.cancel_request()
        return self.cancelled

    def _translate_text(self, text, count=0, interval=5):
        try:
            return self.translator.translate(text)
        except IncorrectApiKeyFormat:
            raise IncorrectApiKeyFormat(
                self.translator.api_key_error_message())
        except Exception as e:
            """Translation engine service error code documentation:
            * https://cloud.google.com/apis/design/errors
            * https://www.deepl.com/docs-api/api-access/error-handling/
            * https://platform.openai.com/docs/guides/error-codes/api-errors
            * https://ai.youdao.com/DOCSIRMA/html/trans/api/wbfy/index.html
            * https://api.fanyi.baidu.com/doc/21
            """
            if self.is_cancelled():
                return
            if self.translator.need_change_api_key(str(e).lower()):
                if not self.translator.change_api_key():
                    raise Exception(_('No available API key.'))
                self.log(
                    _('API key was Changed due to previous one unavailable.'))
                return self._translate_text(text, count, interval)
            message = _('Failed to retreive data from translate engine API.')
            if count >= self.request_attempt:
                self.log(message)
                raise Exception('{} {}'.format(message, str(e)))
            count += 1
            interval *= count
            self.log(message)
            self.log(_('Will retry in {} seconds.').format(interval))
            time.sleep(interval)
            self.log(
                _('[{}] Retrying {} ... (timeout is {} seconds).')
                .format(time.strftime('%Y-%m-%d %H:%I:%S'), count,
                        int(self.translator.timeout)))
            return self._translate_text(text, count, interval)

    def _prepare_translation(self, paragraph):
        original = paragraph.original
        translation = paragraph.translation

        self.log('-' * 30)
        self.log(_('Original: {}').format(original))

        self.streaming(paragraph)
        self.streaming('')
        self.streaming(_('Translating...'))

        if not translation or self.fresh:
            translation = self._translate_text(original)
            if self.is_cancelled():
                return
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
            paragraph.target_lang = self.translator.get_target_lang()
            paragraph.translation = translation
            paragraph.engine_name = self.translator.name
            self.callback(paragraph)
            self.log(_('Translation: {}').format(translation))
            self.need_sleep = True
        else:
            self.log(_('Translation (Cached): {}').format(translation))
            self.need_sleep = False

    def handle(self, paragraphs=[]):
        total = len(paragraphs)
        self.log(sep)
        self.log(_('Start to translate ebook content'))
        self.log(sep)
        self.log(_('Total items: {}').format(total))
        if total < 1:
            raise Exception(_('There is no content need to translate.'))

        progress = {'count': 0, 'length': 0.0, 'step': 1.0 / total}

        def process_translation(paragraph):
            progress['count'] += 1
            self.progress(
                progress.get('length'), _('Translating: {}/{}')
                .format(progress['count'], total))
            progress['length'] += progress.get('step')
            self._prepare_translation(paragraph)

        if sys.version_info >= (3, 7, 0):
            from .request import AsyncRequest
            async_request = AsyncRequest(paragraphs, self, process_translation)
            async_request.run()
        else:
            for paragraph in paragraphs:
                if self.is_cancelled():
                    return
                process_translation(paragraph)
                if self.need_sleep and progress.get('count') < total:
                    time.sleep(random.randint(0, self.request_interval))

        message = _('Translation completed.')
        if self.cancelled:
            message = _('Translation cancelled.')
        self.log(sep)
        self.log(message)
        self.progress(1, message)
        return paragraphs


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
    engine_config and engine_class.set_config(engine_config)
    return engine_class


def get_translator(engine_class=None):
    config = get_config()
    engine_class = engine_class or get_engine_class()
    translator = engine_class()
    if config.get('proxy_enabled'):
        translator.set_proxy(config.get('proxy_setting'))
    translator.set_merge_enabled(config.get('merge_enabled'))
    translator.set_timeout(config.get('request_timeout'))
    return translator


def get_translation(translator, log=None):
    config = get_config()
    translation = Translation(translator)
    if config.get('log_translation'):
        translation.set_logging(log)
    translation.set_concurrency_limit(config.get('concurrency_limit'))
    translation.set_request_attempt(config.get('request_attempt'))
    translation.set_request_interval(config.get('request_interval'))
    return translation
