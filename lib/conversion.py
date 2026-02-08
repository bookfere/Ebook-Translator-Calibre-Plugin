import os
import os.path
from types import MethodType
from typing import Callable
from tempfile import gettempdir

from calibre import sanitize_file_name  # type: ignore
from calibre.gui2 import Dispatcher  # type: ignore
from calibre.constants import DEBUG, __version__  # type: ignore
from calibre.utils.localization import _  # type: ignore
from calibre.utils.logging import Stream  # type: ignore
from calibre.ebooks.conversion.plumber import (  # type: ignore
    Plumber, CompositeProgressReporter)
from calibre.ptempfile import PersistentTemporaryFile  # type: ignore
from calibre.ebooks.metadata.meta import (  # type: ignore
    get_metadata, set_metadata)

from .. import EbookTranslator

from .config import get_config
from .utils import log, sep, open_path, open_file, get_cache_id
from .cache import get_cache
from .element import (
    get_element_handler, get_srt_elements, get_toc_elements, get_page_elements,
    get_metadata_elements, get_pgn_elements)
from .translation import get_translator, get_translation
from .exception import ConversionAbort


load_translations()  # type: ignore


class PrepareStream:
    mode = 'r'

    def __init__(self, callback):
        self.callback = callback
        self.temp = ''

    def write(self, text):
        self.temp += text
        if text == '\n':
            self.callback(self.temp.strip('\n'))
            self.temp = ''

    def flush(self):
        pass


def convert_book(
        input_path, output_path, translation, element_handler, cache,
        debug_info, encoding, notification) -> None:
    """Process ebooks that Calibre supported."""
    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)
    _convert = plumber.output_plugin.convert
    elements = []

    def convert(self, oeb, output_path, input_plugin, opts, log):
        backup_progress = self.report_progress.global_min
        self.report_progress = CompositeProgressReporter(0, 1, notification)
        log.info('Translating ebook content... (this will take a while)')
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

        log.info(sep())
        log.info(_('Start to convert ebook format...'))
        log.info(sep())

        self.report_progress = CompositeProgressReporter(
            backup_progress, 1, notification)
        self.report_progress(0., _('Outputting ebook file...'))
        _convert(oeb, output_path, input_plugin, opts, log)

    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    plumber.run()


def convert_srt(
        input_path, output_path, translation, element_handler, cache,
        debug_info, encoding, notification) -> None:
    log.info('Translating subtitles content... (this will take a while)')
    log.info(debug_info)

    elements = get_srt_elements(input_path, encoding)
    original_group = element_handler.prepare_original(elements)
    cache.save(original_group)

    paragraphs = cache.all_paragraphs()
    translation.set_progress(notification)
    translation.handle(paragraphs)
    element_handler.add_translations(paragraphs)

    log.info(sep())
    log.info(_('Starting to output subtitles file...'))
    log.info(sep())

    with open(output_path, 'w') as file:
        file.write('\n\n'.join([e.get_translation() for e in elements]))

    log.info(_('The translation of the subtitles file was completed.'))


def convert_pgn(
        input_path, output_path, translation, element_handler, cache,
        debug_info, encoding, notification) -> None:
    log.info('Translating PGN content... (this may be take a while)')
    log.info(debug_info)

    elements = get_pgn_elements(input_path, encoding)
    original_group = element_handler.prepare_original(elements)
    cache.save(original_group)

    paragraphs = cache.all_paragraphs()
    translation.set_progress(notification)
    translation.handle(paragraphs)
    element_handler.add_translations(paragraphs)

    log.info(sep())
    log.info(_('Starting to output PGN file...'))
    log.info(sep())

    pgn_content = open_file(input_path, encoding)
    for element in elements:
        pgn_content = pgn_content.replace(
            element.get_raw(), element.get_translation(), 1)
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(pgn_content)

    log.info(_('The translation of the PGN file was completed.'))


extra_formats: dict[str, dict[str, Callable]] = {
    'srt': {
        'extractor': get_srt_elements,
        'convertor': convert_srt,
    },
    'pgn': {
        'extractor': get_pgn_elements,
        'convertor': convert_pgn,
    }
}


def extract_item(input_path, input_format, encoding, callback=None):
    if callback is not None:
        log.outputs = [Stream(PrepareStream(callback))]
    handler = extra_formats.get(input_format)
    extractor = extract_book if handler is None else handler['extractor']
    return extractor(input_path, encoding)


def extract_book(input_path, encoding):
    elements = []
    output_path = os.path.join(gettempdir(), 'temp.epub')
    plumber = Plumber(input_path, output_path, log=log)

    def convert(self, oeb, output_path, input_plugin, opts, log):
        # for item in oeb.manifest.items:
        #     if item.media_type == 'text/css':
        #         for rule in item.data.cssRules:
        #             print('='*20)
        #             # CSSStyleRule or CSSPageRule
        #             print(type(rule))
        #             # CSSStyleDeclaration
        #             print(rule.style.keys())
        elements.extend(get_metadata_elements(oeb.metadata))
        elements.extend(get_toc_elements(oeb.toc.nodes, []))
        elements.extend(get_page_elements(oeb.manifest.items))
        raise ConversionAbort()
    plumber.output_plugin.convert = MethodType(convert, plumber.output_plugin)
    try:
        plumber.run()
    except ConversionAbort:
        return elements


def convert_item(
        ebook_title, input_path, output_path, source_lang, target_lang,
        cache_only, is_batch, format, encoding, direction, notification):
    """The following parameters need attention:
    :cache_only: Only use the translation which exists in the cache.
    :notification: It is automatically added by arbitrary_n.
    """
    translator = get_translator()
    translator.set_source_lang(source_lang)
    translator.set_target_lang(target_lang)

    element_handler = get_element_handler(
        translator.placeholder, translator.separator, direction)
    element_handler.set_translation_lang(
        translator.get_iso639_target_code(target_lang))
    element_handler.set_source_lang(
        translator.get_source_code(translator.source_lang))

    merge_length = element_handler.get_merge_length()
    cache_id = get_cache_id(
        input_path, translator.name, target_lang, merge_length, encoding)
    cache = get_cache(cache_id)
    cache.set_cache_only(cache_only)
    cache.set_info('title', ebook_title)
    cache.set_info('engine_name', translator.name)
    cache.set_info('target_lang', target_lang)
    cache.set_info('merge_length', merge_length)
    cache.set_info('plugin_version', EbookTranslator.__version__)
    cache.set_info('calibre_version', __version__)
    cache.set_info('source_lang', source_lang)
    cache.set_info('target_direction', direction)

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
    debug_info += '| Encoding: %s\n' % encoding
    debug_info += '| Cache Enabled: %s\n' % cache.is_persistence()
    debug_info += '| Merging Length: %s\n' % element_handler.merge_length
    debug_info += '| Concurrent requests: %s\n' % translator.concurrency_limit
    debug_info += '| Request Interval: %s\n' % translator.request_interval
    debug_info += '| Request Attempt: %s\n' % translator.request_attempt
    debug_info += '| Request Timeout: %s\n' % translator.request_timeout
    debug_info += '| Input Path: %s\n' % input_path
    debug_info += '| Output Path: %s' % output_path

    handler: dict[str, Callable] | None = extra_formats.get(format)
    convertor = convert_book if handler is None else handler['convertor']
    convertor(
        input_path, output_path, translation, element_handler, cache,
        debug_info, encoding, notification)
    cache.done()


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
            filename = sanitize_file_name(ebook.title[:200])
            output_path = self.config.get('output_path')
            if output_path is None or not os.path.isdir(output_path):
                raise Exception(
                    _('Please set a valid output path.'))
            output_path = os.path.join(
                output_path, f'{filename}.{ebook.output_format}')
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
                 ebook.target_lang, cache_only, is_batch, ebook.input_format,
                 ebook.encoding, ebook.target_direction)),
            description=(_('[{} > {}] Translating "{}"').format(
                ebook.source_lang, ebook.target_lang, ebook.title)))
        self.working_jobs[job] = (ebook, output_path)

    def translate_done(self, job):
        ebook, output_path = self.working_jobs.pop(job)

        if job.failed:
            if not DEBUG:
                self.gui.job_exception(
                    job, dialog_title=_('Translation job failed'))
            return

        # TODO: Try to use the calibre generated metadata file.
        ebook_metadata_config = self.config.get('ebook_metadata') or {}
        if not ebook.is_extra_format():
            with open(output_path, 'r+b') as file:
                metadata = get_metadata(file, ebook.output_format)
                ebook_title = metadata.title
                if ebook.custom_title is not None:
                    ebook_title = ebook.custom_title
                if ebook_metadata_config.get('lang_mark'):
                    ebook_title = '%s [%s]' % (ebook_title, ebook.target_lang)
                metadata.title = ebook_title
                if ebook_metadata_config.get('lang_code', True):
                    metadata.language = ebook.lang_code
                subjects = ebook_metadata_config.get('subjects')
                metadata.tags += (subjects or []) + [
                    'Translated by Ebook Translator: '
                    'https://translator.bookfere.com']
                # metadata.authors = ['bookfere.com']
                # metadata.book_producer = 'Ebook Translator'
                set_metadata(file, metadata, ebook.output_format)

            # Add RTL/LTR OPF metadata by modifying the EPUB after write
            if ebook.output_format.lower() == 'epub' and ebook.target_direction:
                from ..engines.languages import lang_directionality

                target_direction = ebook.target_direction.lower()
                translator = get_translator()
                source_lang_code = translator.get_source_code(
                    ebook.source_lang)
                source_lang_base = (
                    source_lang_code.split('-')[0]
                    if source_lang_code else None)
                source_direction = lang_directionality.get(
                    source_lang_code) or (
                    lang_directionality.get(source_lang_base)
                    if source_lang_base else None) or 'ltr'

                if (target_direction in ('rtl', 'ltr')
                        and source_direction != target_direction):
                    try:
                        from lxml import etree
                        from calibre.ebooks.oeb.polish.container import (
                            get_container)

                        container = get_container(
                            output_path, tweak_mode=True)
                        opf_root = container.opf
                        ns = {'opf': 'http://www.idpf.org/2007/opf'}

                        # Set spine page-progression-direction
                        spine_elem = opf_root.xpath(
                            '//opf:spine', namespaces=ns)[0]
                        spine_elem.set(
                            'page-progression-direction', target_direction)

                        # Add primary-writing-mode meta
                        writing_mode = (
                            'horizontal-rl' if target_direction == 'rtl'
                            else 'horizontal-lr')
                        metadata_elem = opf_root.xpath(
                            '//opf:metadata', namespaces=ns)[0]
                        etree.SubElement(
                            metadata_elem,
                            '{http://www.idpf.org/2007/opf}meta',
                            attrib={
                                'name': 'primary-writing-mode',
                                'content': writing_mode,
                            })

                        container.dirty(container.opf_name)
                        container.commit()
                        log.info(
                            'Added RTL metadata: '
                            'primary-writing-mode=%s, '
                            'page-progression-direction=%s'
                            % (writing_mode, target_direction))
                    except Exception as e:
                        log.warn(
                            'Failed to add RTL metadata to EPUB: %s' % e)
        else:
            metadata = self.api.get_metadata(ebook.id)
            ebook_title = ebook.title
            if ebook.custom_title is not None:
                ebook_title = ebook.custom_title
            if ebook_metadata_config.get('lang_mark'):
                ebook_title = '%s [%s]' % (ebook_title, ebook.target_lang)
            metadata.title = ebook_title

        if self.config.get('to_library'):
            book_id = self.db.create_book_entry(metadata)
            self.api.add_format(
                book_id, ebook.output_format, output_path, run_hooks=False)
            self.gui.library_view.model().books_added(1)
            output_path = self.api.format_abspath(book_id, ebook.output_format)
        else:
            dirname = os.path.dirname(output_path)
            filename = sanitize_file_name(ebook_title[:200])
            new_output_path = os.path.join(
                dirname, '%s.%s' % (filename, ebook.output_format))
            os.rename(output_path, new_output_path)
            output_path = new_output_path

        self.gui.status_bar.show_message(
            job.description + ' ' + _('completed'), 5000)

        def callback(payload):
            if ebook.input_format in extra_formats.keys():
                open_path(output_path)
            else:
                kwargs = {'args': ['ebook-viewer', output_path]}
                payload('ebook-viewer', kwargs=kwargs)

        if self.config.get('show_notification', True):
            self.gui.proceed_question(
                callback,
                self.gui.job_manager.launch_gui_app,
                job.log_path,
                _('Ebook Translation Log'), _('Translation Completed'),
                _('The translation of "{}" was completed. Do you want to '
                  'open the book?').format(ebook_title),
                log_is_file=True, icon=self.icon, auto_hide_after=10)
