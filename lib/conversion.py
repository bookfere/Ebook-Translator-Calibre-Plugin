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
from .utils import log, sep, uid, open_path, open_file
from .cache import get_cache
from .element import (
    get_element_handler, get_srt_elements, get_toc_elements, get_page_elements,
    get_metadata_elements, get_pgn_elements)
from .translation import get_translator, get_translation
from .novel import (
    ChapterBuilder, ContextManager, NovelTranslator, novel_cache_id)
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


def convert_book_novel(
        input_path, output_path, translator, element_handler, cache,
        debug_info, encoding, notification,
        chapter_source='toc_level_1',
        novel_config=None,
        log_callback=None,
        progress_callback=None,
        cancel_request=None,
        chapter_started=None,
        chapter_done=None,
        cache_only=False) -> None:
    """Novel-mode variant of ``convert_book``.

    Translates the book sequentially, chapter-by-chapter, maintaining a
    running summary + glossary through a ``ContextManager`` persisted in the
    same SQLite cache. Metadata and TOC titles are translated with the
    classic single-shot pipeline (they are not narrative content) so this
    function accepts a *translator* rather than the wrapped ``Translation``
    orchestrator used by ``convert_book``.

    :translator: an already-configured engine instance (source_lang,
        target_lang and merge_enabled must be set by the caller). Only
        GenAI-compatible engines make sense here.
    :chapter_source: strategy passed to ``ChapterBuilder`` ('toc_level_1'
        or 'xhtml_file').
    :novel_config: dict of ``novel_*`` config keys read from
        ``lib.config.get_config``.
    :log_callback: callable(str, bool=False). Logging function reused by
        the UI (mirrors ``lib.translation.Translation.set_logging``).
    :progress_callback: callable(float 0..1, str message).
    :cancel_request: callable() -> bool. If True, the pipeline raises
        ``TranslationCanceled`` at the next safe point.
    :chapter_started / chapter_done: UI callbacks (see NovelTranslator).
    :cache_only: If True, do NOT translate anything. Just use existing
        translations from the SQLite cache to rebuild the output ebook.
        This is the mode used by the UI "Build translated ebook" button
        after the user has already run the pipeline interactively.
    """
    log_callback = log_callback or (lambda *a, **k: None)
    progress_callback = progress_callback or (lambda *a, **k: None)
    cancel_request = cancel_request or (lambda: False)

    plumber = Plumber(
        input_path, output_path, log=log, report_progress=notification)
    _convert = plumber.output_plugin.convert
    elements = []

    def convert(self, oeb, output_path, input_plugin, opts, log):
        backup_progress = self.report_progress.global_min
        self.report_progress = CompositeProgressReporter(0, 1, notification)
        log.info('Translating ebook content in novel mode...')
        log.info(debug_info)

        # 1. Extract elements exactly like the classic pipeline. Novel mode
        #    still relies on the same DOM handler for TOC/metadata and
        #    for reinserting the translated paragraphs at the end.
        elements.extend(get_metadata_elements(oeb.metadata))
        elements.extend(get_toc_elements(oeb.toc.nodes, []))
        elements.extend(get_page_elements(oeb.manifest.items))
        original_group = element_handler.prepare_original(elements)
        # ``save`` is idempotent: it only writes when the cache is fresh.
        cache.save(original_group)

        paragraphs = cache.all_paragraphs()

        if cache_only:
            # Cache-only path: the UI already ran the translation pipeline
            # interactively and populated the cache. We just need to inject
            # the existing translations back into the DOM and let Plumber
            # emit the output ebook. Do NOT invoke the LLM at all.
            log_callback(_(
                'Novel mode (cache-only): reusing {} cached paragraph(s).')
                .format(len(paragraphs)))
        else:
            # 2. Compute the ordered spine (xhtml pages only) so
            #    ChapterBuilder can walk the book in reading order. Reuse
            #    the same key as ``Extraction.get_sorted_pages`` for
            #    consistency.
            import re as _re
            from .utils import sorted_mixed_keys
            page_pattern = _re.compile(r'\.(xhtml|html|htm|xml|xht)$')
            xhtml_items = [item for item in oeb.manifest.items
                           if page_pattern.search(item.href or '')]
            xhtml_items.sort(
                key=lambda item: sorted_mixed_keys(item.href or ''))
            ordered_page_ids = [item.id for item in xhtml_items]

            # 3. Build chapters.
            builder = ChapterBuilder(
                ordered_page_ids, oeb.toc.nodes,
                list(oeb.manifest.items), paragraphs,
                source=chapter_source)
            chapters = builder.build()
            log_callback(
                _('Novel mode: {} chapter(s) detected.')
                .format(len(chapters)))

            # 4. Load the context manager (summaries + glossary + progress).
            ctx = ContextManager(
                cache,
                glossary_max_entries=int(
                    (novel_config or {}).get(
                        'novel_glossary_max_entries', 200) or 0),
            ).load()

            # 5. Non-chapter paragraphs (metadata, TOC titles): translate
            #    them with the classic single-shot translator so the
            #    resulting ebook is not stuck with English titles /
            #    metadata.
            aux_paragraphs = [
                p for p in paragraphs
                if p.page in ChapterBuilder.AUX_PAGES
                and not p.ignored and not p.translation]
            if aux_paragraphs:
                log_callback(
                    _('Novel mode: translating {} auxiliary item(s) '
                      '(metadata/TOC).').format(len(aux_paragraphs)))
                for para in aux_paragraphs:
                    if cancel_request():
                        from .exception import TranslationCanceled
                        raise TranslationCanceled(
                            _('Translation canceled.'))
                    try:
                        if hasattr(translator, 'restore_prompt'):
                            translator.restore_prompt()
                        text = translator.translate(para.original)
                        if hasattr(text, '__iter__') and not isinstance(
                                text, str):
                            text = ''.join(text)
                        para.translation = (text or '').strip()
                        para.engine_name = translator.name
                        para.target_lang = (
                            translator.get_target_lang()
                            if hasattr(translator, 'get_target_lang')
                            else getattr(translator, 'target_lang', None))
                        cache.update_paragraph(para)
                    except Exception as exc:
                        log_callback(
                            _('Auxiliary translation failed for id={}: {}')
                            .format(para.id, exc), True)

            # 6. Run the novel translator on chapter content.
            novel_translator = NovelTranslator(
                translator, chapters, ctx, cache,
                config=novel_config or {})
            novel_translator.set_logging(log_callback)
            novel_translator.set_progress(progress_callback)
            novel_translator.set_cancel_request(cancel_request)
            if chapter_started is not None:
                novel_translator.set_chapter_started(chapter_started)
            if chapter_done is not None:
                novel_translator.set_chapter_done(chapter_done)
            novel_translator.run()

        # 7. Reload paragraphs from cache (they were mutated during
        #    translation via update_paragraph) and reinject into the DOM.
        paragraphs = cache.all_paragraphs()
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

    merge_length = str(element_handler.get_merge_length())
    _encoding = ''
    if encoding.lower() != 'utf-8':
        _encoding = encoding.lower()
    cache_id = uid(
        input_path + translator.name + target_lang + merge_length + _encoding)
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


def convert_item_novel(
        ebook_title, input_path, output_path, source_lang, target_lang,
        cache_only, format, encoding, direction, notification):
    """Novel-mode variant of ``convert_item``.

    Kept as a *separate* function (rather than a flag on ``convert_item``)
    because Calibre's ``arbitrary_n`` job runner injects ``notification`` as
    the last positional argument of the callable. Adding any parameter
    between ``direction`` and ``notification`` would collide with that
    convention and raise "multiple values for argument 'notification'".

    :cache_only: If True, do NOT invoke the LLM. Reuse the cache populated
        by the interactive UI (``NovelTranslation`` dialog) and only rebuild
        the output ebook via Plumber. This is the mode used by the
        "Build translated ebook" button.
    """
    if format in extra_formats:
        raise Exception(
            _('Novel mode is not supported for {} files.').format(format))

    translator = get_translator()
    translator.set_source_lang(source_lang)
    translator.set_target_lang(target_lang)

    element_handler = get_element_handler(
        translator.placeholder, translator.separator, direction)
    element_handler.set_translation_lang(
        translator.get_iso639_target_code(target_lang))

    _encoding = ''
    if encoding.lower() != 'utf-8':
        _encoding = encoding.lower()
    cache_id = novel_cache_id(
        input_path, translator.name, target_lang, _encoding)
    cache = get_cache(cache_id)
    cache.set_cache_only(cache_only)
    cache.set_info('title', ebook_title)
    cache.set_info('engine_name', translator.name)
    cache.set_info('target_lang', target_lang)
    cache.set_info('plugin_version', EbookTranslator.__version__)
    cache.set_info('calibre_version', __version__)
    cache.set_info('novel_mode', '1')

    debug_info = '{0}\n| Diagnosis Information\n{0}'.format(sep())
    debug_info += '\n| Calibre Version: %s\n' % __version__
    debug_info += '| Plugin Version: %s\n' % EbookTranslator.__version__
    debug_info += '| Translation Engine: %s\n' % translator.name
    debug_info += '| Source Language: %s\n' % source_lang
    debug_info += '| Target Language: %s\n' % target_lang
    debug_info += '| Encoding: %s\n' % encoding
    debug_info += '| Cache Enabled: %s\n' % cache.is_persistence()
    debug_info += '| Cache-only: %s\n' % ('yes' if cache_only else 'no')
    debug_info += '| Novel Mode: yes\n'
    debug_info += '| Input Path: %s\n' % input_path
    debug_info += '| Output Path: %s' % output_path

    config = get_config()
    novel_config = {
        'novel_chunk_tokens': config.get('novel_chunk_tokens', 12000),
        'novel_max_paragraphs_per_chunk': config.get(
            'novel_max_paragraphs_per_chunk', 60),
        'novel_context_tokens': config.get('novel_context_tokens', 1500),
        'novel_summary_tokens': config.get('novel_summary_tokens', 400),
        'novel_glossary_max_entries': config.get(
            'novel_glossary_max_entries', 200),
        'novel_min_chars_for_context': config.get(
            'novel_min_chars_for_context', 300),
        'novel_translation_prompt': config.get(
            'novel_translation_prompt', None),
        'novel_summary_prompt': config.get(
            'novel_summary_prompt', None),
        'novel_glossary_prompt': config.get(
            'novel_glossary_prompt', None),
    }
    chapter_source = config.get(
        'novel_chapter_source', 'toc_level_1') or 'toc_level_1'

    convert_book_novel(
        input_path, output_path, translator, element_handler, cache,
        debug_info, encoding, notification,
        chapter_source=chapter_source,
        novel_config=novel_config,
        log_callback=lambda text, error=False: log.info(text),
        progress_callback=notification,
        cache_only=cache_only,
    )
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

    def translate_ebook_novel(self, ebook, cache_only=True):
        """Launch a novel-mode job.

        Typically used only with ``cache_only=True`` to rebuild the output
        ebook after the interactive novel-mode UI has already populated
        the cache. Uses a dedicated ``convert_item_novel`` entry point so
        it does not conflict with the classic pipeline's positional args.
        """
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
                'convert_item_novel',
                (ebook.title, input_path, output_path, ebook.source_lang,
                 ebook.target_lang, cache_only, ebook.input_format,
                 ebook.encoding, ebook.target_direction)),
            description=(_('[{} > {}] Building novel "{}"').format(
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
                if ebook_metadata_config.get('lang_code'):
                    metadata.language = ebook.lang_code
                subjects = ebook_metadata_config.get('subjects')
                metadata.tags += (subjects or []) + [
                    'Translated by Ebook Translator: '
                    'https://translator.bookfere.com']
                # metadata.authors = ['bookfere.com']
                # metadata.author_sort = 'bookfere.com'
                # metadata.book_producer = 'Ebook Translator'
                set_metadata(file, metadata, ebook.output_format)
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
