import os
import os.path
from types import MethodType
from tempfile import gettempdir

from calibre.gui2 import Dispatcher
from calibre.constants import DEBUG, __version__
from calibre.ebooks.conversion.plumber import Plumber
from calibre.ptempfile import PersistentTemporaryFile
from calibre.ebooks.metadata.meta import get_metadata, set_metadata

from .. import EbookTranslator

from .config import get_config
from .utils import log, sep, uid, open_path
from .cache import get_cache, TranslationCache
from .element import (
    Extraction, get_element_handler, get_srt_elements, get_toc_elements,
    get_page_elements, get_metadata_elements)
from .translation import get_translator, get_translation


load_translations()


def extract_item(input_path, input_format):
    extractors = {'srt': extract_srt}
    extractor = extractors.get(input_format) or extract_book
    return extractor(input_path)


def extract_book(input_path):
    elements = []

    output_path = os.path.join(gettempdir(), 'temp.epub')
    plumber = Plumber(input_path, output_path, log=log)

    def convert(self, oeb, output_path, input_plugin, opts, log):
        elements.extend(get_metadata_elements(oeb.metadata))
        elements.extend(get_toc_elements(oeb.toc.nodes, []))
        elements.extend(get_page_elements(oeb.manifest.items))
    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()

    return elements


def extract_srt(input_path):
    return get_srt_elements(input_path)


def convert_item(ebook_title, input_path, output_path, source_lang,
                 target_lang, cache_only, is_batch, format, notification):
    """The following parameters need attention:
    :cache_only: Only use the translation which exists in the cache.
    :notification: It is automatically added by arbitrary_n.
    """
    translator = get_translator()
    translator.set_source_lang(source_lang)
    translator.set_target_lang(target_lang)

    element_handler = get_element_handler(
        translator.placeholder, translator.separator)
    element_handler.set_translation_lang(
        translator.get_iso639_target_code(target_lang))

    merge_length = str(element_handler.get_merge_length())
    cache_id = uid(
        input_path + translator.name + target_lang + merge_length
        + TranslationCache.__version__ + Extraction.__version__)
    cache = get_cache(cache_id)
    cache.set_cache_only(cache_only)
    cache.set_info('title', ebook_title)
    cache.set_info('engine_name', translator.name)
    cache.set_info('target_lang', target_lang)
    cache.set_info('merge_length', merge_length)
    cache.set_info('plugin_version', EbookTranslator.__version__)
    cache.set_info('calibre_version', __version__)

    translation = get_translation(
        translator, lambda text, error=False: log.info(text))
    translation.set_batch(is_batch)
    translation.set_callback(cache.update_paragraph)

    debug_info = '{0}\n| Diagnosis Information\n{0}'.format(sep())
    debug_info += '\n| Calibre Version: %s\n' % __version__
    debug_info += '| Plugin Version: %s\n' % EbookTranslator.__version__
    debug_info += '| Translation Engine: %s\n' % translator.name
    debug_info += '| Source Language: %s\n' % source_lang
    debug_info += '| Target Language: %s\n' % target_lang
    debug_info += '| Cache Enabled: %s\n' % cache.is_persistence()
    debug_info += '| Merging Length: %s\n' % element_handler.merge_length
    debug_info += '| Concurrent requests: %s\n' % translator.concurrency_limit
    debug_info += '| Request Interval: %s\n' % translator.request_interval
    debug_info += '| Request Attempt: %s\n' % translator.request_attempt
    debug_info += '| Request Timeout: %s\n' % translator.request_timeout
    debug_info += '| Input Path: %s\n' % input_path
    debug_info += '| Output Path: %s' % output_path

    convertors = {'srt': convert_srt}
    convertor = convertors.get(format) or convert_book
    convertor(input_path, output_path, translation, element_handler, cache,
              debug_info, notification)

    cache.done()


def convert_book(input_path, output_path, translation, element_handler, cache,
                 debug_info, notification):
    """Process ebooks that Calibre supported."""
    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)
    _convert = plumber.output_plugin.convert
    elements = []

    def convert(self, oeb, output_path, input_plugin, opts, log):
        log.info('Translating ebook content ... (this will take a while)')
        log.info(debug_info)
        translation.set_progress(self.report_progress)

        elements.extend(get_metadata_elements(oeb.metadata))
        # The number of elements may vary with format conversion.
        elements.extend(get_toc_elements(oeb.toc.nodes, []))
        elements.extend(get_page_elements(oeb.manifest.items))
        original_group = element_handler.prepare_original(elements)
        cache.save(original_group)

        paragraphs = cache.all_paragraphs()
        translation.handle(paragraphs)
        element_handler.add_translations(paragraphs)

        log(sep())
        log(_('Start to convert ebook format ...'))
        log(sep())
        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()


def convert_srt(input_path, output_path, translation, element_handler, cache,
                debug_info, notification):
    log.info('Translating subtitles content ... (this will take a while)')
    log.info(debug_info)

    elements = get_srt_elements(input_path)
    original_group = element_handler.prepare_original(elements)
    cache.save(original_group)

    paragraphs = cache.all_paragraphs()
    translation.set_progress(notification)
    translation.handle(paragraphs)
    element_handler.add_translations(paragraphs)

    log(sep())
    log(_('Starting to output subtitles file ...'))
    log(sep())

    with open(output_path, 'w') as f:
        f.write('\n\n'.join(['\n'.join(e.element) for e in elements]))

    log(_('The translation of the subtitles file was completed.'))


class ConversionWorker:
    def __init__(self, gui, icon):
        self.gui = gui
        self.icon = icon
        self.config = get_config()
        self.db = gui.current_db
        self.api = self.db.new_api
        self.working_jobs = self.gui.bookfere_ebook_translator.jobs

    def translate_ebook(self, ebook, cache_only=False, is_batch=False):
        input_path = ebook.get_input_path()
        if not self.config.get('to_library'):
            output_path = os.path.join(
                self.config.get('output_path'), '%s [%s].%s' % (
                    ebook.title[:200], ebook.target_lang, ebook.output_format))
        else:
            output_path = PersistentTemporaryFile(
                suffix='.' + ebook.output_format).name

        job = self.gui.job_manager.run_job(
            Dispatcher(self.translate_done),
            'arbitrary_n',
            args=(
                'calibre_plugins.ebook_translator.lib.conversion',
                'convert_item',
                (ebook.title, input_path, output_path, ebook.source_lang,
                 ebook.target_lang, cache_only, is_batch, ebook.input_format)),
            description=(_('[{} > {}] Translating "{}"').format(
                ebook.source_lang, ebook.target_lang, ebook.title)))
        self.working_jobs[job] = (ebook, output_path)

    def translate_done(self, job):
        ebook, output_path = self.working_jobs.pop(job)

        if job.failed:
            DEBUG or self.gui.job_exception(
                job, dialog_title=_('Translation job failed'))
            return

        if self.config.get('to_library'):
            with open(output_path, 'rb') as file:
                metadata = get_metadata(file, ebook.output_format)
                if ebook.is_extra_format():
                    metadata.title = ebook.title
            book_id = self.db.create_book_entry(metadata)
            self.api.add_format(
                book_id, ebook.output_format, output_path, run_hooks=False)
            self.gui.library_view.model().books_added(1)
            output_path = self.api.format_abspath(book_id, ebook.output_format)
            # os.remove(temp_file)

        ebook_metadata = self.config.get('ebook_metadata')
        if not ebook.is_extra_format() and ebook_metadata:
            with open(output_path, 'r+b') as file:
                metadata = get_metadata(file, ebook.output_format)
                if ebook_metadata.get('language'):
                    metadata.language = ebook.lang_code
                subjects = ebook_metadata.get('subjects')
                metadata.tags += subjects or ['Translate by Ebook Translator']
                # metadata.title = 'Custom Title'
                # metadata.authors = ['bookfere.com']
                # metadata.author_sort = 'bookfere.com'
                # metadata.book_producer = 'Ebook Translator'
                set_metadata(file, metadata, ebook.output_format)

        self.gui.status_bar.show_message(
            job.description + ' ' + _('completed'), 5000)

        openers = {'srt': open_path}
        opener = openers.get(ebook.input_format)

        def callback(payload):
            if opener is not None:
                opener(output_path)
            else:
                kwargs = {'args': ['ebook-viewer', output_path]}
                payload('ebook-viewer', kwargs=kwargs)
        self.gui.proceed_question(
            callback,
            self.gui.job_manager.launch_gui_app,
            job.log_path,
            _('Ebook Translation Log'),
            _('Translation Completed'),
            _('The translation of "{}" was completed. '
              'Do you want to open the book?').format(ebook.title),
            log_is_file=True,
            icon=self.icon)
