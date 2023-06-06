import os.path
from types import MethodType
from tempfile import gettempdir

from calibre.constants import __version__
from calibre.ebooks.conversion.plumber import Plumber

from . import EbookTranslator
from .utils import log, uid, sep
from .cache import get_cache
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


def convert_book(input_path, output_path, source_lang, target_lang,
                 cache_only, notification):
    """ The following parameters need attention:"
    :cache_only: Only use the translation which exists in the cache.
    :notification: It is automatically added by arbitrary_n.
    """
    translator = get_translator()
    translator.set_source_lang(source_lang)
    translator.set_target_lang(target_lang)

    element_handler = get_element_handler(translator.get_target_lang_code())

    cache = get_cache(uid(
        input_path, translator.name, target_lang, Extraction.__version__,
        str(element_handler.get_merge_length())))
    cache.set_cache_only(cache_only)

    translation = get_translation(translator)
    translation.set_logging(log.info)
    translation.set_callback(
        lambda paragraph: cache.update_paragraph(paragraph))

    info = '=' * 30
    info += '\n| Diagnosis Information\n'
    info += '=' * 30
    info += '\n| Calibre Version: %s\n' % __version__
    info += '| Plugin Version: %s\n' % EbookTranslator.__version__
    info += '| Translate Engine: %s\n' % translator.name
    info += '| Source Language: %s\n' % source_lang
    info += '| Target Language: %s\n' % target_lang
    info += '| Cache Enabled: %s\n' % cache.is_persistence()
    info += '| Merge Length: %s\n' % element_handler.merge_length
    info += '| Concurrency: %s\n' % translation.concurrency_limit
    info += '| Attempt Limit: %s\n' % translation.request_attempt
    info += '| Max Interval: %s\n' % translation.request_interval
    info += '| Timeout: %s\n' % translator.timeout
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
        translations = translation.handle(paragraphs)
        element_handler.add_translations(translations)

        log('\n'.join((sep, _('Start to convert ebook format:'), sep)))
        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()

    cache.done()
