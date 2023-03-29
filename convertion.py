import hashlib
from types import MethodType

from calibre.utils.logging import Log
from calibre.ebooks.conversion.plumber import Plumber
from calibre_plugins.ebook_translator.config import get_config
from calibre_plugins.ebook_translator.utils import ns, uid, trim
from calibre_plugins.ebook_translator.cache import TranslationCache
from calibre_plugins.ebook_translator.translation import Translation
from calibre_plugins.ebook_translator.translator import TranslatorBuilder


load_translations()


def get_translator(source_lang, target_lang):
    engine = get_config('translate_engine')
    api_key = get_config('api_key.%s' % engine)
    builder = TranslatorBuilder(source_lang, target_lang, engine, api_key)
    translator = builder.build()
    if get_config('proxy_enabled'):
        translator.set_proxy(get_config('proxy_setting'))
    return translator


def get_translation(translator):
    translation = Translation(translator)
    translation.set_request_attempt(get_config('request_attempt'))
    translation.set_request_interval(get_config('request_interval'))
    return translation


def convert_book(input_path, output_path, source_lang, target_lang,
                 notification):
    """parameter notification is automatically added by arbitrary_n."""
    log = Log()
    translator = get_translator(source_lang, target_lang)
    translation = get_translation(translator)

    if get_config('cache_enabled'):
        cache = TranslationCache(uid(
            translator.get_name(), input_path, source_lang, target_lang))
        translation.set_cache(cache)

    if get_config('log_translation'):
        translation.set_log(log)

    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)
    _convert = plumber.output_plugin.convert

    def convert(self, oeb, output_path, input_plugin, opts, log):
        elements = []
        tags = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
        pattern = './/*[self::x:p%s]' % \
                  ''.join([' or self::x:%s' % tag for tag in tags])
        for item in oeb.manifest.items:
            if 'html' in item.media_type:
                for element in item.data.xpath(pattern, namespaces=ns):
                    if trim(''.join(element.itertext())):
                        elements.append(element)

        log.info('translating ebook content ... (this will take a while)')
        translation.set_progress(self.report_progress)
        translation.handle(elements)

        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()
