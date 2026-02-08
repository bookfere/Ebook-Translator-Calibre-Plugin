import re
import time
import json
from types import GeneratorType

from calibre.utils.localization import _  # type: ignore

from ..engines import builtin_engines
from ..engines import GoogleFreeTranslateNew
from ..engines.base import Base
from ..engines.custom import CustomTranslate

from .utils import log, sep, trim, dummy, traceback_error
from .config import get_config
from .exception import TranslationFailed, TranslationCanceled
from .handler import Handler


load_translations()  # type: ignore


class Glossary:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.glossary = []

    def load_from_file(self, path):
        content = None
        try:
            with open(path, 'r', newline=None) as f:
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

    def translate_text(self, row, text, retry=0, interval=0):
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
            translation = self.translator.translate(text)
            self.abort_count = 0
            return translation
        except Exception as e:
            if self.cancel_request() or self.need_stop():
                raise TranslationCanceled(_('Translation canceled.'))
            self.abort_count += 1
            message = _('Failed to retrieve data from translate engine API.')
            if retry >= self.translator.request_attempt:
                raise TranslationFailed('{}\n{}'.format(message, str(e)))
            retry += 1
            interval += 5
            # Logging any errors that occur during translation.
            logged_text = text[:200] + '...' if len(text) > 200 else text
            error_messages = [
                sep(), _('Original: {}').format(logged_text), sep('┈'),
                _('Status: Failed {} times / Sleeping for {} seconds')
                .format(retry, interval), sep('┈'), _('Error: {}')
                .format(traceback_error())]
            if row >= 0:
                error_messages.insert(1, _('Row: {}').format(row))
            self.log('\n'.join(error_messages), True)
            if self.translator.match_error(str(e)):
                raise TranslationCanceled(_('Translation canceled.'))
            time.sleep(interval)
            return self.translate_text(row, text, retry, interval)

    def translate_paragraph(self, paragraph):
        if self.cancel_request():
            raise TranslationCanceled(_('Translation canceled.'))
        if paragraph.translation and not self.fresh:
            paragraph.is_cache = True
            return
        self.streaming('')
        self.streaming(_('Translating...'))
        text = self.glossary.replace(paragraph.original)
        translation = self.translate_text(paragraph.row, text)
        # Process streaming text
        if isinstance(translation, GeneratorType):
            if self.total == 1:
                # Only for a single translation.
                temp = ''
                clear = True
                for char in translation:
                    # Check for cancellation during streaming
                    if self.cancel_request():
                        raise TranslationCanceled(_('Translation canceled.'))
                    if clear:
                        self.streaming('')
                        clear = False
                    self.streaming(char)
                    time.sleep(0.05)
                    temp += char
            else:
                # For batch mode, still check cancellation periodically
                temp_chars = []
                for char in translation:
                    if self.cancel_request():
                        raise TranslationCanceled(_('Translation canceled.'))
                    temp_chars.append(char)
                temp = ''.join(temp_chars)
            translation = temp
        translation = self.glossary.restore(translation)
        paragraph.translation = translation.strip()
        # Apply aligment checking and processing.
        if self.translator.merge_enabled:
            paragraph.do_aligment(self.translator.separator)
        paragraph.engine_name = self.translator.name
        paragraph.target_lang = self.translator.get_target_lang()
        paragraph.is_cache = False

    def process_translation(self, paragraph):
        self.progress(
            self.progress_bar.length, _('Translating: {}/{}').format(
                self.progress_bar.count, self.progress_bar.total))

        self.streaming(paragraph)
        self.callback(paragraph)

        row = paragraph.row
        original = paragraph.original.strip()
        if paragraph.error is None:
            # Only log verbose content if log_content setting is enabled
            from .config import get_config
            if get_config().get('log_content', True):
                self.log(sep())
                if row >= 0:
                    self.log(_('Row: {}').format(row))
                self.log(_('Original: {}').format(original))
                self.log(sep('┈'))
                message = _('Translation: {}')
                if paragraph.is_cache:
                    message = _('Translation (Cached): {}')
                self.log(message.format(paragraph.translation.strip()))

    def handle(self, paragraphs=[]):
        start_time = time.time()
        char_count = 0
        for paragraph in paragraphs:
            self.total += 1
            char_count += len(paragraph.original)

        # Set up prompt caching if enabled
        # Collect full book context for caching (Claude only)
        if hasattr(self.translator, 'enable_prompt_caching') and self.translator.enable_prompt_caching:
            full_context = '\n\n'.join([p.original for p in paragraphs])
            self.translator.full_book_context = full_context
            self.log(sep())
            self.log(_('Prompt caching enabled - using full book context'))
            self.log(_('Context size: {} characters').format(len(full_context)))

        self.log(sep())
        self.log(_('Start to translate ebook content'))
        self.log(sep('┈'))
        self.log(_('Item count: {}').format(self.total))
        self.log(_('Character count: {}').format(char_count))

        if self.total < 1:
            raise Exception(_('There is no content need to translate.'))
        self.progress_bar.load(self.total)

        handler = Handler(
            paragraphs, self.translator.concurrency_limit,
            self.translate_paragraph, self.process_translation,
            self.translator.request_interval)
        handler.handle()

        self.log(sep())
        if self.batch and self.need_stop():
            raise Exception(_('Translation failed.'))
        consuming = round((time.time() - start_time) / 60, 2)
        self.log(_('Time consuming: {} minutes').format(consuming))
        self.log(_('Translation completed.'))
        self.progress(1, _('Translation completed.'))


def get_engine_class(engine_name=None):
    config = get_config()
    engine_name = engine_name or config.get('translate_engine')
    engines: dict[str, type[Base]] = {
        engine.name: engine for engine in builtin_engines
        if engine.name is not None}
    custom_engines = config.get('custom_engines') or {}
    if engine_name in engines:
        engine_class = engines[engine_name]
    elif engine_name in custom_engines:
        engine_class = CustomTranslate
        engine_data = json.loads(custom_engines[engine_name])
        engine_class.set_engine_data(engine_data)
    else:
        engine_class = GoogleFreeTranslateNew
    engine_preferences = config.get('engine_preferences') or {}
    engine_class.set_config(engine_preferences.get(engine_class.name) or {})
    return engine_class


def get_translator(engine_class=None):
    config = get_config()
    engine_class = engine_class or get_engine_class()
    translator = engine_class()
    translator.set_search_paths(config.get('search_paths'))
    if config.get('proxy_enabled'):
        proxy_type: str | None = config.get('proxy_type')
        proxy_setting: dict[str, list] | None = config.get('proxy_setting')
        if proxy_type is not None and proxy_setting is not None:
            # Compatible with old proxy settings stored as a list.
            if isinstance(proxy_setting, list):
                proxy_setting = {'http': proxy_setting}
            host, port = proxy_setting.get(proxy_type) or ['', '']
            translator.set_proxy(proxy_type, host, port)
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
