import time
from types import MethodType

from calibre.constants import __version__

from .lib.utils import uid
from .lib.config import get_config
from .lib.cache import Paragraph, TranslationCache, get_cache
from .lib.translation import get_engine_class, get_translator, get_translation
from .lib.element import get_element_handler, Extraction
from .lib.conversion import extract_item

from . import EbookTranslator
from .components import (
    EngineList, layout_info, SourceLang, TargetLang, InputFormat, OutputFormat,
    AlertMessage, AdvancedTranslationTable)


try:
    from qt.core import (
        Qt, QObject, QDialog, QGroupBox, QWidget, QVBoxLayout, QHBoxLayout,
        QPlainTextEdit, QPushButton, QSplitter, QLabel, QThread, QLineEdit,
        QGridLayout, QProgressBar, pyqtSignal, pyqtSlot, QPixmap, QEvent,
        QStackedWidget, QSpacerItem, QTextCursor, QTabWidget)
except ImportError:
    from PyQt5.Qt import (
        Qt, QObject, QDialog, QGroupBox, QWidget, QVBoxLayout, QHBoxLayout,
        QPlainTextEdit, QPushButton, QSplitter, QLabel, QThread, QLineEdit,
        QGridLayout, QProgressBar, pyqtSignal, pyqtSlot, QPixmap, QEvent,
        QStackedWidget, QSpacerItem, QTextCursor, QTabWidget)

load_translations()


class StatusWorker(QObject):
    start = pyqtSignal((str,), (str, object))
    show = pyqtSignal(str)

    def __init__(self):
        QObject.__init__(self)
        self.start[str].connect(self.show_message)
        self.start[str, object].connect(self.show_message)

    @pyqtSlot(str)
    @pyqtSlot(str, object)
    def show_message(self, message, callback=None):
        self.show.emit(message)
        time.sleep(1)
        self.show.emit('')
        callback and callback()


class PreparationWorker(QObject):
    start = pyqtSignal()
    progress = pyqtSignal(int)
    progress_message = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, engine_class, ebook):
        QObject.__init__(self)
        self.ebook = ebook
        self.engine_class = engine_class
        self.start.connect(self.prepare_ebook_data)

    def clean_cache(self, cache):
        cache.is_fresh() and cache.destroy()

    @pyqtSlot()
    def prepare_ebook_data(self):
        input_path = self.ebook.get_input_path()
        element_handler = get_element_handler(
            self.engine_class.placeholder, self.engine_class.separator)
        merge_length = str(element_handler.get_merge_length())
        cache_id = uid(
            input_path + self.engine_class.name + self.ebook.target_lang
            + merge_length + TranslationCache.__version__
            + Extraction.__version__)
        cache = get_cache(cache_id)

        if cache.is_fresh() or not cache.is_persistence():
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
            elements = extract_item(input_path, self.ebook.input_format)
            self.progress.emit(30)
            b = time.time()
            print('extract: ', b - a)
            if self.cancel():
                self.clean_cache(cache)
                return
            # --------------------------
            self.progress_message.emit(_('Filtering ebook content...'))
            original_group = element_handler.prepare_original(elements)
            self.progress.emit(80)
            c = time.time()
            print('filter: ', c - b)
            if self.cancel():
                self.clean_cache(cache)
                return
            # --------------------------
            self.progress_message.emit(_('Preparing user interface...'))
            cache.save(original_group)
            self.progress.emit(100)
            d = time.time()
            print('cache: ', d - c)
            if self.cancel():
                self.clean_cache(cache)
                return

        self.finished.emit(cache_id)

    def cancel(self):
        return self.thread().isInterruptionRequested()


class TranslationWorker(QObject):
    start = pyqtSignal()
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

        self.canceled = False
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

    @pyqtSlot(list, bool)
    def translate_paragraphs(self, paragraphs=[], fresh=False):
        """:fresh: retranslate all paragraphs."""
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
        self.finished.emit()


class CreateTranslationProject(QDialog):
    start_translation = pyqtSignal(object)

    def __init__(self, parent, ebook):
        QDialog.__init__(self, parent)
        self.ebook = ebook

        layout = QVBoxLayout(self)
        self.choose_format = self.layout_format()

        self.start_button = QPushButton(_('Start'))
        # self.start_button.setStyleSheet(
        #     'padding:0;height:48;font-size:20px;color:royalblue;'
        #     'text-transform:uppercase;')
        self.start_button.clicked.connect(self.show_advanced)

        layout.addWidget(self.choose_format)
        layout.addWidget(self.start_button)

    def layout_format(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        input_group = QGroupBox(_('Input Format'))
        input_layout = QGridLayout(input_group)
        input_format = InputFormat(self.ebook.files.keys())
        input_format.setFixedWidth(150)
        input_layout.addWidget(input_format)

        def change_input_format(format):
            self.ebook.set_input_format(format)
        change_input_format(input_format.currentText())
        input_format.currentTextChanged.connect(change_input_format)

        target_group = QGroupBox(_('Target Language'))
        target_layout = QVBoxLayout(target_group)
        target_lang = TargetLang()
        target_lang.setFixedWidth(150)
        target_layout.addWidget(target_lang)

        engine_class = get_engine_class()
        target_lang.refresh.emit(
            engine_class.lang_codes.get('target'),
            engine_class.config.get('target_lang'))

        def change_target_format(format):
            self.ebook.set_target_lang(format)
        change_target_format(target_lang.currentText())
        target_lang.currentTextChanged.connect(change_target_format)

        layout.addWidget(input_group)
        layout.addWidget(target_group)

        return widget

    @pyqtSlot()
    def show_advanced(self):
        self.done(0)
        self.start_translation.emit(self.ebook)


class AdvancedTranslation(QDialog):
    raw_text = pyqtSignal(str)
    original_text = pyqtSignal(str)
    translation_text = pyqtSignal((), (str,))
    progress_bar = pyqtSignal()

    preparation_thread = QThread()
    trans_thread = QThread()
    status_thread = QThread()

    def __init__(self, parent, icon, worker, ebook):
        QDialog.__init__(self, parent)
        self.api = parent.current_db.new_api
        self.icon = icon
        self.worker = worker
        self.ebook = ebook
        self.config = get_config()
        self.alert = AlertMessage(self)
        # self.error = JobError(self)
        self.current_engine = get_engine_class()
        self.cache = None

        self.on_working = False
        self.prgress_step = 0
        self.translate_all = False

        self.status_worker = StatusWorker()
        self.status_worker.moveToThread(self.status_thread)
        self.status_thread.finished.connect(self.status_worker.deleteLater)
        self.status_thread.start()

        self.trans_worker = TranslationWorker(self.current_engine, self.ebook)
        self.trans_worker.moveToThread(self.trans_thread)
        self.trans_thread.finished.connect(self.trans_worker.deleteLater)
        self.trans_thread.start()

        self.preparation_worker = PreparationWorker(
            self.current_engine, self.ebook)
        self.preparation_worker.moveToThread(self.preparation_thread)
        self.preparation_thread.finished.connect(
            self.preparation_worker.deleteLater)
        self.preparation_thread.start()

        layout = QVBoxLayout(self)

        self.waiting = self.layout_progress()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.waiting)
        layout.addWidget(self.stack)
        layout.addWidget(layout_info())

        def working_status():
            self.on_working = True
            self.logging_text.clear()
            self.errors_text.clear()
        self.trans_worker.start.connect(working_status)

        self.trans_worker.logging.connect(
            lambda text, error: self.errors_text.appendPlainText(text)
            if error else self.logging_text.appendPlainText(text))

        def working_finished():
            if self.translate_all and not self.trans_worker.cancel_request():
                failures = len(self.table.get_selected_items(True, True))
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
            self.on_working = False
        self.trans_worker.finished.connect(working_finished)

        # self.trans_worker.error.connect(
        #     lambda title, reason, detail: self.error.show_error(
        #         title, _('Failed') + ': ' + reason, det_msg=detail))

        def prepare_table_layout(cache_id):
            self.cache = get_cache(cache_id)
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
        mode = getattr(Qt.TransformationMode, 'SmoothTransformation', None) \
            or Qt.SmoothTransformation
        cover_image = cover_image.scaledToHeight(480, mode)

        cover = QLabel()
        cover.setAlignment(Qt.AlignCenter)
        cover.setPixmap(cover_image)

        progress_bar = QProgressBar()
        progress_bar.setFormat('')
        progress_bar.setValue(0)
        # progress_bar.setFixedWidth(300)
        # progress_bar.setMaximum(0)
        # progress_bar.setMinimum(0)
        self.preparation_worker.progress.connect(progress_bar.setValue)

        label = QLabel(_('Loading ebook data, please wait...'))
        label.setAlignment(Qt.AlignCenter)
        self.preparation_worker.progress_message.connect(label.setText)

        layout.addItem(QSpacerItem(0, 0), 0, 0, 1, 3)
        layout.addWidget(cover, 1, 1)
        layout.addItem(QSpacerItem(0, 30), 2, 0, 1, 3)
        layout.addWidget(progress_bar, 3, 1)
        layout.addWidget(label, 4, 1)
        layout.addItem(QSpacerItem(0, 0), 5, 0, 1, 3)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(5, 1)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(2, 1)

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
                else review_index))

        splitter = QSplitter()
        splitter.addWidget(self.layout_table())
        splitter.addWidget(tabs)

        layout.addWidget(self.layout_control())
        layout.addWidget(splitter, 1)

        return widget

    def layout_table(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        progress_bar = QProgressBar()
        progress_bar.setMaximum(100000000)
        progress_bar.setVisible(False)

        def write_progress():
            value = progress_bar.value() + self.prgress_step
            if value > progress_bar.maximum():
                value = progress_bar.maximum()
            progress_bar.setValue(value)
        self.progress_bar.connect(write_progress)

        layout.addWidget(self.table, 1)
        layout.addWidget(progress_bar)
        layout.addWidget(self.layout_table_control())

        def working_start():
            if self.translate_all:
                progress_bar.setValue(0)
                progress_bar.setVisible(True)
        self.trans_worker.start.connect(working_start)

        self.trans_worker.finished.connect(
            lambda: progress_bar.setVisible(False))

        return widget

    def layout_table_control(self):
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)

        delete_button = QPushButton(_('Delete'))
        paragraph_count = QLabel()
        paragraph_count.setAlignment(Qt.AlignCenter)
        translate_all = QPushButton('  %s  ' % _('Translate All'))
        translate_selected = QPushButton('  %s  ' % _('Translate Selected'))

        delete_button.clicked.connect(self.table.delete_by_rows)
        translate_all.clicked.connect(self.translate_all_paragraphs)
        translate_selected.clicked.connect(self.translate_selected_paragraph)

        delete_button.setDisabled(True)
        translate_selected.setDisabled(True)

        def get_paragraph_count(select_all=True):
            item_count = char_count = 0
            paragraphs = self.table.get_selected_items(select_all=select_all)
            for paragraph in paragraphs:
                item_count += 1
                char_count += len(paragraph.original)
            return (item_count, char_count)
        all_item_count, all_char_count = get_paragraph_count(True)

        def item_selection_changed():
            disabled = self.table.selected_count() < 1
            delete_button.setDisabled(disabled)
            translate_selected.setDisabled(disabled)
            item_count, char_count = get_paragraph_count(False)
            total = '%s/%s' % (item_count, all_item_count)
            parts = '%s/%s' % (char_count, all_char_count)
            paragraph_count.setText(
                _('Total items: {}').format(total) + ' · ' +
                _('Character count: {}').format(parts))
        item_selection_changed()
        self.table.itemSelectionChanged.connect(item_selection_changed)

        action_layout.addWidget(delete_button)
        action_layout.addWidget(paragraph_count, 1)
        action_layout.addWidget(translate_all)
        action_layout.addWidget(translate_selected)

        stop_widget = QWidget()
        stop_layout = QHBoxLayout(stop_widget)
        stop_layout.setContentsMargins(0, 0, 0, 0)
        # stop_layout.addStretch(1)
        stop_button = QPushButton(_('Stop'))
        stop_layout.addWidget(stop_button)

        def terminate_translation():
            if self.terminate_translation():
                stop_button.setDisabled(True)
                stop_button.setText(_('Stopping...'))
        stop_button.clicked.connect(terminate_translation)

        def terminate_finished():
            stop_button.setDisabled(False)
            stop_button.setText(_('Stop'))
            self.translation_text[str].emit(
                self.table.current_paragraph().translation)
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

        engine_group = QGroupBox(_('Translation Engine'))
        engine_layout = QVBoxLayout(engine_group)
        engine_list = EngineList(self.current_engine.name)
        engine_list.setFixedWidth(150)
        engine_layout.addWidget(engine_list)

        source_group = QGroupBox(_('Source Language'))
        source_layout = QVBoxLayout(source_group)
        source_lang = SourceLang()
        source_lang.setFixedWidth(150)
        source_layout.addWidget(source_lang)

        target_group = QGroupBox(_('Target Language'))
        target_layout = QVBoxLayout(target_group)
        target_lang = TargetLang()
        target_lang.setFixedWidth(150)
        target_layout.addWidget(target_lang)

        cache_group = QGroupBox(_('Cache Status'))
        cache_layout = QVBoxLayout(cache_group)
        cache_status = QLabel(
            _('Enabled') if self.cache.is_persistence() else _('Disabled'))
        cache_status.setAlignment(Qt.AlignCenter)
        cache_status.setStyleSheet(
            'border-radius:2px;color:white;background-color:%s;'
            % ('green' if self.cache.is_persistence() else 'grey'))
        cache_layout.addWidget(cache_status)

        save_group = QGroupBox(_('Output Ebook'))
        save_layout = QHBoxLayout(save_group)
        save_ebook = QPushButton(_('Output'))
        ebook_title = QLineEdit()
        ebook_title.setText(self.ebook.title)
        ebook_title.setCursorPosition(0)
        output_format = OutputFormat()
        output_format.setFixedWidth(150)
        save_layout.addWidget(QLabel(_('Title')))
        save_layout.addWidget(ebook_title, 1)
        save_layout.addWidget(output_format)
        save_layout.addWidget(save_ebook)

        ebook_title.textChanged.connect(self.ebook.set_title)

        layout.addWidget(cache_group)
        layout.addWidget(engine_group)
        layout.addWidget(source_group)
        layout.addWidget(target_group)
        layout.addWidget(save_group)

        source_lang.currentTextChanged.connect(
            self.trans_worker.set_source_lang)
        target_lang.currentTextChanged.connect(
            self.trans_worker.set_target_lang)

        def refresh_languages():
            source_lang.refresh.emit(
                self.current_engine.lang_codes.get('source'),
                self.current_engine.config.get('source_lang'),
                not self.current_engine.is_custom())
            lang = self.current_engine.config.get('target_lang')
            if target_lang.findText(self.ebook.target_lang):
                lang = self.ebook.target_lang
            target_lang.refresh.emit(
                self.current_engine.lang_codes.get('target'), lang)
        refresh_languages()
        self.ebook.set_source_lang(source_lang.currentText())

        def choose_engine(index):
            engine_name = engine_list.itemData(index)
            self.current_engine = get_engine_class(engine_name)
            self.trans_worker.set_engine_class(self.current_engine)
            refresh_languages()
        engine_list.currentIndexChanged.connect(choose_engine)

        def change_output_format(format):
            self.ebook.set_output_format(format)
        change_output_format(output_format.currentText())
        output_format.currentTextChanged.connect(change_output_format)

        if self.ebook.is_extra_format():
            output_format.lock_format(self.ebook.input_format)
            change_output_format(self.ebook.input_format)

        def output_ebook():
            if len(self.table.findItems(_('Translated'), Qt.MatchExactly)) < 1:
                self.alert.pop('The ebook has not been translated yet.')
                return
            lang_code = self.current_engine.get_iso639_target_code(
                self.ebook.target_lang)
            self.ebook.set_lang_code(lang_code)
            self.worker.translate_ebook(self.ebook, cache_only=True)
            self.done(1)
        save_ebook.clicked.connect(output_ebook)

        def working_start():
            self.translate_all and widget.setVisible(False)
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

        splitter = QSplitter(Qt.Vertical)
        splitter.setContentsMargins(0, 0, 0, 0)
        raw_text = QPlainTextEdit()
        raw_text.setReadOnly(True)
        original_text = QPlainTextEdit()
        original_text.setReadOnly(True)
        translation_text = QPlainTextEdit()
        translation_text.setPlaceholderText(_('No translation yet'))
        splitter.addWidget(raw_text)
        splitter.addWidget(original_text)
        splitter.addWidget(translation_text)
        splitter.setSizes([0, 1, 1])

        translation_text.cursorPositionChanged.connect(
            translation_text.ensureCursorVisible)

        self.raw_text.connect(raw_text.setPlainText)
        self.original_text.connect(original_text.setPlainText)
        self.translation_text.connect(translation_text.clear)
        self.translation_text[str].connect(translation_text.setPlainText)
        self.trans_worker.start.connect(
            lambda: translation_text.setReadOnly(False))
        self.trans_worker.finished.connect(
            lambda: translation_text.setReadOnly(False))

        default_flag = translation_text.textInteractionFlags()

        def disable_translation_text():
            if self.on_working:
                translation_text.setTextInteractionFlags(Qt.TextEditable)
                end = getattr(QTextCursor.MoveOperation, 'End', None) \
                    or QTextCursor.End
                translation_text.moveCursor(end)
            else:
                translation_text.setTextInteractionFlags(default_flag)
        translation_text.cursorPositionChanged.connect(
            disable_translation_text)

        def auto_open_close_splitter():
            size = 0 if splitter.sizes()[0] > 0 else 1
            splitter.setSizes([size, 1, 1])
        self.install_widget_event(
            splitter, splitter.handle(1), QEvent.MouseButtonDblClick,
            auto_open_close_splitter)

        self.table.itemDoubleClicked.connect(
            lambda item: auto_open_close_splitter())

        control = QWidget()
        control.setVisible(False)
        controle_layout = QHBoxLayout(control)
        controle_layout.setContentsMargins(0, 0, 0, 0)

        save_status = QLabel()
        save_button = QPushButton(_('Save'))

        controle_layout.addWidget(save_status)
        controle_layout.addStretch(1)
        controle_layout.addWidget(save_button)

        layout.addWidget(splitter)
        layout.addWidget(control)

        def change_selected_item():
            if self.on_working:
                return
            paragraph = self.table.current_paragraph()
            if paragraph is None:
                return
            self.raw_text.emit(paragraph.raw)
            self.original_text.emit(paragraph.original.strip())
            self.translation_text[str].emit(paragraph.translation)
        self.table.itemSelectionChanged.connect(change_selected_item)
        self.table.setCurrentItem(self.table.item(0, 0))
        change_selected_item()

        def translation_callback(paragraph):
            row = paragraph.row
            self.table.row.emit(row)
            self.raw_text.emit(paragraph.raw)
            self.original_text.emit(paragraph.original)
            self.translation_text[str].emit(paragraph.translation)
            self.cache.update_paragraph(paragraph)
            self.progress_bar.emit()
        self.trans_worker.callback.connect(translation_callback)

        def streaming_translation(data):
            if data == '':
                self.translation_text.emit()
            elif isinstance(data, Paragraph):
                self.table.setCurrentItem(self.table.item(data.row, 0))
            else:
                translation_text.insertPlainText(data)
        self.trans_worker.streaming.connect(streaming_translation)

        def modify_translation():
            if self.on_working and self.table.selected_count() > 1:
                return
            paragraph = self.table.current_paragraph()
            translation = translation_text.toPlainText()
            control.setVisible(
                bool(translation) and translation != paragraph.translation)
        translation_text.textChanged.connect(modify_translation)

        def save_translation():
            paragraph = self.table.current_paragraph()
            translation = translation_text.toPlainText()
            paragraph.translation = translation
            paragraph.engine_name = self.current_engine.name
            paragraph.target_lang = self.ebook.target_lang
            self.table.row.emit(paragraph.row)
            self.cache.update_paragraph(paragraph)
            self.status_worker.start[str, object].emit(
                _('Your changes have been saved.'),
                lambda: control.setVisible(False))
            translation_text.setFocus(Qt.OtherFocusReason)
        self.status_worker.show.connect(save_status.setText)
        save_button.clicked.connect(save_translation)

        return widget

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
        paragraphs = self.table.get_selected_items(True, True)
        is_fresh = len(paragraphs) < 1
        if is_fresh:
            paragraphs = self.table.get_selected_items(False, True)
        self.prgress_step = self.get_progress_step(len(paragraphs))
        if not self.translate_all:
            message = _(
                'Are you sure you want to translate all {:n} paragraphs?')
            if self.alert.ask(message.format(len(paragraphs))) != 'yes':
                return
        self.translate_all = True
        self.trans_worker.translate.emit(paragraphs, is_fresh)

    def translate_selected_paragraph(self):
        paragraphs = self.table.get_selected_items()
        # Consider selecting all paragraphs as translating all.
        if len(paragraphs) == self.table.rowCount():
            self.translate_all_paragraphs()
        else:
            self.prgress_step = self.get_progress_step(len(paragraphs))
            self.trans_worker.translate.emit(paragraphs, True)

    def install_widget_event(
            self, source, target, action, callback, stop=False):
        def eventFilter(self, object, event):
            event.type() == action and callback()
            return stop
        source.eventFilter = MethodType(eventFilter, source)
        target.installEventFilter(source)

    def terminate_translation(self):
        if self.on_working:
            action = self.alert.ask(
                _('Are you sure you want to stop the translation progress?'))
            if action != 'yes':
                return False
        self.trans_worker.set_canceled(True)
        return True

    def done(self, result):
        if not self.terminate_translation():
            return
        self.preparation_thread.requestInterruption()
        self.preparation_thread.quit()
        self.preparation_thread.wait()
        self.trans_thread.quit()
        self.trans_thread.wait()
        self.status_thread.quit()
        self.status_thread.wait()
        if self.cache is not None:
            if self.cache.is_persistence():
                self.cache.close()
            elif result == 0:
                self.cache.destroy()
        QDialog.done(self, result)
