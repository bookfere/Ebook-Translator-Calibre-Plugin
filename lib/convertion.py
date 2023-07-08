import os.path
from types import MethodType
from tempfile import gettempdir

from calibre.constants import __version__
from calibre.ebooks.conversion.plumber import Plumber

from .. import EbookTranslator

from .utils import log, sep, uid
from .cache import get_cache, TranslationCache
from .element import get_ebook_elements, get_element_handler, Extraction
from .translation import get_translator, get_translation


load_translations()


def ebook_pages(input_path):
    pages = []

    output_path = os.path.join(gettempdir(), 'temp.epub')
    plumber = Plumber(input_path, output_path, log=log)

    def convert(self, oeb, output_path, input_plugin, opts, log):
        pages.extend(oeb.manifest.items)
    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()

    return pages


def convert_book(ebook_title, input_path, output_path, source_lang,
                 target_lang, cache_only, notification):
    """ The following parameters need attention:
    :cache_only: Only use the translation which exists in the cache.
    :notification: It is automatically added by arbitrary_n.
    """
    translator = get_translator()
    translator.set_source_lang(source_lang)
    translator.set_target_lang(target_lang)

    element_handler = get_element_handler()
    element_handler.set_translation_lang(
        translator.get_iso639_target_code(target_lang))

    merge_length = str(element_handler.get_merge_length())
    identity = uid(
        input_path + translator.name + target_lang
        + merge_length + TranslationCache.__version__ + Extraction.__version__)
    cache = get_cache(identity)
    cache.set_cache_only(cache_only)
    cache.set_info('title', ebook_title)
    cache.set_info('engine_name', translator.name)
    cache.set_info('target_lang', target_lang)
    cache.set_info('merge_length', merge_length)
    cache.set_info('plugin_version', EbookTranslator.__version__)
    cache.set_info('calibre_version', __version__)

    translation = get_translation(
        translator, lambda text, error=False: log.info(text))
    translation.set_callback(cache.update_paragraph)

    info = '{0}\n| Diagnosis Information\n{0}'.format(sep())
    info += '\n| Calibre Version: %s\n' % __version__
    info += '| Plugin Version: %s\n' % EbookTranslator.__version__
    info += '| Translate Engine: %s\n' % translator.name
    info += '| Source Language: %s\n' % source_lang
    info += '| Target Language: %s\n' % target_lang
    info += '| Cache Enabled: %s\n' % cache.is_persistence()
    info += '| Merging Length: %s\n' % element_handler.merge_length
    info += '| Concurrent requests: %s\n' % translator.concurrency_limit
    info += '| Request Interval: %s\n' % translator.request_interval
    info += '| Request Attempt: %s\n' % translator.request_attempt
    info += '| Request Timeout: %s\n' % translator.request_timeout
    info += '| Input Path: %s\n' % input_path
    info += '| Output Path: %s' % output_path

    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)
    _convert = plumber.output_plugin.convert

    def convert(self, oeb, output_path, input_plugin, opts, log):
        log.info('Translating ebook content ... (this will take a while)')
        log.info(info)
        translation.set_progress(self.report_progress)

        elements = get_ebook_elements(
            oeb.manifest.items, translator.placeholder)
        original_group = element_handler.prepare_original(elements)
        cache.save(original_group)

        paragraphs = cache.all_paragraphs()
        translation.handle(paragraphs)
        element_handler.add_translations(paragraphs)

        log(sep())
        log(_('Start to convert ebook format:'))
        log(sep())
        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()
    cache.done()