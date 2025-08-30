from functools import wraps

from qt.core import (  # type: ignore
    pyqtSignal, pyqtSlot, Qt, QLabel, QDialog, QVBoxLayout, QStackedLayout,
    QWidget, QPushButton, QProgressBar, QFormLayout, QGroupBox, QObject,
    QThread, QHBoxLayout, QPlainTextEdit, QEvent)

from ..lib.utils import log, traceback_error

from .alert import AlertMessage


load_translations()  # type: ignore


def request(func):
    @wraps(func)
    def wrapper(self):
        try:
            func(self)
        except Exception:
            self.show_information.emit(
                'Oops, an error occurred!', traceback_error())
            self.stack_index.emit(3)
    return wrapper


class ChatgptBatchTranslationWorker(QObject):
    enable_apply_button = pyqtSignal(bool)
    stack_index = pyqtSignal(int)
    process_tip = pyqtSignal(str)
    trans_details = pyqtSignal(dict)
    show_information = pyqtSignal(str, str)
    paragraph_sig = pyqtSignal(object)
    finished = pyqtSignal()

    save_batch_id = pyqtSignal(str)
    save_file_id = pyqtSignal(str)
    remove_batch = pyqtSignal()

    create = pyqtSignal()
    check = pyqtSignal()
    cancel = pyqtSignal()
    apply = pyqtSignal()

    def __init__(self, batch_translator):
        QObject.__init__(self)
        self._batch_translator = batch_translator

        self._paragraphs = []
        self._file_id = None
        self._batch_id = None

        self._batch_info = {}

        self.create.connect(self.create_batch)
        self.check.connect(self.check_details)
        self.cancel.connect(self.cancel_batch)
        self.apply.connect(self.apply_batch)

    def set_paragraphs(self, paragraphs):
        self._paragraphs = paragraphs

    def set_batch_id(self, batch_id):
        self._batch_id = batch_id

    def set_file_id(self, file_id):
        self._file_id = file_id

    @pyqtSlot()
    @request
    def create_batch(self):
        self.process_tip.emit(_('processing...'))
        self.stack_index.emit(1)
        if self._file_id is None:
            self._file_id = self._batch_translator.upload(self._paragraphs)
            log.debug('A new file was uploaded: %s' % self._file_id)
            self.save_file_id.emit(self._file_id)
        self._batch_id = self._batch_translator.create(self._file_id)
        log.debug('A batch translation was created: %s' % self._batch_id)
        self.save_batch_id.emit(self._batch_id)
        self.check.emit()

    @pyqtSlot()
    @request
    def check_details(self):
        self.process_tip.emit(_('checking...'))
        self.stack_index.emit(1)
        log.debug('Checking the batch translation: %s' % self._batch_id)
        self._batch_info = self._batch_translator.check(self._batch_id)
        if self._batch_info.get('status') == 'completed':
            self.enable_apply_button.emit(True)
        self.trans_details.emit(self._batch_info)
        self.stack_index.emit(2)

    @pyqtSlot()
    @request
    def cancel_batch(self):
        self.process_tip.emit(_('canceling...'))
        self.stack_index.emit(1)
        self._batch_info = self._batch_translator.check(self._batch_id)
        if self._batch_info.get('status') not in (
                'cancelling', 'cancelled', 'completed', 'failed'):
            self._batch_translator.cancel(self._batch_id)
            self._batch_translator.delete(self._file_id)
        self.remove_batch.emit()
        self.finished.emit()

    @pyqtSlot()
    @request
    def apply_batch(self):
        self.enable_apply_button.emit(False)
        self.process_tip.emit(_('applying...'))
        self.stack_index.emit(1)
        translator = self._batch_translator.translator
        output_file_id = self._batch_info.get('output_file_id')
        translations = self._batch_translator.retrieve(output_file_id)
        for paragraph in self._paragraphs:
            if paragraph.md5 not in translations.keys():
                continue
            paragraph.translation = translations.get(paragraph.md5)
            paragraph.engine_name = translator.name
            paragraph.target_lang = translator.get_target_lang()
            self.paragraph_sig.emit(paragraph)
        self.finished.emit()


class ChatgptBatchTranslationManager(QDialog):
    batch_thread = QThread()

    def __init__(self, translator, cache, table, parent=None):
        QDialog.__init__(self, parent=parent)
        self.setWindowTitle(_('ChatGPT Batch Translation'))
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        # self.setModal(True)

        self.cache = cache
        self.table = table

        self.alert = AlertMessage(self)

        self.batch_worker = ChatgptBatchTranslationWorker(translator)
        self.batch_worker.moveToThread(self.batch_thread)
        self.batch_thread.finished.connect(self.batch_worker.deleteLater)
        self.batch_thread.start()

        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(100, 30, 30, 30)
        self.stack.addWidget(self.layout_create())
        self.stack.addWidget(self.layout_process())
        self.stack.addWidget(self.layout_details())
        self.stack.addWidget(self.layout_information())

        self.batch_worker.stack_index.connect(self.stack.setCurrentIndex)

        self.batch_id = self.cache.get_info('chatgpt_batch_id')
        self.file_id = self.cache.get_info('chatgpt_file_id')

        log.debug('Initialized batch id: %s' % self.batch_id)
        log.debug('Initialized file id: %s' % self.file_id)

        self.batch_worker.set_paragraphs(
            self.table.get_selected_paragraphs(True, True))
        self.batch_worker.set_batch_id(self.batch_id)
        self.batch_worker.set_file_id(self.file_id)

        def set_batch_id(batch_id):
            self.batch_id = batch_id
            self.cache.set_info('chatgpt_batch_id', batch_id)
            log.debug('A new batch id was stored: %s' % batch_id)
        self.batch_worker.save_batch_id.connect(set_batch_id)

        def set_file_id(file_id):
            self.file_id = file_id
            self.cache.set_info('chatgpt_file_id', file_id)
            log.debug('A new file id was stored: %s' % file_id)
        self.batch_worker.save_file_id.connect(set_file_id)

        def remove_batch():
            self.file_id = None
            self.cache.del_info('chatgpt_batch_id')
            self.cache.del_info('chatgpt_file_id')
            log.debug('The batch information was deleted.')
        self.batch_worker.remove_batch.connect(remove_batch)

        def apply_paragraph(paragraph):
            self.table.row.emit(paragraph.row)
            self.cache.update_paragraph(paragraph)
        self.batch_worker.paragraph_sig.connect(apply_paragraph)

        if self.batch_id is not None:
            self.batch_worker.check.emit()

        self.batch_worker.finished.connect(lambda: self.done(0))

    def layout_create(self):
        title = QLabel(_('Create a new batch translation'))
        title.setStyleSheet('font-size:16px;font-weight:bold;')
        message = QLabel(_(
            'All original content must be uploaded to OpenAI for batch '
            'translation, and you will need to wait up to 24 hours to '
            'continue the translation process.'
            '<a href="https://cookbook.openai.com/examples/batch_processing">'
            'more details</a>'))
        message.setWordWrap(True)
        message.setOpenExternalLinks(True)
        button = QPushButton('Create Batch Translation')

        button.clicked.connect(self.batch_worker.create)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(message)
        layout.addSpacing(20)
        layout.addWidget(button)
        layout.setAlignment(button, Qt.AlignCenter)
        layout.addStretch(1)

        return widget

    def layout_process(self):
        progress = QProgressBar()
        progress.setMinimum(0)
        progress.setMaximum(0)
        description = QLabel()

        self.batch_worker.process_tip.connect(description.setText)

        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.addStretch(1)
        layout.addWidget(progress)
        layout.addWidget(description)
        layout.setAlignment(description, Qt.AlignCenter)
        layout.addStretch(1)

        return widget

    def layout_details(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        # layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.layout_data(), 1)
        layout.addWidget(self.layout_buttons())

        return widget

    def layout_buttons(self):
        refresh = QPushButton(_('Refresh'))
        cancel = QPushButton(_('Cancel Batch Translation'))
        apply = QPushButton(_('Apply'))
        apply.setEnabled(False)

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(refresh)
        layout.addWidget(cancel)
        layout.addStretch(1)
        layout.addWidget(apply)

        self.batch_worker.enable_apply_button.connect(apply.setEnabled)

        refresh.clicked.connect(self.batch_worker.check.emit)
        apply.clicked.connect(lambda: self.batch_worker.apply.emit())

        def cancel_batch_translation():
            action = self.alert.ask(
                _('Are you sure you want to cancel the batch translation?'))
            if action == 'yes':
                self.batch_worker.cancel.emit()
        cancel.clicked.connect(cancel_batch_translation)

        return widget

    def layout_data(self):
        status = QLabel()
        detail = QPlainTextEdit()
        detail.setReadOnly(True)

        def set_details_data(data):
            detail.clear()
            batch_status = data.get('status')
            status.setText(str(batch_status))
            if batch_status == 'completed':
                request_counts = data.get('request_counts')
                detail.appendPlainText(str(request_counts))
            else:
                error_info = data.get('errors')
                detail.appendPlainText(str(error_info))
        self.batch_worker.trans_details.connect(set_details_data)

        widget = QGroupBox(_('Batch translation details'))
        layout = QFormLayout(widget)
        layout.addRow(_('Status'), status)
        layout.addRow(_('Detail'), detail)

        self.set_form_layout_policy(layout)

        return widget

    def layout_information(self):
        title = QLabel()
        content = QPlainTextEdit()

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(title)
        layout.addWidget(content)

        def set_information(title_text, content_text):
            title.setText(title_text)
            content.setPlainText(content_text)
        self.batch_worker.show_information.connect(set_information)

        return widget

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.parent().raise_()

    def done(self, reason):
        QDialog.done(self, reason)
        self.parent().raise_()

    def set_form_layout_policy(self, layout):
        layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setLabelAlignment(Qt.AlignRight)
