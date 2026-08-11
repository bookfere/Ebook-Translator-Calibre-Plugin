import time
from types import MethodType

from qt.core import (  # type: ignore
    Qt, QObject, QDialog, QGroupBox, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QSplitter, QLabel, QThread, QLineEdit,
    QGridLayout, QProgressBar, pyqtSignal, pyqtSlot, QPixmap, QEvent,
    QStackedWidget, QSpacerItem, QTabWidget, QCheckBox,
    QComboBox, QSizePolicy)
from calibre.constants import __version__  # type: ignore
from calibre.gui2 import I  # type: ignore
from calibre.utils.localization import _  # type: ignore

from . import EbookTranslator
from .lib.utils import uid, traceback_error
from .lib.config import get_config
from .lib.encodings import encoding_list
from .lib.cache import Paragraph, get_cache
from .lib.translation import get_engine_class, get_translator, get_translation
from .lib.element import get_element_handler
from .lib.conversion import extract_item, extra_formats
from .engines.openai import ChatgptTranslate, ChatgptBatchTranslate
from .engines.custom import CustomTranslate
from .components import (
    EngineList, Footer, SourceLang, TargetLang, InputFormat, OutputFormat,
    AlertMessage, AdvancedTranslationTable, StatusColor, TranslationStatus,
    set_shortcut, ChatgptBatchTranslationManager)
from .components.editor import CodeEditor


load_translations()  # type: ignore


class EditorWorker(QObject):
    start = pyqtSignal((str,), (str, object))
    show = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self):
        QObject.__init__(self)
        self.start[str].connect(self.show_message)
        self.start[str, object].connect(self.show_message)

    @pyqtSlot(str)
    @pyqtSlot(str, object)
    def show_message(self, message, callback=None):
        time.sleep(0.01)
        self.show.emit(message)
        time.sleep(1)
        self.show.emit('')
        if callback is not None:
            callback()
        self.finished.emit()


class PreparationWorker(QObject):
    start = pyqtSignal()
    progress = pyqtSignal(int)
    progress_message = pyqtSignal(str)
    progress_detail = pyqtSignal(str)
    close = pyqtSignal(int)
    finished = pyqtSignal(str)

    def __init__(self, engine_class, ebook):
        QObject.__init__(self)
        self.engine_class = engine_class
        self.ebook = ebook

        self.on_working = False
        self.canceled = False

        self.start.connect(self.prepare_ebook_data)

    def clean_cache(self, cache):
        if cache.is_fresh():
            cache.destroy()
        self.on_working = False
        self.close.emit(1)

    def set_canceled(self, canceled):
        self.canceled = canceled

    # def cancel(self):
    #     return self.thread().isInterruptionRequested()

    @pyqtSlot()
    def prepare_ebook_data(self):
        self.on_working = True
        input_path = self.ebook.get_input_path()
        element_handler = get_element_handler(
            self.engine_class.placeholder, self.engine_class.separator,
            self.ebook.target_direction)
        merge_length = str(element_handler.get_merge_length())
        encoding = ''
        if self.ebook.encoding.lower() != 'utf-8':
            encoding = self.ebook.encoding.lower()
        cache_id = uid(
            input_path + self.engine_class.name + self.ebook.target_lang
            + merge_length + encoding)
        cache = get_cache(cache_id)

        if cache.is_fresh() or not cache.is_persistence():
            self.progress_detail.emit(
                'Start processing the ebook: %s' % self.ebook.title)
            cache.set_info('title', self.ebook.title)
            cache.set_info('engine_name', self.engine_class.name)
            cache.set_info('target_lang', self.ebook.target_lang)
            cache.set_info('merge_length', merge_length)
            cache.set_info('plugin_version', EbookTranslator.__version__)
            cache.set_info('calibre_version', __version__)
            # --------------------------
            a = time.time()
            # --------------------------
            self.progress_message.emit(_('Extracting ebook content...'))
            try:
                elements = extract_item(
                    input_path, self.ebook.input_format, self.ebook.encoding,
                    self.progress_detail.emit)
            except Exception:
                self.progress_message.emit(
                    _('Failed to extract ebook content'))
                self.progress_detail.emit('\n' + traceback_error())
                self.progress.emit(100)
                self.clean_cache(cache)
                return
            if self.canceled:
                self.clean_cache(cache)
                return
            self.progress.emit(30)
            b = time.time()
            self.progress_detail.emit('extracting timing: %s' % (b - a))
            if self.canceled:
                self.clean_cache(cache)
                return
            # --------------------------
            self.progress_message.emit(_('Filtering ebook content...'))
            original_group = element_handler.prepare_original(elements)
            self.progress.emit(80)
            c = time.time()
            self.progress_detail.emit('filtering timing: %s' % (c - b))
            if self.canceled:
                self.clean_cache(cache)
                return
            # --------------------------
            self.progress_message.emit(_('Preparing user interface...'))
            cache.save(original_group)
            self.progress.emit(100)
            d = time.time()
            self.progress_detail.emit('cache timing: %s' % (d - c))
            if self.canceled:
                self.clean_cache(cache)
                return
        else:
            self.progress_detail.emit(
                'Loading data from cache and preparing user interface...')
            time.sleep(0.1)

        self.finished.emit(cache_id)
        self.on_working = False


class TranslationWorker(QObject):
    start = pyqtSignal()
    close = pyqtSignal(int)
    finished = pyqtSignal()
    translate = pyqtSignal(list, bool)
    logging = pyqtSignal(str, bool)
    # error = pyqtSignal(str, str, str)
    streaming = pyqtSignal(object)
    callback = pyqtSignal(object)

    def __init__(self, engine_class, ebook):
        QObject.__init__(self)
        self.source_lang = ebook.source_lang
        self.target_lang = ebook.target_lang
        self.engine_class = engine_class

        self.on_working = False
        self.canceled = False
        self.need_close = False
        self.translate.connect(self.translate_paragraphs)
        # self.finished.connect(lambda: self.set_canceled(False))

    def set_source_lang(self, lang):
        self.source_lang = lang

    def set_target_lang(self, lang):
        self.target_lang = lang

    def set_engine_class(self, engine_class):
        self.engine_class = engine_class

    def set_canceled(self, canceled):
        self.canceled = canceled

    def cancel_request(self):
        return self.canceled

    def set_need_close(self, need_close):
        self.need_close = need_close

    @pyqtSlot(list, bool)
    def translate_paragraphs(self, paragraphs=[], fresh=False):
        """:fresh: retranslate all paragraphs."""
        self.on_working = True
        self.start.emit()
        translator = get_translator(self.engine_class)
        translator.set_source_lang(self.source_lang)
        translator.set_target_lang(self.target_lang)
        translation = get_translation(translator)
        translation.set_fresh(fresh)
        translation.set_logging(
            lambda text, error=False: self.logging.emit(text, error))
        translation.set_streaming(self.streaming.emit)
        translation.set_callback(self.callback.emit)
        translation.set_cancel_request(self.cancel_request)
        translation.handle(paragraphs)
        self.on_working = False
        self.finished.emit()
        if self.need_close:
            time.sleep(0.5)
            self.close.emit(0)


class CreateTranslationProject(QDialog):
    start_translation = pyqtSignal(object)

    def __init__(self, parent, ebook):
        QDialog.__init__(self, parent)
        self.ebook = ebook

        layout = QVBoxLayout(self)
        self.choose_format = self.layout_format()

        self.start_button = QPushButton(_('&Start'))
        # self.start_button.setStyleSheet(
        #     'padding:0;height:48;font-size:20px;color:royalblue;'
        #     'text-transform:uppercase;')
        self.start_button.clicked.connect(self.show_advanced)

        layout.addWidget(self.choose_format)
        layout.addWidget(self.start_button)

    def layout_format(self):
        engine_class = get_engine_class()
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        input_group = QGroupBox(_('Input Format'))
        input_layout = QGridLayout(input_group)
        input_format = InputFormat(self.ebook.files.keys())
        # input_format.setFixedWidth(150)
        input_layout.addWidget(input_format)
        layout.addWidget(input_group, 0, 0, 1, 3)

        output_group = QGroupBox(_('Output Format'))
        output_layout = QGridLayout(output_group)
        output_format = OutputFormat()
        # output_format.setFixedWidth(150)
        output_layout.addWidget(output_format)
        layout.addWidget(output_group, 0, 3, 1, 3)

        source_group = QGroupBox(_('Source Language'))
        source_layout = QVBoxLayout(source_group)
        source_lang = SourceLang()
        source_lang.setFixedWidth(150)
        source_layout.addWidget(source_lang)
        layout.addWidget(source_group, 1, 0, 1, 2)

        target_group = QGroupBox(_('Target Language'))
        target_layout = QVBoxLayout(target_group)
        target_lang = TargetLang()
        target_lang.setFixedWidth(150)
        target_layout.addWidget(target_lang)
        layout.addWidget(target_group, 1, 2, 1, 2)

        source_lang.refresh.emit(
            engine_class.lang_codes.get('source'),
            engine_class.config.get('source_lang'),
            not issubclass(engine_class, CustomTranslate))

        target_lang.refresh.emit(
            engine_class.lang_codes.get('target'),
            engine_class.config.get('target_lang'))

        def change_input_format(_format):
            self.ebook.set_input_format(_format)
        change_input_format(input_format.currentText())
        input_format.currentTextChanged.connect(change_input_format)

        def change_output_format(_format):
            self.ebook.set_output_format(_format)
        if self.ebook.is_extra_format():
            output_format.lock_format(self.ebook.input_format)
            change_output_format(self.ebook.input_format)
        else:
            change_output_format(output_format.currentText())
            output_format.currentTextChanged.connect(change_output_format)

        def change_source_lang(lang):
            self.ebook.set_source_lang(lang)
        change_source_lang(source_lang.currentText())
        source_lang.currentTextChanged.connect(change_source_lang)

        def change_target_lang(lang):
            self.ebook.set_target_lang(lang)
            self.ebook.set_lang_code(
                engine_class.get_iso639_target_code(lang))
        change_target_lang(target_lang.currentText())
        target_lang.currentTextChanged.connect(change_target_lang)

        if self.ebook.input_format in extra_formats.keys():
            encoding_group = QGroupBox(_('Encoding'))
            encoding_layout = QVBoxLayout(encoding_group)
            encoding_select = QComboBox()
            encoding_select.setFixedWidth(150)
            encoding_select.addItems(encoding_list)
            encoding_layout.addWidget(encoding_select)
            layout.addWidget(encoding_group, 1, 4, 1, 2)

            def change_encoding(encoding):
                self.ebook.set_encoding(encoding)
            encoding_select.currentTextChanged.connect(change_encoding)
        else:
            direction_group = QGroupBox(_('Target Directionality'))
            direction_layout = QVBoxLayout(direction_group)
            direction_list = QComboBox()
            direction_list.setFixedWidth(150)
            direction_list.addItem(_('Auto'), 'auto')
            direction_list.addItem(_('Left to Right'), 'ltr')
            direction_list.addItem(_('Right to Left'), 'rtl')
            direction_layout.addWidget(direction_list)
            layout.addWidget(direction_group, 1, 4, 1, 2)

            def change_direction(_index):
                _direction = direction_list.itemData(_index)
                self.ebook.set_target_direction(_direction)
            direction_list.currentIndexChanged.connect(change_direction)

            engine_target_lange_codes = engine_class.lang_codes.get('target')
            if engine_target_lange_codes is not None and \
                    self.ebook.target_lang in engine_target_lange_codes:
                target_lang_code = engine_target_lange_codes[
                    self.ebook.target_lang]
                direction = engine_class.get_lang_directionality(
                    target_lang_code)
                index = direction_list.findData(direction)
                direction_list.setCurrentIndex(index)

        return widget

    @pyqtSlot()
    def show_advanced(self):
        self.done(0)
        self.start_translation.emit(self.ebook)


class AdvancedTranslation(QDialog):
    paragraph_sig = pyqtSignal(object)
    ebook_title = pyqtSignal()
    progress_bar = pyqtSignal()
    batch_translation = pyqtSignal()

    def __init__(self, plugin, parent, worker, ebook):
        QDialog.__init__(self, parent)

        self.ui_settings = plugin.ui_settings
        self.api = parent.current_db.new_api
        self.worker = worker
        self.ebook = ebook

        self.config = get_config()
        self.alert = AlertMessage(self)
        self.footer = Footer()
        # self.error = JobError(self)
        self.current_engine = get_engine_class()
        self.cache = None
        self.merge_enabled = False

        self.progress_step = 0
        self.translate_all = False

        # Create threads per-instance to avoid accumulating signal
        # connections across dialog instances.
        self.preparation_thread = QThread()
        self.trans_thread = QThread()
        self.editor_thread = QThread()

        self.editor_worker = EditorWorker()
        self.editor_worker.moveToThread(self.editor_thread)
        self.editor_thread.start()

        self.trans_worker = TranslationWorker(self.current_engine, self.ebook)
        self.trans_worker.close.connect(self.done)
        self.trans_worker.moveToThread(self.trans_thread)
        self.trans_thread.start()

        self.preparation_worker = PreparationWorker(
            self.current_engine, self.ebook)
        self.preparation_worker.close.connect(self.done)
        self.preparation_worker.moveToThread(self.preparation_thread)
        self.preparation_thread.start()

        layout = QVBoxLayout(self)

        self.waiting = self.layout_progress()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.waiting)
        layout.addWidget(self.stack)
        layout.addWidget(self.footer)

        def working_status():
            self.logging_text.clear()
            self.errors_text.clear()
        self.trans_worker.start.connect(working_status)

        self.trans_worker.logging.connect(
            lambda text, error: self.errors_text.appendPlainText(text)
            if error else self.logging_text.appendPlainText(text))

        def working_finished():
            if self.translate_all and not self.trans_worker.cancel_request():
                failures = len(self.table.get_selected_paragraphs(True, True))
                if failures > 0:
                    message = _(
                        'Failed to translate {} paragraph(s), '
                        'Would you like to retry?')
                    if self.alert.ask(message.format(failures)) == 'yes':
                        self.translate_all_paragraphs()
                        return
                else:
                    self.alert.pop(_('Translation completed.'))
            self.trans_worker.set_canceled(False)
            self.translate_all = False
        self.trans_worker.finished.connect(working_finished)

        # self.trans_worker.error.connect(
        #     lambda title, reason, detail: self.error.show_error(
        #         title, _('Failed') + ': ' + reason, det_msg=detail))

        def prepare_table_layout(cache_id):
            self.cache = get_cache(cache_id)
            merge_length = self.cache.get_info('merge_length') or 0
            self.merge_enabled = int(merge_length) > 0
            paragraphs = self.cache.all_paragraphs()
            if len(paragraphs) < 1:
                self.alert.pop(
                    _('There is no content that needs to be translated.'),
                    'warning')
                self.done(0)
                return
            self.table = AdvancedTranslationTable(self, paragraphs)
            self.panel = self.layout_panel()
            self.stack.addWidget(self.panel)
            self.stack.setCurrentWidget(self.panel)
            self.table.setFocus(Qt.OtherFocusReason)
        self.preparation_worker.finished.connect(prepare_table_layout)
        self.preparation_worker.start.emit()

    def layout_progress(self):
        widget = QWidget()
        layout = QGridLayout(widget)

        try:
            cover_image = self.api.cover(self.ebook.id, as_pixmap=True)
        except Exception:
            cover_image = QPixmap(self.api.cover(self.ebook.id, as_image=True))
        if cover_image.isNull():
            cover_image = QPixmap(I('default_cover.png'))
        cover_image = cover_image.scaledToHeight(
            480, Qt.TransformationMode.SmoothTransformation)

        cover = QLabel()
        cover.setAlignment(Qt.AlignCenter)
        cover.setPixmap(cover_image)

        title = QLabel()
        title.setMaximumWidth(cover_image.width())
        title.setText(title.fontMetrics().elidedText(
            self.ebook.title, Qt.ElideRight, title.width()))
        title.setToolTip(self.ebook.title)

        progress_bar = QProgressBar()
        progress_bar.setFormat('')
        progress_bar.setValue(0)
        # progress_bar.setFixedWidth(300)
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(0)

        def show_progress(value):
            if progress_bar.maximum() == 0:
                progress_bar.setMaximum(100)
            progress_bar.setValue(value)
        self.preparation_worker.progress.connect(show_progress)

        label = QLabel(_('Loading ebook data, please wait...'))
        label.setAlignment(Qt.AlignCenter)
        self.preparation_worker.progress_message.connect(label.setText)

        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        self.preparation_worker.progress_detail.connect(detail.appendPlainText)

        layout.addWidget(cover, 0, 0)
        layout.addWidget(title, 1, 0)
        layout.addItem(QSpacerItem(0, 20), 2, 0, 1, 3)
        layout.addWidget(progress_bar, 3, 0)
        layout.addWidget(label, 4, 0)
        layout.addItem(QSpacerItem(0, 0), 5, 0, 1, 3)
        layout.addItem(QSpacerItem(10, 0), 0, 1, 6, 1)
        layout.addWidget(detail, 0, 2, 6, 1)
        # layout.setRowStretch(0, 1)
        layout.setRowStretch(2, 1)
        layout.setColumnStretch(2, 1)
        # layout.setColumnStretch(2, 1)

        return widget

    def layout_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        review_index = tabs.addTab(self.layout_review(), _('Review'))
        log_index = tabs.addTab(self.layout_log(), _('Log'))
        errors_index = tabs.addTab(self.layout_errors(), _('Errors'))
        tabs.setStyleSheet('QTabBar::tab {min-width:120px;}')

        self.trans_worker.start.connect(
            lambda: (self.translate_all or self.table.selected_count() > 1)
            and tabs.setCurrentIndex(log_index))
        self.trans_worker.finished.connect(
            lambda: tabs.setCurrentIndex(
                errors_index if self.errors_text.toPlainText()
                and len(self.table.get_selected_paragraphs(True, True)) > 0
                else review_index))
        splitter = QSplitter()
        splitter.addWidget(self.layout_table())
        splitter.addWidget(tabs)
        splitter.setSizes([int(splitter.width() / 2)] * 2)

        layout.addWidget(self.layout_control())
        layout.addWidget(splitter, 1)

        return widget

    def layout_filter(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        categories = QComboBox()
        categories.addItem(_('All'), 'all')
        if self.merge_enabled:
            categories.addItem(_('Non-aligned'), 'non_aligned')
        categories.addItem(_('Translated'), 'translated')
        categories.addItem(_('Untranslated'), 'untranslated')

        content_types = QComboBox()
        content_types.addItem(_('Original Text'), 'original_text')
        content_types.addItem(_('Original Code'), 'original_code')
        content_types.addItem(_('Translation Text'), 'translation_text')

        search_input = QLineEdit()
        search_input.setPlaceholderText(_('keyword for filtering'))
        set_shortcut(
            search_input, 'search', search_input.setFocus,
            search_input.placeholderText())

        reset_button = QPushButton(_('Reset'))
        reset_button.setVisible(False)

        def filter_table_items(index):
            self.table.show_all_rows()
            category = categories.itemData(index)
            if category == 'non_aligned':
                self.table.hide_by_paragraphs(self.table.aligned_paragraphs())
            elif category == 'translated':
                self.table.hide_by_paragraphs(
                    self.table.untranslated_paragraphs())
            elif category == 'untranslated':
                self.table.hide_by_paragraphs(
                    self.table.translated_paragraphs())

        def filter_by_category(index):
            reset_button.setVisible(index != 0)
            filter_table_items(index)
            self.table.show_by_text(
                search_input.text(), content_types.currentData())
        categories.currentIndexChanged.connect(filter_by_category)

        def filter_by_content_type(index):
            reset_button.setVisible(index != 0)
            filter_table_items(categories.currentIndex())
            self.table.show_by_text(
                search_input.text(), content_types.itemData(index))
        content_types.currentIndexChanged.connect(filter_by_content_type)

        def filter_by_keyword(text):
            reset_button.setVisible(text != '')
            filter_table_items(categories.currentIndex())
            self.table.show_by_text(text, content_types.currentData())
        search_input.textChanged.connect(filter_by_keyword)

        def reset_filter_criteria():
            categories.setCurrentIndex(0)
            content_types.setCurrentIndex(0)
            search_input.clear()
            reset_button.setVisible(False)
        reset_button.clicked.connect(reset_filter_criteria)

        # def reset_filter():
        #     filter_table_items(categories.currentIndex())
        #     self.table.show_by_text(search_input.text())
        # self.editor_worker.finished.connect(reset_filter)
        # self.trans_worker.finished.connect(reset_filter)

        layout.addWidget(categories)
        layout.addWidget(content_types)
        layout.addWidget(search_input)
        layout.addWidget(reset_button)

        return widget

    def layout_table(self):
        widget = QWidget()
        widget.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        progress_bar = QProgressBar()
        progress_bar.setMaximum(100000000)
        progress_bar.setVisible(False)

        def write_progress():
            value = progress_bar.value() + self.progress_step
            if value > progress_bar.maximum():
                value = progress_bar.maximum()
            progress_bar.setValue(value)
        self.progress_bar.connect(write_progress)

        paragraph_count = QLabel()
        non_aligned_paragraph_count = QLabel()
        non_aligned_paragraph_count.setVisible(False)

        counter = QWidget()
        counter_layout = QHBoxLayout(counter)
        counter_layout.setContentsMargins(0, 0, 0, 0)
        counter_layout.setSpacing(0)
        counter_layout.addWidget(paragraph_count)
        counter_layout.addWidget(non_aligned_paragraph_count)
        counter_layout.addStretch(1)
        self.footer.layout().insertWidget(0, counter)

        def get_paragraph_count(select_all=True):
            item_count = char_count = 0
            paragraphs = self.table.get_selected_paragraphs(
                select_all=select_all)
            for paragraph in paragraphs:
                item_count += 1
                char_count += len(paragraph.original)
            return (item_count, char_count)
        all_item_count, all_char_count = get_paragraph_count(True)

        def item_selection_changed():
            item_count, char_count = get_paragraph_count(False)
            total = '%s/%s' % (item_count, all_item_count)
            parts = '%s/%s' % (char_count, all_char_count)
            paragraph_count.setText(
                _('Total items: {}').format(total) + ' · '
                + _('Character count: {}').format(parts))
        item_selection_changed()
        self.table.itemSelectionChanged.connect(item_selection_changed)

        if self.merge_enabled:
            non_aligned_paragraph_count.setVisible(True)

            def show_none_aligned_count():
                non_aligned_paragraph_count.setText(
                    ' · ' + _('Non-aligned items: {}')
                    .format(self.table.non_aligned_count))
            show_none_aligned_count()
            self.table.row.connect(show_none_aligned_count)

        filter_widget = self.layout_filter()

        layout.addWidget(filter_widget)
        layout.addWidget(self.table, 1)
        layout.addWidget(progress_bar)
        layout.addWidget(self.layout_table_control())

        def working_start():
            if self.translate_all or self.table.selected_count() > 1:
                filter_widget.setVisible(False)
                progress_bar.setValue(0)
                progress_bar.setVisible(True)
                counter.setVisible(False)
        self.trans_worker.start.connect(working_start)

        def working_end():
            filter_widget.setVisible(True)
            progress_bar.setVisible(False)
            counter.setVisible(True)
        self.trans_worker.finished.connect(working_end)

        return widget

    def layout_table_control(self):
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)

        delete_button = QPushButton(_('Delete'))
        delete_button.setToolTip(delete_button.text() + ' [Del]')
        batch_translation = QPushButton(
            ' %s (%s)' % (_('Batch Translation'), _('Beta')))
        translate_all = QPushButton('  %s  ' % _('Translate All'))
        translate_selected = QPushButton('  %s  ' % _('Translate Selected'))

        delete_button.clicked.connect(self.table.delete_selected_rows)
        translate_all.clicked.connect(self.translate_all_paragraphs)
        translate_selected.clicked.connect(self.translate_selected_paragraph)

        action_layout.addWidget(delete_button)
        action_layout.addStretch(1)
        action_layout.addWidget(batch_translation)
        action_layout.addWidget(translate_all)
        action_layout.addWidget(translate_selected)

        stop_widget = QWidget()
        stop_layout = QHBoxLayout(stop_widget)
        stop_layout.setContentsMargins(0, 0, 0, 0)
        # stop_layout.addStretch(1)
        stop_button = QPushButton(_('Stop'))
        stop_layout.addWidget(stop_button)

        delete_button.setDisabled(True)
        translate_selected.setDisabled(True)

        self.batch_translation.connect(
            lambda: batch_translation.setVisible(
                self.current_engine == ChatgptTranslate))
        self.batch_translation.emit()

        def start_batch_translation():
            translator = get_translator(self.current_engine)
            translator.set_source_lang(self.ebook.source_lang)
            translator.set_target_lang(self.ebook.target_lang)
            batch_translator = ChatgptBatchTranslate(translator)
            batch = ChatgptBatchTranslationManager(
                batch_translator, self.cache, self.table, self)
            batch.exec_()
        batch_translation.clicked.connect(start_batch_translation)

        def item_selection_changed():
            disabled = self.table.selected_count() < 1
            delete_button.setDisabled(disabled)
            translate_selected.setDisabled(disabled)
        item_selection_changed()
        self.table.itemSelectionChanged.connect(item_selection_changed)

        def stop_translation():
            action = self.alert.ask(
                _('Are you sure you want to stop the translation progress?'))
            if action != 'yes':
                return
            stop_button.setDisabled(True)
            stop_button.setText(_('Stopping...'))
            self.trans_worker.set_canceled(True)
        stop_button.clicked.connect(stop_translation)

        def terminate_finished():
            stop_button.setDisabled(False)
            stop_button.setText(_('Stop'))
            self.paragraph_sig.emit(self.table.current_paragraph())
        self.trans_worker.finished.connect(terminate_finished)

        stack = QStackedWidget()
        stack.addWidget(action_widget)
        stack.addWidget(stop_widget)

        def working_start():
            stack.setCurrentWidget(stop_widget)
            action_widget.setDisabled(True)
        self.trans_worker.start.connect(working_start)

        def working_finished():
            stack.setCurrentWidget(action_widget)
            action_widget.setDisabled(False)
        self.trans_worker.finished.connect(working_finished)

        return stack

    def layout_control(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        cache_group = QGroupBox(_('Cache Status'))
        cache_layout = QVBoxLayout(cache_group)
        cache_status = QLabel(
            _('Enabled') if self.cache and self.cache.is_persistence()
            else _('Disabled'))
        cache_status.setAlignment(Qt.AlignCenter)
        cache_status.setStyleSheet(
            'border-radius:2px;color:white;background-color:%s;'
            % ('green' if self.cache and self.cache.is_persistence()
               else 'grey'))
        cache_layout.addWidget(cache_status)

        engine_group = QGroupBox(_('Translation Engine'))
        engine_layout = QVBoxLayout(engine_group)
        engine_list = EngineList(self.current_engine.name)
        engine_list.setMaximumWidth(150)
        engine_layout.addWidget(engine_list)

        source_group = QGroupBox(_('Source Language'))
        source_layout = QVBoxLayout(source_group)
        source_lang = SourceLang()
        source_lang.setMaximumWidth(150)
        source_layout.addWidget(source_lang)

        target_group = QGroupBox(_('Target Language'))
        target_layout = QVBoxLayout(target_group)
        target_lang = TargetLang()
        target_lang.setMaximumWidth(150)
        target_layout.addWidget(target_lang)

        title_group = QGroupBox(_('Custom Ebook Title'))
        title_layout = QHBoxLayout(title_group)
        custom_title = QCheckBox()
        ebook_title = QLineEdit()
        ebook_title.setToolTip(
            _('By default, title metadata will be translated.'))
        ebook_title.setText(self.ebook.title)
        ebook_title.setCursorPosition(0)
        ebook_title.setDisabled(True)
        title_layout.addWidget(custom_title)
        title_layout.addWidget(ebook_title)

        def enable_custom_title(checked):
            ebook_title.setDisabled(not checked)
            self.ebook.set_custom_title(
                ebook_title.text() if checked else None)
            if checked:
                ebook_title.setFocus(Qt.MouseFocusReason)
        custom_title.stateChanged.connect(enable_custom_title)

        def change_ebook_title():
            if ebook_title.text() == '':
                ebook_title.undo()
            self.ebook.set_custom_title(ebook_title.text())
        ebook_title.editingFinished.connect(change_ebook_title)

        # if self.config.get('to_library'):
        #     ebook_title.setDisabled(True)
        #     ebook_title.setToolTip(_(
        #         "The ebook's filename is automatically managed by Calibre "
        #         'according to metadata since the output path is set to '
        #         'Calibre Library.'))
        # ebook_title.textChanged.connect(self.ebook.set_custom_title)

        output_group = QGroupBox(_('Output Ebook'))
        output_layout = QHBoxLayout(output_group)
        output_button = QPushButton(_('Output'))
        output_format = OutputFormat()
        output_layout.addWidget(output_format)
        output_layout.addWidget(output_button)

        layout.addWidget(cache_group)
        layout.addWidget(engine_group)
        layout.addWidget(source_group)
        layout.addWidget(target_group)
        layout.addWidget(title_group, 1)
        layout.addWidget(output_group)

        source_lang.currentTextChanged.connect(
            self.trans_worker.set_source_lang)
        target_lang.currentTextChanged.connect(
            self.trans_worker.set_target_lang)

        def refresh_languages():
            source_lang.refresh.emit(
                self.current_engine.lang_codes.get('source'),
                self.ebook.source_lang,
                not isinstance(self.current_engine, CustomTranslate))
            target_lang.refresh.emit(
                self.current_engine.lang_codes.get('target'),
                self.ebook.target_lang)
        refresh_languages()
        self.ebook.set_source_lang(source_lang.currentText())

        def choose_engine(index):
            engine_name = engine_list.itemData(index)
            self.current_engine = get_engine_class(engine_name)
            self.trans_worker.set_engine_class(self.current_engine)
            self.batch_translation.emit()
            refresh_languages()
        engine_list.currentIndexChanged.connect(choose_engine)

        output_format.setCurrentText(self.ebook.output_format)

        def change_output_format(_format):
            self.ebook.set_output_format(_format)
        if self.ebook.is_extra_format():
            output_format.lock_format(self.ebook.input_format)
            change_output_format(self.ebook.input_format)
        else:
            change_output_format(output_format.currentText())
            output_format.currentTextChanged.connect(change_output_format)

        def output_ebook():
            if len(self.table.findItems(_('Translated'), Qt.MatchExactly)) < 1:
                self.alert.pop(_('The ebook has not been translated yet.'))
                return
            if self.table.non_aligned_count > 0:
                message = _(
                    'The number of lines in some translation units differs '
                    'between the original text and the translated text. Are '
                    'you sure you want to output without checking alignment?')
                if self.alert.ask(message) != 'yes':
                    return
            self.worker.translate_ebook(self.ebook, cache_only=True)
            self.done(1)
        output_button.clicked.connect(output_ebook)

        def working_start():
            if self.translate_all:
                widget.setVisible(False)
            widget.setDisabled(True)
        self.trans_worker.start.connect(working_start)

        def working_finished():
            widget.setVisible(True)
            widget.setDisabled(False)
        self.trans_worker.finished.connect(working_finished)

        return widget

    def layout_review(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        orientation = self.ui_settings.value(
            'review/layout_orientation', 'vertical')
        self.review_splitter = QSplitter(
            Qt.Horizontal if orientation == 'horizontal' else Qt.Vertical)
        self.review_splitter.setContentsMargins(0, 0, 0, 0)
        raw_text = CodeEditor()
        raw_text.setReadOnly(True)
        original_text = CodeEditor()
        original_text.setReadOnly(True)
        translation_text = CodeEditor()
        if self.ebook.target_direction == 'rtl':
            translation_text.setLayoutDirection(Qt.RightToLeft)
            document = translation_text.document()
            option = document.defaultTextOption()
            option.setAlignment(Qt.AlignRight)
            document.setDefaultTextOption(option)
        translation_text.setPlaceholderText(_('No translation yet'))
        self.review_splitter.addWidget(raw_text)
        self.review_splitter.addWidget(original_text)
        self.review_splitter.addWidget(translation_text)
        _size = [0] + [int(self.review_splitter.width() / 2)] * 2
        if self.review_splitter.orientation() == Qt.Vertical:
            _size = [0] + [int(self.review_splitter.height() / 2)] * 2
        self.review_splitter.setSizes(_size)

        def synchronizeScrollbars(editors):
            for editor in editors:
                for other_editor in editors:
                    if editor != other_editor:
                        editor.verticalScrollBar().valueChanged.connect(
                            other_editor.verticalScrollBar().setValue)
        synchronizeScrollbars((raw_text, original_text, translation_text))

        translation_text.cursorPositionChanged.connect(
            translation_text.ensureCursorVisible)

        def refresh_translation(paragraph):
            # TODO: check - why/how can "paragraph" be None and what should we do in such case?
            if paragraph is not None:
                raw_text.setPlainText(paragraph.raw.strip())
                original_text.setPlainText(paragraph.original.strip())
                translation_text.setPlainText(paragraph.translation)

        self.paragraph_sig.connect(refresh_translation)

        self.trans_worker.start.connect(
            lambda: translation_text.setReadOnly(True))
        self.trans_worker.finished.connect(
            lambda: translation_text.setReadOnly(False))

        # default_flag = translation_text.textInteractionFlags()

        # def disable_translation_text():
        #     if self.trans_worker.on_working:
        #         translation_text.setTextInteractionFlags(Qt.TextEditable)
        #         end = getattr(QTextCursor.MoveOperation, 'End', None) \
        #             or QTextCursor.End
        #         translation_text.moveCursor(end)
        #     else:
        #         translation_text.setTextInteractionFlags(default_flag)
        # translation_text.cursorPositionChanged.connect(
        #     disable_translation_text)

        def auto_open_close_splitter():
            if self.review_splitter.sizes()[0] > 0:
                sizes = [0] + [int(self.review_splitter.height() / 2)] * 2
            else:
                sizes = [int(self.review_splitter.height() / 3)] * 3
            self.review_splitter.setSizes(sizes)

        self.install_widget_event(
            self.review_splitter,
            self.review_splitter.handle(1),
            QEvent.MouseButtonDblClick,
            auto_open_close_splitter)

        self.table.itemDoubleClicked.connect(
            lambda item: auto_open_close_splitter())

        control = QWidget()
        control_layout = QHBoxLayout(control)
        control_layout.setContentsMargins(0, 0, 0, 0)

        self.trans_worker.start.connect(
            lambda: control.setVisible(False))
        self.trans_worker.finished.connect(
            lambda: control.setVisible(True))

        save_status = QLabel()
        save_button = QPushButton(_('&Save'))
        save_button.setDisabled(True)

        # Word Wrap toggle button
        word_wrap_button = QPushButton(_("Word Wrap"))
        word_wrap_button.setCheckable(True)

        word_wrap_enabled = self.ui_settings.value(
            'review/word_wrap', True, type=bool)  # Default to enabled
        word_wrap_button.setChecked(word_wrap_enabled)

        # Set initial word wrap state for all editors
        # Try different approaches for different Qt versions
        try:
            # Method 1: Modern Qt with LineWrapMode enum
            wrap_enabled = QPlainTextEdit.LineWrapMode.WidgetWidth
            wrap_disabled = QPlainTextEdit.LineWrapMode.NoWrap
        except AttributeError:
            try:
                # Method 2: Older Qt versions
                wrap_enabled = QPlainTextEdit.WidgetWidth
                wrap_disabled = QPlainTextEdit.NoWrap
            except AttributeError:
                # Method 3: Direct integer values as fallback
                wrap_enabled = 1  # WidgetWidth
                wrap_disabled = 0  # NoWrap

        raw_text.setLineWrapMode(wrap_enabled)
        original_text.setLineWrapMode(wrap_enabled)
        translation_text.setLineWrapMode(wrap_enabled)

        def toggle_word_wrap(checked):
            self.ui_settings.setValue('review/word_wrap', checked)
            wrap_mode = wrap_enabled if checked else wrap_disabled
            raw_text.setLineWrapMode(wrap_mode)
            original_text.setLineWrapMode(wrap_mode)
            translation_text.setLineWrapMode(wrap_mode)

        word_wrap_button.clicked.connect(toggle_word_wrap)

        layout_button = QPushButton(_("Horizontal Split"))
        layout_button.setCheckable(True)
        is_horizontal = self.ui_settings.value(
            'review/layout_orientation', 'vertical') == 'horizontal'
        layout_button.setChecked(is_horizontal)
        layout_button.toggled.connect(self.toggle_review_layout)

        status_indicator = TranslationStatus()

        control_layout.addWidget(status_indicator)
        control_layout.addWidget(word_wrap_button)
        control_layout.addWidget(layout_button)
        control_layout.addStretch(1)
        control_layout.addWidget(save_status)
        control_layout.addWidget(save_button)

        layout.addWidget(self.review_splitter, 1)
        layout.addWidget(control)

        def update_translation_status(row):
            paragraph = self.table.paragraph(row)
            if paragraph is None:
                return
            if not paragraph.translation:
                if paragraph.error is not None:
                    status_indicator.set_color(
                        StatusColor('red'), paragraph.error)
                else:
                    status_indicator.set_color(StatusColor('gray'))
            elif not paragraph.aligned and self.merge_enabled:
                status_indicator.set_color(
                    StatusColor('yellow'), )
            else:
                status_indicator.set_color(StatusColor('green'))
        self.table.row.connect(update_translation_status)

        def change_selected_item():
            if self.trans_worker.on_working:
                return
            paragraph = self.table.current_paragraph()
            if paragraph is None:
                return
            self.paragraph_sig.emit(paragraph)
            self.table.row.emit(paragraph.row)
        self.table.setCurrentItem(self.table.item(0, 0))
        change_selected_item()
        self.table.itemSelectionChanged.connect(change_selected_item)

        def translation_callback(paragraph):
            self.table.row.emit(paragraph.row)
            self.paragraph_sig.emit(paragraph)
            if self.cache is not None:
                self.cache.update_paragraph(paragraph)
            self.progress_bar.emit()

        self.trans_worker.callback.connect(translation_callback)

        def streaming_translation(data):
            if data == '':
                translation_text.clear()
            elif isinstance(data, Paragraph):
                self.table.setCurrentItem(self.table.item(data.row, 0))
            else:
                translation_text.insertPlainText(data)
        self.trans_worker.streaming.connect(streaming_translation)

        def modify_translation():
            if self.trans_worker.on_working and \
                    self.table.selected_count() > 1:
                return

            paragraph = self.table.current_paragraph()

            # TODO: check - why/how can "paragraph" be None and what should we
            # do in such case?
            if paragraph is not None:
                translation = translation_text.toPlainText()
                save_button.setDisabled(
                    translation == (paragraph.translation or ''))

        translation_text.textChanged.connect(modify_translation)

        self.editor_worker.show.connect(save_status.setText)

        def save_translation():
            paragraph = self.table.current_paragraph()

            # TODO: check - why/how can "paragraph" be None and what should we
            # do in such case?
            if paragraph is not None:
                save_button.setDisabled(True)
                translation = translation_text.toPlainText()
                paragraph.translation = translation
                paragraph.engine_name = self.current_engine.name
                paragraph.target_lang = self.ebook.target_lang
                self.table.row.emit(paragraph.row)
                if self.cache is not None:
                    self.cache.update_paragraph(paragraph)
                translation_text.setFocus(Qt.OtherFocusReason)
                self.editor_worker.start[str].emit(
                    _('Your changes have been saved.'))

        save_button.clicked.connect(save_translation)
        set_shortcut(save_button, 'save', save_translation, save_button.text())

        return widget

    def toggle_review_layout(self, checked):
        if checked:
            self.review_splitter.setOrientation(Qt.Horizontal)
            self.ui_settings.setValue('review/layout_orientation', 'horizontal')
        else:
            self.review_splitter.setOrientation(Qt.Vertical)
            self.ui_settings.setValue('review/layout_orientation', 'vertical')

    def layout_log(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.logging_text = QPlainTextEdit()
        self.logging_text.setPlaceholderText(_('Translation log'))
        self.logging_text.setReadOnly(True)
        layout.addWidget(self.logging_text)

        return widget

    def layout_errors(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.errors_text = QPlainTextEdit()
        self.errors_text.setPlaceholderText(_('Error log'))
        self.errors_text.setReadOnly(True)
        layout.addWidget(self.errors_text)

        return widget

    def get_progress_step(self, total):
        return int(round(100.0 / (total or 1), 100) * 1000000)

    def translate_all_paragraphs(self):
        """Translate the untranslated paragraphs when at least one is selected.
        Otherwise, retranslate all paragraphs regardless of prior translation.
        """
        paragraphs = self.table.get_selected_paragraphs(True, True)
        is_fresh = len(paragraphs) < 1
        if is_fresh:
            paragraphs = self.table.get_selected_paragraphs(False, True)
        self.progress_step = self.get_progress_step(len(paragraphs))
        if not self.translate_all:
            message = _(
                'Are you sure you want to translate all {:n} paragraphs?')
            if self.alert.ask(message.format(len(paragraphs))) != 'yes':
                return
        self.translate_all = True
        self.trans_worker.translate.emit(paragraphs, is_fresh)

    def translate_selected_paragraph(self):
        paragraphs = self.table.get_selected_paragraphs()
        # Consider selecting all paragraphs as translating all.
        if len(paragraphs) == self.table.rowCount():
            self.translate_all_paragraphs()
        else:
            self.progress_step = self.get_progress_step(len(paragraphs))
            self.trans_worker.translate.emit(paragraphs, True)

    def install_widget_event(
            self, source, target, action, callback, stop=False):
        def eventFilter(self, object, event):
            if event.type() == action:
                callback()
            return stop
        source.eventFilter = MethodType(eventFilter, source)
        target.installEventFilter(source)

    def terminate_preparework(self):
        if self.preparation_worker.on_working:
            if self.preparation_worker.canceled:
                return False
            action = self.alert.ask(
                _('Are you sure you want to cancel the preparation progress?'))
            if action != 'yes':
                return False
            self.preparation_worker.set_canceled(True)
            self.preparation_worker.progress_message.emit('Canceling...')
            return False
        return True

    def terminate_translation(self):
        if self.trans_worker.on_working:
            action = self.alert.ask(
                _('Are you sure you want to cancel the translation progress?'))
            if action != 'yes':
                return False
            self.trans_worker.set_need_close(True)
            self.trans_worker.set_canceled(True)
            return False
        return True

    def done(self, result):
        if not self.terminate_preparework():
            return
        if not self.terminate_translation():
            return

        # Close cache first to prevent corruption if cleanup crashes.
        if self.cache is not None:
            if self.cache.is_persistence():
                self.cache.close()
            elif result == 0:
                self.cache.destroy()

        # Disconnect all worker signals before quitting threads to prevent
        # pending cross-thread queued events from being delivered to stale
        # Python slots after the workers' C++ objects are destroyed.
        for worker in (self.trans_worker, self.preparation_worker,
                       self.editor_worker):
            try:
                worker.disconnect()
            except TypeError:
                pass

        # self.preparation_thread.requestInterruption()
        self.preparation_thread.quit()
        self.preparation_thread.wait()
        self.trans_thread.quit()
        self.trans_thread.wait()
        self.editor_thread.quit()
        self.editor_thread.wait()

        QDialog.done(self, result)
