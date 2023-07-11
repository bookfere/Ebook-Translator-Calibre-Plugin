import os
import os.path
from types import MethodType
from tempfile import gettempdir

from calibre.gui2 import Dispatcher
from calibre.constants import __version__, DEBUG
from calibre.ebooks.conversion.plumber import Plumber
from calibre.ptempfile import PersistentTemporaryFile
from calibre.ebooks.metadata.meta import get_metadata, set_metadata

from .. import EbookTranslator

from .config import get_config
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

    element_handler = get_element_handler(translator.placeholder)
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

        elements = get_ebook_elements(oeb.manifest.items)
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


class ConversionWorker:
    def __init__(self, gui, icon):
        self.gui = gui
        self.icon = icon
        self.config = get_config()
        self.db = gui.current_db
        self.api = self.db.new_api
        self.working_jobs = self.gui.bookfere_ebook_translator.jobs

    def translate_ebook(self, ebook, cache_only=False):
        input_path = ebook.get_input_path()
        if not self.config.get('to_library'):
            output_path = os.path.join(
                self.config.get('output_path'), '%s (%s).%s' % (
                    ebook.title[:200], ebook.target_lang, ebook.output_format))
        else:
            output_path = PersistentTemporaryFile(
                suffix='.' + ebook.output_format).name

        job = self.gui.job_manager.run_job(
            Dispatcher(self.translate_done),
            'arbitrary_n',
            args=(
                'calibre_plugins.ebook_translator.lib.conversion',
                'convert_book',
                (ebook.title, input_path, output_path, ebook.source_lang,
                 ebook.target_lang, cache_only)),
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
            book_id = self.db.create_book_entry(metadata)
            self.api.add_format(
                book_id, ebook.output_format, output_path, run_hooks=False)
            self.gui.library_view.model().books_added(1)
            output_path = self.api.format_abspath(book_id, ebook.output_format)
            # os.remove(temp_file)

        ebook_metadata = self.config.get('ebook_metadata')
        if ebook_metadata:
            with open(output_path, 'r+b') as file:
                metadata = get_metadata(file, ebook.output_format)
                if ebook_metadata.get('language'):
                    metadata.language = ebook.lang_code
                subjects = ebook_metadata.get('subjects')
                metadata.tags = subjects or ['Translate by Ebook Translator']
                # metadata.title = 'Custom Title'
                # metadata.authors = ['bookfere.com']
                # metadata.author_sort = 'bookfere.com'
                # metadata.book_producer = 'Ebook Translator'
                set_metadata(file, metadata, ebook.output_format)

        self.gui.status_bar.show_message(
            job.description + ' ' + _('completed'), 5000)

        self.gui.proceed_question(
            lambda payload: payload(
                'ebook-viewer',
                kwargs={'args': ['ebook-viewer', output_path]}),
            self.gui.job_manager.launch_gui_app,
            job.log_path,
            _('Ebook Translation Log'),
            _('Translation Completed'),
            _('The translation of "{}" was completed. '
              'Do you want to open the book?').format(ebook.title),
            log_is_file=True,
            icon=self.icon)
